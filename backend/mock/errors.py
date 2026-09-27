"""S01 error envelope (section 7) as FastAPI handlers. The real backend should reuse these."""

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import schemas as api


class ApiError(Exception):
    """Raise from a route to return the S01 error body for `code`."""

    def __init__(self, code: api.ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def error_response(code: api.ErrorCode, message: str) -> JSONResponse:
    body = api.ErrorResponse(
        error_code=code,
        message=message,
        reply_text=api.ERROR_REPLY_TEXT[code],
        request_id=uuid.uuid4().hex[:8],
    )
    return JSONResponse(status_code=api.ERROR_STATUS[code], content=body.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.code, exc.message)

    # S01 section 7: validation errors are 400 INVALID_INPUT, not FastAPI's default 422.
    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"] if part != "body")
        return error_response(api.ErrorCode.INVALID_INPUT, f"{where}: {first['msg']}")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return error_response(api.ErrorCode.INTERNAL_ERROR, "Unexpected error.")
