"""Consistent error responses: {"error": {"code", "message", "details"?}}."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("modelradar.api")

_CODES = {400: "bad_request", 404: "not_found", 405: "method_not_allowed", 422: "validation_error"}


def _response(
    status: int, code: str, message: str, details: list[dict[str, str]] | None = None
) -> JSONResponse:
    body: dict[str, object] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=jsonable_encoder({"error": body}))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODES.get(exc.status_code, "error")
        message = "Resource not found." if exc.status_code == 404 else str(exc.detail)
        return _response(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"][1:]) or "query", "message": err["msg"]}
            for err in exc.errors()
        ]
        return _response(422, "validation_error", "Some parameters are invalid.", details)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # Log the exception type only: no request details (no IP addresses, no parameters).
        logger.error("unhandled error: %s", type(exc).__name__)
        return _response(500, "internal_error", "The service could not complete the request.")
