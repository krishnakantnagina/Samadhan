"""S01 — API Contract (Website <-> Core), v1.0.0.

Single definition of the request/response shapes between the citizen website and the
FastAPI core. Spec: docs/specs/S01-api-contract.md (section numbers below refer to it).

Either of us can change this file. If you do, update docs/specs/S01-api-contract.md and tell
the other so the mock and tests stay in sync.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import UUID4, BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "1.0.0"

# --- Limits (S01 sections 3 and 4.1). Audio limits are still to confirm (G-API-1). ---
TEXT_MIN_LENGTH = 1
TEXT_MAX_LENGTH = 1000
AUDIO_MAX_SECONDS = 60
AUDIO_MAX_BYTES = 2 * 1024 * 1024
ACCEPTED_AUDIO_TYPES = frozenset({"audio/webm", "audio/ogg", "audio/mp4", "audio/wav"})
COMPLAINT_ID_PATTERN = r"^SMD-\d{4,}$"


# --- Enums -------------------------------------------------------------------------------


class ComplaintStatus(StrEnum):
    """Ticket status (S01 section 5)."""

    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    NEEDS_REVIEW = "needs_review"


class Action(StrEnum):
    """What the client should do next (S01 section 4.3)."""

    ASK = "ask"
    CONFIRM = "confirm"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    OUT_OF_SCOPE = "out_of_scope"
    ERROR = "error"


class OfficeLevel(StrEnum):
    """Jurisdiction level of the routed office (S01 section 4.4)."""

    WARD = "ward"
    ZONE = "zone"
    MUNICIPAL_CORP = "municipal_corp"
    GRAM_PANCHAYAT = "gram_panchayat"
    BLOCK = "block"
    DISTRICT = "district"


class Command(StrEnum):
    """Text messages the backend treats as commands, not free text (S01 section 4.1)."""

    CANCEL = "cancel"
    RESTART = "restart"


class ErrorCode(StrEnum):
    """Error codes of the non-2xx body (S01 section 7)."""

    INVALID_INPUT = "INVALID_INPUT"
    INVALID_COMPLAINT_ID = "INVALID_COMPLAINT_ID"
    COMPLAINT_NOT_FOUND = "COMPLAINT_NOT_FOUND"
    AUDIO_TOO_LARGE = "AUDIO_TOO_LARGE"
    UNSUPPORTED_AUDIO = "UNSUPPORTED_AUDIO"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.INVALID_COMPLAINT_ID: 400,
    ErrorCode.COMPLAINT_NOT_FOUND: 404,
    ErrorCode.AUDIO_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_AUDIO: 415,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}

# Citizen-safe: no stack traces, keys, or internal names (S01 section 9, rule 3).
ERROR_REPLY_TEXT: dict[ErrorCode, str] = {
    ErrorCode.INVALID_INPUT: "कृपया अपना संदेश दोबारा भेजें।",
    ErrorCode.INVALID_COMPLAINT_ID: "कृपया सही शिकायत क्रमांक दर्ज करें (जैसे SMD-0007)।",
    ErrorCode.COMPLAINT_NOT_FOUND: "यह शिकायत क्रमांक नहीं मिला। कृपया जाँच कर दोबारा प्रयास करें।",
    ErrorCode.AUDIO_TOO_LARGE: "आवाज़ की रिकॉर्डिंग बहुत लंबी है। कृपया छोटा संदेश भेजें।",
    ErrorCode.UNSUPPORTED_AUDIO: "यह ऑडियो प्रारूप समर्थित नहीं है। कृपया टेक्स्ट में लिखें।",
    ErrorCode.SERVICE_UNAVAILABLE: "सेवा अभी उपलब्ध नहीं है। कृपया कुछ देर बाद प्रयास करें।",
    ErrorCode.INTERNAL_ERROR: "कुछ गड़बड़ हो गई। कृपया दोबारा प्रयास करें।",
}


# --- Models ------------------------------------------------------------------------------


class ContractModel(BaseModel):
    """Base for all contract models. Unknown fields are rejected on the server side."""

    model_config = ConfigDict(extra="forbid")


class MessageRequest(ContractModel):
    """Form fields of POST /api/v1/message (S01 section 4.1).

    `audio` is an UploadFile at the route level and is not part of this model.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: UUID4
    message_id: UUID4
    text: str | None = Field(None, min_length=TEXT_MIN_LENGTH, max_length=TEXT_MAX_LENGTH)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)

    @model_validator(mode="after")
    def _lat_lng_together(self) -> "MessageRequest":
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must be sent together.")
        return self


