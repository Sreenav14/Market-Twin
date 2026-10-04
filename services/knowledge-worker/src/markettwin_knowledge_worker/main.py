"""Private Knowledge Worker HTTP application."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry import trace

from markettwin_knowledge_worker.api.preview import router as preview_router
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


def create_app() -> FastAPI:
    app = FastAPI(title="MarketTwin Knowledge Worker", version="0.1.0", lifespan=lifespan)
    app.state.preview_service = KnowledgePreviewService(KnowledgeBuilder())
    app.include_router(preview_router)
    return app


app = create_app()
