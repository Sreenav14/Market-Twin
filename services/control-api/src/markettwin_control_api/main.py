"""MarketTwin Control API application."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final, Literal

from fastapi import FastAPI
from markettwin_shared.messaging import KafkaProducer
from pydantic import BaseModel

from markettwin_control_api.api.applications import router as applications_router
from markettwin_control_api.api.artifacts import router as artifacts_router
from markettwin_control_api.api.auth import router as auth_router
from markettwin_control_api.api.ingestion import router as ingestion_router
from markettwin_control_api.api.lifecycle import router as lifecycle_router
from markettwin_control_api.api.runtime_snapshots import router as runtime_snapshots_router
from markettwin_control_api.api.target_authorizations import router as target_authorizations_router
from markettwin_control_api.api.targets import router as targets_router
from markettwin_control_api.api.test_run import router as test_run_router
from markettwin_control_api.api.test_run_results import router as test_run_results_router
from markettwin_control_api.api.workspaces import router as workspaces_router
from markettwin_control_api.config import get_settings
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.knowledge.processor import run_ingestion_processor
from markettwin_control_api.services import OutboxRelay, run_outbox_relay

APP_NAME: Final[str] = "MarketTwin Control API"
APP_VERSION: Final[str] = "0.1.0"


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: Literal["ok"]
    service: str
    version: str
    environment: str


class KafkaHealthResponse(BaseModel):
    """Kafka connectivity, independent of Control API process health."""

    status: Literal["connected", "unavailable"]
    outbox_relay_enabled: bool


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()

    @asynccontextmanager
    async def lifespan(
        application: FastAPI,
    ) -> AsyncGenerator[None, None]:
        """Own long-lived application resources."""

        database = DatabaseRuntime(settings)
        application.state.database = database
        ingestion_task = asyncio.create_task(
            run_ingestion_processor(database.engine, settings), name="markettwin-ingestion"
        )
        relay_task: asyncio.Task[None] | None = None

        if settings.outbox_relay_enabled:
            producer = KafkaProducer(settings.kafka_producer_settings)
            
            relay = OutboxRelay(
                session_factory = database.session_factory,
                producer = producer,
            )
            
            relay_task = asyncio.create_task(run_outbox_relay(
                relay = relay,
                producer = producer,
            ),
            name = "markettwin-outbox-relay",
            )
        
        try:
            yield
        finally:
            ingestion_task.cancel()
            try:
                await ingestion_task
            except asyncio.CancelledError:
                pass
            if relay_task is not None:
                relay_task.cancel()
                
                try:
                    await relay_task
                except asyncio.CancelledError:
                    pass
            await database.close()

    application = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description="Control plane API for MarketTwin V1.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    async def health() -> HealthResponse:
        """Confirm that the Control API process is running."""

        return HealthResponse(
            status="ok",
            service="control-api",
            version=APP_VERSION,
            environment=settings.app_env,
        )

    application.add_api_route(
        "/health",
        health,
        methods=["GET"],
        response_model=HealthResponse,
        tags=["System"],
        summary="Check API process health",
    )

    async def kafka_health() -> KafkaHealthResponse:
        """Probe Kafka authentication and connectivity without publishing events."""
        status: Literal["connected", "unavailable"] = "unavailable"
        producer: KafkaProducer | None = None
        try:
            async with asyncio.timeout(5):
                producer = KafkaProducer(settings.kafka_producer_settings)
                await producer.start()
                status = "connected"
        except Exception:
            pass
        finally:
            if producer is not None:
                try:
                    async with asyncio.timeout(2):
                        await producer.stop()
                except Exception:
                    pass
        return KafkaHealthResponse(
            status=status,
            outbox_relay_enabled=settings.outbox_relay_enabled,
        )

    application.add_api_route(
        "/api/v1/health/kafka",
        kafka_health,
        methods=["GET"],
        response_model=KafkaHealthResponse,
        tags=["System"],
        summary="Check Kafka connectivity",
    )

    application.include_router(auth_router)
    application.include_router(lifecycle_router)
    application.include_router(workspaces_router)
    application.include_router(applications_router)
    application.include_router(ingestion_router)
    application.include_router(targets_router)
    application.include_router(target_authorizations_router)
    application.include_router(test_run_router)
    application.include_router(test_run_results_router)
    application.include_router(artifacts_router)
    application.include_router(runtime_snapshots_router)
    return application


app = create_app()