class Office(ContractModel):
    """Routed office (S01 section 4.4)."""

    name: str
    level: OfficeLevel


class Ticket(ContractModel):
    """Created ticket, returned when action = submitted (S01 section 4.4)."""

    complaint_id: str = Field(pattern=COMPLAINT_ID_PATTERN)
    department: str
    office: Office
    status: ComplaintStatus


class MessageResponse(ContractModel):
    """200 body of POST /api/v1/message (S01 section 4.2).

    Every field is always present; absent values are null, never omitted.
    """

    session_id: UUID4
    message_id: UUID4
    action: Action
    ask_for: str | None
    reply_text: str = Field(min_length=1)
    transcript: str | None
    summary: dict[str, Any] | None
    ticket: Ticket | None
    duplicate: bool


class StatusResponse(ContractModel):
    """200 body of GET /api/v1/status/{complaint_id} (S01 section 5).

    Exactly these four fields: never transcript, audio, location, contact or collected fields.
    """

    complaint_id: str = Field(pattern=COMPLAINT_ID_PATTERN)
    status: ComplaintStatus
    department: str
    updated_at: datetime


class HealthResponse(ContractModel):
    """200 body of GET /health (S01 section 6)."""

    status: str = "ok"


class ErrorResponse(ContractModel):
    """Body of every non-2xx response (S01 section 7)."""

    error_code: ErrorCode
    message: str  # for developers and logs
    reply_text: str  # citizen-safe, can be shown as-is
    request_id: str


class SpeakRequest(ContractModel):
    """POST /api/v1/speak body (S17 section 1). Reuses S01's own text bounds -- every text this
    endpoint is ever asked to speak is a reply_text the backend already generated, already inside
    them."""

    text: str = Field(min_length=TEXT_MIN_LENGTH, max_length=TEXT_MAX_LENGTH)


class SpeakResponse(ContractModel):
    """200 body: Sarvam's own base64 WAV, forwarded unmodified (S17 D-S17-4)."""

    audio_base64: str


# --- Shared helpers (used by the mock and the real backend) --------------------------------


def normalise_content_type(content_type: str | None) -> str:
    """'audio/webm;codecs=opus' -> 'audio/webm' (browsers append codec parameters)."""
    return (content_type or "").split(";", 1)[0].strip().lower()


REPLY_CANCELLED = "आपकी शिकायत रद्द कर दी गई है।"  # D-S04-6: matches mock/app.py verbatim
REPLY_RESTART = "ठीक है, शुरू से शुरू करते हैं। आपकी क्या समस्या है?"  # ditto

# S20 section 5: whole-utterance aliases, typed or spoken (transcript). Adjust from real Sarvam
# transcripts (live check L6). Substrings never match, only the entire normalised utterance.
COMMAND_ALIASES: dict[str, Command] = {
    **dict.fromkeys(
        ("cancel", "कैंसल", "कैन्सल", "रद्द", "रद्द करो", "रद्द करें", "रद्द कीजिए", "शिकायत रद्द करो"),
        Command.CANCEL,
    ),
    **dict.fromkeys(
        (
            "restart",
            "रीस्टार्ट",
            "रिस्टार्ट",
            "शुरू से",
            "शुरू से शुरू करो",
            "फिर से शुरू करो",
            "दोबारा शुरू करो",
        ),
        Command.RESTART,
    ),
}


def _normalise_command_text(text: str) -> str:
    return " ".join(text.lower().split()).rstrip(".।!? ")


def parse_command(text: str | None) -> Command | None:
    """Return the command if the whole of `text` is `cancel`/`restart` or a known alias
    (case-insensitive, trailing punctuation ignored). S20 section 5."""
    if text is None:
        return None
    return COMMAND_ALIASES.get(_normalise_command_text(text))


def check_message_inputs(
    *, text: str | None, has_audio: bool, lat: float | None, lng: float | None
) -> str | None:
    """Route-level input rules of POST /api/v1/message (S01 section 4.1).

    Returns a developer-facing message for an INVALID_INPUT error, or None when valid.
    """
    if text is not None and not TEXT_MIN_LENGTH <= len(text.strip()) <= TEXT_MAX_LENGTH:
        return f"text must be {TEXT_MIN_LENGTH}-{TEXT_MAX_LENGTH} characters after trimming."
    if (lat is None) != (lng is None):
        return "lat and lng must be sent together."
    if text is not None and has_audio:
        return "Provide text or audio, not both."
    if text is None and not has_audio and lat is None:
        return "Provide text, audio, or lat+lng."
    return None
