"""Authenticated client for the private browser owner service."""

import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID

import httpx
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, SecretStr


class ViewerGrant(BaseModel):
    """One-time browser viewer grant returned by the worker."""

    model_config = ConfigDict(extra="forbid")

    ticket: str = Field(min_length=32, max_length=128, repr=False)
    viewer_url: AnyUrl


class HitlWorkerClient:
    """Signs every short internal request; never logs body or response values."""

    def __init__(
        self,
        *,
        base_url: str,
        secret: SecretStr,
        timeout_seconds: float = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret = secret.get_secret_value().encode("utf-8")
        self._timeout = timeout_seconds
        self._transport = transport

    async def issue_viewer_grant(
        self,
        *,
        actor_id: UUID,
        request_id: UUID,
        browser_session_id: UUID,
        lease_id: UUID,
        lease_token: str,
        generation: int,
        expires_at: str,
        execution_id: UUID,
        journey_id: UUID,
    ) -> ViewerGrant:
        response = await self._post(
            path="/internal/hitl/leases",
            payload={
                "actor_id": str(actor_id),
                "request_id": str(request_id),
                "browser_session_id": str(browser_session_id),
                "lease_id": str(lease_id),
                "lease_token": lease_token,
                "generation": generation,
                "expires_at": expires_at,
                "execution_id": str(execution_id),
                "journey_id": str(journey_id),
            },
            response_model=ViewerGrant,
        )
        if response is None:
            raise RuntimeError("The supervised browser owner is unavailable.")
        return response

    async def _post(
        self,
        *,
        path: str,
        payload: dict[str, object],
        response_model: type[ViewerGrant] | None = None,
    ) -> ViewerGrant | None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        signature = hmac.new(
            self._secret,
            timestamp.encode("ascii") + b"." + nonce.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=2), transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}{path}",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-MarketTwin-HITL-Timestamp": timestamp,
                        "X-MarketTwin-HITL-Nonce": nonce,
                        "X-MarketTwin-HITL-Signature": signature,
                    },
                )
                response.raise_for_status()
                if response_model is None:
                    return None
                return response_model.model_validate(response.json())
        except (httpx.HTTPError, ValueError, TypeError):
            # Do not include downstream content, token, or exception in API errors.
            raise RuntimeError("The supervised browser owner is unavailable.") from None

    async def notify(
        self,
        *,
        path: str,
        payload: dict[str, object],
    ) -> None:
        await self._post(path=path, payload=payload)
