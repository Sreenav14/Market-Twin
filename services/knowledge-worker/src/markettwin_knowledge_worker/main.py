"""Private Knowledge Worker HTTP application."""

import asyncio
import hmac
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

from markettwin_knowledge_worker.api.preview import router as preview_router
from markettwin_knowledge_worker.config import KnowledgeWorkerSettings
from markettwin_knowledge_worker.knowledge_builder import KnowledgeBuilder
from markettwin_knowledge_worker.observability import initialize_knowledge_observability
from markettwin_knowledge_worker.services.knowledge_preview_service import KnowledgePreviewService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    enabled = initialize_knowledge_observability()
    try:
        yield
    finally:
        if enabled:
            provider = trace.get_tracer_provider()
            flush = getattr(provider, "force_flush", None)
            if flush is not None:
                await asyncio.to_thread(flush, timeout_millis=5000)


def create_app(settings: KnowledgeWorkerSettings | None = None) -> FastAPI:
    settings = settings if settings is not None else KnowledgeWorkerSettings.from_env()
    app = FastAPI(title="MarketTwin Knowledge Worker", version="0.1.0", lifespan=lifespan)
    preview_slots = asyncio.Semaphore(settings.preview_max_concurrency)

    async def authenticate_preview(
        request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        # Authenticate before FastAPI parses or spools the multipart body.
        if request.url.path.rstrip("/") == "/internal/v1/knowledge/preview":
            secret = settings.knowledge_internal_secret
            if secret is not None and not hmac.compare_digest(
                request.headers.get("authorization", "").encode(),
                f"Bearer {secret.get_secret_value()}".encode(),
            ):
                return JSONResponse(
                    {"detail": "Internal knowledge authentication is required."},
                    status_code=401, headers={"WWW-Authenticate": "Bearer"},
                )
            # Refuse excess requests before multipart parsing/spooling, rather
            # than keeping an unbounded queue of uploaded sources in memory.
            if preview_slots.locked():
                return JSONResponse(
                    {"detail": "Knowledge preview capacity is busy. Retry later."},
                    status_code=503, headers={"Retry-After": "5"},
                )
            async with preview_slots:
                return await call_next(request)
        return await call_next(request)

    app.middleware("http")(authenticate_preview)
    app.state.preview_service = KnowledgePreviewService(
        KnowledgeBuilder(), timeout_seconds=settings.preview_timeout_seconds,
    )
    app.include_router(preview_router)
    return app


app = create_app()
