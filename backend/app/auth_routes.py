"""S31 -- /api/v1/auth: phone registration and saved login. Spec: docs/specs/S31-registration.md.

POST /auth/start   {phone}                  -> {challenge_id, provider, hint}   sends a code (demo: nothing to send; the hint says PIN 5555)
POST /auth/verify  {challenge_id, code}     -> {token, expires_at, phone_masked}
GET  /auth/me      Authorization: Bearer    -> {phone_masked, expires_at}      401 AUTH_REQUIRED (no token) / AUTH_EXPIRED (unknown or expired token: log in again)
POST /auth/logout  Authorization: Bearer    -> {}
Plain sync routes (the stores are synchronous). When AUTH_PROVIDER is not set every endpoint answers 503 SERVICE_UNAVAILABLE: enquiries and status checks never need login.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Header
from pydantic import Field

from app import auth
from app import schemas as api
from mock.errors import ApiError

router = APIRouter(prefix="/auth")


class StartRequest(api.ContractModel):
    phone: str = Field(min_length=7, max_length=20)


class StartResponse(api.ContractModel):
    challenge_id: str
    provider: str
    hint: str | None = None


class VerifyRequest(api.ContractModel):
    challenge_id: str = Field(min_length=8, max_length=64)
    code: str = Field(min_length=1, max_length=12)


class LoginResponse(api.ContractModel):
    token: str
    expires_at: datetime
    phone_masked: str


class MeResponse(api.ContractModel):
    phone_masked: str
    expires_at: datetime


def _service() -> auth.AuthService:
    try:
        return auth.get_service()
    except auth.AuthDisabled as exc:
        raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, f"Login is not enabled: {exc}") from exc


@router.post("/start", response_model=StartResponse)
def start(body: StartRequest) -> StartResponse:
    try:
        result = _service().start(body.phone)
    except auth.AuthError as exc:
        raise ApiError(exc.code, exc.message) from exc
    return StartResponse(challenge_id=result.challenge_id, provider=result.provider, hint=result.hint)


@router.post("/verify", response_model=LoginResponse)
def verify(body: VerifyRequest) -> LoginResponse:
    try:
        result = _service().verify(body.challenge_id, body.code)
    except auth.AuthError as exc:
        raise ApiError(exc.code, exc.message) from exc
    return LoginResponse(token=result.token, expires_at=result.expires_at, phone_masked=auth.mask_phone(result.user.phone))


@router.get("/me", response_model=MeResponse)
def me(authorization: Annotated[str | None, Header()] = None) -> MeResponse:
    token = auth.token_from_header(authorization)
    if token is None:
        raise ApiError(api.ErrorCode.AUTH_REQUIRED, "No login token.")
    service = _service()
    user = service.user_for_token(token)
    if user is None:
        raise ApiError(api.ErrorCode.AUTH_EXPIRED, "Login expired.")
    return MeResponse(phone_masked=auth.mask_phone(user.phone), expires_at=service.expires_at(token))


@router.post("/logout")
def logout(authorization: Annotated[str | None, Header()] = None) -> dict:
    token = auth.token_from_header(authorization)
    if token:
        _service().logout(token)
    return {}
