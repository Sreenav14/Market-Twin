"""Authenticated HTTP handoff and same-origin WSS service for human browser control."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner import OwnerLease, ViewerRejectedError
from markettwin_execution_orchestrator.browser.owner_registry import BrowserOwnerRegistry
from markettwin_execution_orchestrator.browser.viewer_authority import DatabaseViewerAuthority
from markettwin_execution_orchestrator.browser.viewer_gateway import ViewerGateway

_active_service: HITLWorkerService | None = None


class LeaseEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    actor_id: UUID
    request_id: UUID
    browser_session_id: UUID
    execution_id: UUID
    journey_id: UUID
    lease_id: UUID
    lease_token: SecretStr
    generation: Annotated[int, Field(ge=1)]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def require_aware_expiration(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Lease expiration must be timezone-aware.")
        return value

    def owner_lease(self) -> OwnerLease:
        return OwnerLease(
            handle=BrowserSessionHandle(
                self.browser_session_id,
                self.execution_id,
                self.journey_id,
            ),
            actor_id=self.actor_id,
            lease_id=self.lease_id,
            generation=self.generation,
            expires_at=self.expires_at,
            request_id=self.request_id,
        )


class RevokeEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: UUID | None = None
    lease_id: UUID | None = None
    browser_session_id: UUID | None = None
    generation: Annotated[int, Field(ge=1)]


class ObserveEnvelope(BaseModel):
    """Exact read-only frame request; carries no input, URL, script or protocol method."""

    model_config = ConfigDict(extra="forbid", strict=True)

    actor_id: UUID
    browser_session_id: UUID
    execution_id: UUID
    journey_id: UUID
    generation: Annotated[int, Field(ge=0)]


class HITLWorkerService:
    """Own the internal handoff endpoint and WSS gateway in the worker process."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        registry: BrowserOwnerRegistry,
        internal_secret: str,
        allowed_origins: frozenset[str],
        viewer_url: str,
        allow_local_ws: bool = False,
    ) -> None:
        if len(internal_secret.encode("utf-8")) < 32:
            raise ValueError("The HITL internal secret must contain at least 32 bytes.")
        parsed_viewer_url = urlsplit(viewer_url)
        expected_scheme = "ws" if allow_local_ws else "wss"
        if (
            parsed_viewer_url.scheme != expected_scheme
            or not parsed_viewer_url.hostname
            or parsed_viewer_url.path != "/api/v1/hitl-viewer"
            or parsed_viewer_url.query
            or parsed_viewer_url.fragment
            or parsed_viewer_url.username is not None
            or parsed_viewer_url.password is not None
        ):
            raise ValueError("The HITL viewer URL must use WSS.")
        self._secret = internal_secret.encode("utf-8")
        self._viewer_url = viewer_url
        self._registry = registry
        self._used_nonces: dict[str, float] = {}
        self._resume_events: dict[UUID, asyncio.Event] = {}
        self._server: Any = None
        self._server_task: asyncio.Task[None] | None = None
        self._authority = DatabaseViewerAuthority(session_factory, registry)
        self._gateway = ViewerGateway(
            registry,
            self._authority,
            allowed_origins=allowed_origins,
            allow_local_ws=allow_local_ws,
        )
        self.app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        self.app.include_router(self._gateway.router)
        self.app.include_router(self._internal_router())

    @property
    def is_running(self) -> bool:
        return self._server_task is not None and not self._server_task.done()

    def _internal_router(self) -> APIRouter:
        router = APIRouter(prefix="/internal/hitl")

        async def signed_body(request: Request) -> bytes:
            chunks: list[bytes] = []
            body_length = 0
            async for chunk in request.stream():
                body_length += len(chunk)
                if body_length > 4096:
                    raise HTTPException(status_code=413, detail="Request too large")
                chunks.append(chunk)
            body = b"".join(chunks)
            timestamp = request.headers.get("X-MarketTwin-HITL-Timestamp", "")
            nonce = request.headers.get("X-MarketTwin-HITL-Nonce", "")
            signature = request.headers.get("X-MarketTwin-HITL-Signature", "")
            if (
                not timestamp.isascii()
                or not timestamp.isdigit()
                or not nonce.isascii()
                or re.fullmatch(r"[A-Za-z0-9_-]{24,128}", nonce) is None
                or not signature.isascii()
                or len(signature) != 64
            ):
                raise HTTPException(status_code=401, detail="Unauthorized")
            now = time.time()
            timestamp_value = int(timestamp)
            if abs(timestamp_value - int(now)) > 30:
                raise HTTPException(status_code=401, detail="Unauthorized")
            expected = hmac.new(
                self._secret,
                timestamp.encode("ascii") + b"." + nonce.encode("ascii") + b"." + body,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise HTTPException(status_code=401, detail="Unauthorized")
            self._used_nonces = {
                key: expires for key, expires in self._used_nonces.items() if expires > now
            }
            if nonce in self._used_nonces or len(self._used_nonces) >= 10_000:
                raise HTTPException(status_code=401, detail="Unauthorized")
            self._used_nonces[nonce] = max(now, float(timestamp_value)) + 31
            return body

        async def parse_signed(
            request: Request,
            model: type[BaseModel],
        ) -> BaseModel:
            body = await signed_body(request)
            try:
                return model.model_validate_json(body, strict=True)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid handoff") from None

        async def attach(request: Request) -> dict[str, str]:
            envelope = await parse_signed(request, LeaseEnvelope)
            assert isinstance(envelope, LeaseEnvelope)
            lease = envelope.owner_lease()
            now = datetime.now(UTC)
            if lease.expires_at <= now or lease.expires_at > now + timedelta(seconds=60):
                raise HTTPException(status_code=409, detail="Browser handoff unavailable")
            try:
                if not await self._authority.validate_lease_token(
                    lease,
                    envelope.lease_token.get_secret_value(),
                ):
                    raise ViewerRejectedError("Lease is unavailable.")
                await self._registry.begin_human_control(lease.handle, generation=lease.generation)
                if not await self._authority.activate_human(lease):
                    raise ViewerRejectedError("Lease is unavailable.")
                ticket = await self._gateway.issue_ticket(lease.actor_id, lease)
                if lease.request_id is None:
                    raise ViewerRejectedError("Lease is unavailable.")
            except Exception:
                raise HTTPException(status_code=409, detail="Browser handoff unavailable") from None
            return {"ticket": ticket, "viewer_url": self._viewer_url}

        async def renew(request: Request) -> dict[str, bool]:
            envelope = await parse_signed(request, LeaseEnvelope)
            assert isinstance(envelope, LeaseEnvelope)
            lease = envelope.owner_lease()
            try:
                if not await self._authority.validate_lease_token(
                    lease,
                    envelope.lease_token.get_secret_value(),
                ):
                    raise ViewerRejectedError("Lease is unavailable.")
                await self._gateway.renew_for_actor(lease.actor_id, lease.lease_id)
            except Exception:
                raise HTTPException(status_code=409, detail="Browser handoff unavailable") from None
            return {"renewed": True}

        async def revoke(request: Request) -> dict[str, bool]:
            envelope = await parse_signed(request, RevokeEnvelope)
            assert isinstance(envelope, RevokeEnvelope)
            try:
                durable = await self._authority.revoked_handle(
                    generation=envelope.generation, request_id=envelope.request_id,
                    lease_id=envelope.lease_id, session_id=envelope.browser_session_id,
                )
                if durable is None:
                    raise ViewerRejectedError("Lease is unavailable.")
                handle, request_id, completed = durable
                if completed:
                    return {"revoked": True}
                await self._registry.revoke(handle, envelope.generation)
                await self._gateway.revoke_request(request_id, envelope.generation)
                self._resume_events.setdefault(request_id, asyncio.Event()).set()
            except Exception:
                raise HTTPException(status_code=409, detail="Browser handoff unavailable") from None
            return {"revoked": True}

        async def observe(request: Request) -> Response:
            envelope = await parse_signed(request, ObserveEnvelope)
            assert isinstance(envelope, ObserveEnvelope)
            try:
                handle = self._registry.handle(
                    session_id=envelope.browser_session_id,
                    execution_id=envelope.execution_id,
                    journey_id=envelope.journey_id,
                )
                if not await self._authority.observer_permitted(
                    envelope.actor_id, handle, envelope.generation,
                ):
                    raise ViewerRejectedError("Observation is unavailable.")
                image = await self._registry.observe(handle, generation=envelope.generation)
            except Exception:
                raise HTTPException(
                    status_code=409, detail="Browser observation unavailable.",
                ) from None
            return Response(
                content=image,
                media_type="image/jpeg",
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )

        router.add_api_route("/leases", attach, methods=["POST"])
        router.add_api_route("/leases/renew", renew, methods=["POST"])
        router.add_api_route("/leases/revoke", revoke, methods=["POST"])
        router.add_api_route("/observe", observe, methods=["POST"])
        return router

    async def wait_for_revoke(self, request_id: UUID, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("A positive HITL wait timeout is required.")
        event = self._resume_events.setdefault(request_id, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), timeout_seconds)
        finally:
            self._resume_events.pop(request_id, None)

    async def start(
        self, *, host: str, port: int, cert_file: str | None, key_file: str | None
    ) -> None:
        """Listen privately or behind the trusted TLS reverse proxy only."""
        import uvicorn

        if (cert_file is None) != (key_file is None):
            raise ValueError("Both HITL viewer TLS files must be configured together.")
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            ssl_certfile=cert_file,
            ssl_keyfile=key_file,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1,::1",
        )
        server = uvicorn.Server(config)
        self._server = server
        global _active_service
        _active_service = self
        self._server_task = asyncio.create_task(server.serve())
        async with asyncio.timeout(10):
            while not server.started:
                if self._server_task.done():
                    await self._server_task
                    raise RuntimeError("The HITL worker service stopped during startup.")
                await asyncio.sleep(0.02)

    async def stop(self) -> None:
        global _active_service
        server = getattr(self, "_server", None)
        task = getattr(self, "_server_task", None)
        if server is not None:
            server.should_exit = True
        if task is not None:
            await task
        if _active_service is self:
            _active_service = None


async def wait_for_human_action_resume(request_id: UUID, timeout_seconds: float) -> None:
    """Wait until the signed Control API revoke follows release/cancel."""

    if _active_service is None:
        raise RuntimeError("The HITL worker service is not running.")
    await _active_service.wait_for_revoke(request_id, timeout_seconds)


__all__ = [
    "HITLWorkerService",
    "LeaseEnvelope",
    "RevokeEnvelope",
    "wait_for_human_action_resume",
]
