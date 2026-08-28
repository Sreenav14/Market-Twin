"""MarketTwin Control API application."""


from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from markettwin_control_api.api.applications import router as applications_router
from markettwin_control_api.api.auth import router as auth_router
from markettwin_control_api.api.targets import router as targets_router
from markettwin_control_api.api.workspaces import router as workspaces_router
from markettwin_control_api.config import get_settings
from markettwin_control_api.database import DatabaseRuntime

APP_NAME: Final[str] = "MarketTwin Control API"
APP_VERSION: Final[str] = "0.1.0"


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: Literal["ok"]
    service: str
    version: str
    environment: str


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

        try:
            yield
        finally:
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

    application.include_router(auth_router)
    application.include_router(workspaces_router)
    application.include_router(applications_router)
    application.include_router(targets_router)
    return application


app = create_app()