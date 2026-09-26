import uuid

import httpx
from api import ErrorCode, ErrorResponse

MESSAGE_PATH = "/api/v1/message"


def new_id() -> str:
    return str(uuid.uuid4())


def post_message(
    client: httpx.Client,
    *,
    session_id: str | None = None,
    message_id: str | None = None,
    text: str | None = None,
    audio: bytes | None = None,
    audio_type: str = "audio/webm",
    lat: float | None = None,
    lng: float | None = None,
    omit: tuple[str, ...] = (),
) -> httpx.Response:
    """POST /api/v1/message as multipart/form-data (S01 section 4.1)."""
    fields = {
        "session_id": session_id or new_id(),
        "message_id": message_id or new_id(),
    }
    if text is not None:
        fields["text"] = text
    if lat is not None:
        fields["lat"] = str(lat)
    if lng is not None:
        fields["lng"] = str(lng)
    # (None, value) makes httpx send a plain multipart field even when there is no file.
    files = {name: (None, value) for name, value in fields.items() if name not in omit}
    if audio is not None:
        files["audio"] = ("voice.webm", audio, audio_type)
    return client.post(MESSAGE_PATH, files=files)


def assert_error(response: httpx.Response, status: int, code: ErrorCode) -> ErrorResponse:
    assert response.status_code == status, response.text
    body = ErrorResponse.model_validate(response.json())
    assert body.error_code == code
    assert body.reply_text.strip()
    return body
