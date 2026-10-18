"""Non-cacheable sanitized route wrapper shared by live observation and pause."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class ObservationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def safe_handler(request: Request) -> Response:
            try:
                response = await handler(request)
                response.headers.update(NO_STORE)
                return response
            except HTTPException as error:
                return JSONResponse(status_code=error.status_code,
                                    content={"detail": error.detail}, headers=NO_STORE)
            except RequestValidationError:
                return JSONResponse(status_code=422,
                                    content={"detail": "Invalid observation request."},
                                    headers=NO_STORE)
        return safe_handler


