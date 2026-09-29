"""S05 — Turn Engine (T12). Spec: docs/specs/S05-turn-engine.md.

One LLM call per citizen turn: Groq primary, Gemini Flash fallback, one attempt each. Output is
untrusted -- S07 (Validator) checks every field against the service spec before anything is stored
or shown (PROJECT.md section 4, S01 section 2).

Either of us can change this file. If you do, update docs/specs/S05-turn-engine.md and tell the
other.
"""

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import LLMConfig, get_llm_config
from app.service_spec import EnumField, IntegerField, LocationField, ServiceSpec, StringField

logger = logging.getLogger(__name__)

PROVIDER_TIMEOUT_SECONDS = 6.0  # S04 section 5 / S05 provider table
TURN_DEADLINE_SECONDS = 14.0  # S26 D-S26-4: stop starting new providers past this

SYSTEM_INSTRUCTIONS = """\
You extract structured data from one message a citizen sent a government grievance chatbot.
Output ONLY a JSON object matching this schema -- no prose, no markdown fences:
{"service_id": "<one of the listed service ids, or null>", \
"fields": {"<field_name>": "<value>"}, "confirmed": true/false, "ack": "<see rules>" or null}

Rules:
- service_id must be one of the listed service ids, or null if the message matches none of them.
  Never invent a service.
- fields keys must be field names from the matched service's spec only, and only for fields the
  citizen actually gave or changed THIS turn -- never repeat a field already listed as collected.
  Never invent a field name or a value outside its listed allowed values.
- confirmed is true only if "awaiting confirmation" below is true AND this turn plainly affirms the
  summary (e.g. "haan", "yes", "sahi hai", "theek hai") with no correction in it. A correction (a
  new/changed field value) is confirmed: false even if phrased politely.
- If the message reads as unrelated to every listed service, set service_id: null and leave fields
  empty -- never guess the closest service.
- Only put a citizen's location text into fields if the matched service has a "location" field
  expecting a place name, and only the place name itself, not commentary.
- A location value must be a specific NAME of a place (a ward, colony, locality or village name).
  A generic word is not a name: "village"/"गाँव", "neighbourhood"/"मोहल्ला", "house"/"घर",
  "hand pump"/"हैंडपंप", "tap"/"नल", "tank"/"टंकी" alone (including "our village", "हमाए गाँव") name
  no place, so leave the location field out entirely.
- A bare yes/no answer ("हाँ", "नहीं", "yes", "no") is never a location; leave the location field out.
- ack: only when this turn gave NEW information, one short warm sentence in Devanagari Hindi (max 12 words)
  that acknowledges what the citizen said. It must not be a question, must not promise anything, and must
  not state any fact about offices, officers, dates, numbers or ticket status. Otherwise null.
  Repeat the citizen's own words (the symptom and how long, if said). Good: "समझ गया, तीन दिन से पानी नहीं आ रहा।"
  Bad (a promise or claim of action): "हम जाँच कर रहे हैं", "जल्द ठीक होगा", "शिकायत भेज दी गई".
"""


class TurnEngineUnavailable(RuntimeError):
    """Both providers failed. S04 maps this to 503 SERVICE_UNAVAILABLE."""


@dataclass(frozen=True)
class SessionState:
    """Minimal session view S05 needs (S02 sessions columns). S06 must produce this shape."""

    service_id: str | None
    collected_fields: dict[str, Any]
    awaiting_confirmation: bool


@dataclass(frozen=True)
class Message:
    """One row of conversation history (S02 messages), as S05 needs it."""

    role: Literal["citizen", "bot"]
    text: str


class TurnResult(BaseModel):
    """S05 output: untrusted, checked by S07 before it touches storage or the citizen."""

    service_id: str | None
    fields: dict[str, Any]
    confirmed: bool
    ack: str | None = None  # S25: untrusted, sanitised by the validator


class _RawTurnOutput(BaseModel):
    """Structural shape only (S05 STRUCTURAL VALIDATION). Extra keys ignored (D-S05-5)."""

    model_config = ConfigDict(extra="ignore")

    service_id: str | None = None
    fields: dict[str, Any] = {}
    confirmed: bool = False
    ack: Any = None  # S25: any type accepted here, the validator decides


class Provider(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...  # raw response text; raises _ProviderError


class _ProviderError(RuntimeError):
    """A provider call failed (timeout, connection error, non-2xx)."""


# --- Prompt construction (S05 section BEHAVIOR 2-3) ---------------------------------------


def _field_vocabulary(field: EnumField | IntegerField | StringField | LocationField) -> str:
    line = f"  - {field.name} ({field.type}, {'required' if field.required else 'optional'})"
    if isinstance(field, EnumField):
        values = ", ".join(v.value for v in field.values)
        line += f": allowed values = [{values}]"
    elif isinstance(field, IntegerField):
        line += f": whole number, {field.min}..{field.max}"
    elif isinstance(field, StringField):
        line += f": free text, max {field.max_length} chars"
    elif isinstance(field, LocationField):
        line += ": GPS (handled separately, do not extract) or a place name string"
    return line


def _service_block(spec: ServiceSpec) -> str:
    lines = [
        f'- service_id "{spec.service}" ({spec.label.en}). Hints: {"; ".join(spec.recognise)}',
        "  Fields:",
    ]
    lines.extend(_field_vocabulary(f) for f in spec.fields)
    return "\n".join(lines)


def _recent_messages_block(recent_messages: Sequence[Message]) -> str:
    if not recent_messages:
        return "(none)"
    return "\n".join(f"{m.role}: {m.text}" for m in recent_messages)


def _build_prompt(
    session: SessionState,
    specs: dict[str, ServiceSpec],
    text: str,
    lat: float | None,
    lng: float | None,
    recent_messages: Sequence[Message],
) -> str:
    services = "\n".join(_service_block(spec) for spec in specs.values())
    gps_note = "yes" if lat is not None and lng is not None else "no"
    return f"""\
{SYSTEM_INSTRUCTIONS}
Listed services:
{services}

Session state:
- active service_id so far: {session.service_id or "none yet"}
- already collected fields: {json.dumps(session.collected_fields, ensure_ascii=False)}
- awaiting confirmation: {"true" if session.awaiting_confirmation else "false"}

Recent turns (oldest first):
{_recent_messages_block(recent_messages)}

This turn:
- citizen also just shared their GPS location: {gps_note}
- citizen said: {text}
"""


# --- Providers ------------------------------------------------------------------------------


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, reasoning_effort: str | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._reasoning_effort = reasoning_effort
        self.name = f"groq:{model}"

    def complete(self, prompt: str) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        if self._reasoning_effort and self._model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = self._reasoning_effort  # S26 D-S26-2: gpt-oss only
        try:
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()  # a 429 raises here and the chain moves on (S26 D-S26-3)
        except httpx.HTTPError as exc:
            raise _ProviderError(f"groq:{self._model}: {exc}") from exc
        return response.json()["choices"][0]["message"]["content"]


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str) -> str:
        try:
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
                params={"key": self._api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise _ProviderError(f"gemini: {exc}") from exc
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def default_providers(config: LLMConfig) -> list[Provider]:
    """[primary, fallback], ordered by config.primary (S05 PROVIDERS AND FALLBACK)."""
    groq_models = [config.groq_model, *config.groq_fallback_models]  # S26: one quota per model
    groq = [
        GroqProvider(config.groq_api_key, model, config.groq_reasoning_effort)
        for model in groq_models
    ]
    gemini = GeminiProvider(config.gemini_api_key, config.gemini_model)
    return [*groq, gemini] if config.primary == "groq" else [gemini, *groq]


# --- run_turn ---------------------------------------------------------------------------------


def run_turn(
    *,
    session: SessionState,
    specs: dict[str, ServiceSpec],
    text: str | None,
    lat: float | None,
    lng: float | None,
    recent_messages: Sequence[Message] = (),
    providers: Sequence[Provider] | None = None,
) -> TurnResult:
    """S05 run_turn. Raises TurnEngineUnavailable if both providers fail (S04 -> 503)."""
    if not text or not text.strip():
        # GPS-only turn (S01 D-A8): GPS carries no field/service intent by itself (S03) --
        # skip the LLM call entirely (D-S05-1).
        return TurnResult(service_id=session.service_id, fields={}, confirmed=False)

    prompt = _build_prompt(session, specs, text, lat, lng, recent_messages)

    started = time.monotonic()
    for provider in providers if providers is not None else default_providers(get_llm_config()):
        if time.monotonic() - started >= TURN_DEADLINE_SECONDS:
            logger.warning("turn deadline reached, not trying %s", provider.name)
            break  # S26 D-S26-4: bounded wait -> the existing 503
        try:
            raw = provider.complete(prompt)
            parsed = _RawTurnOutput.model_validate_json(raw)
        except (_ProviderError, ValueError, ValidationError) as exc:
            # Never the prompt or citizen text; the reason is what made the 503s undiagnosable (G-S16-1).
            logger.warning("LLM provider %s failed: %s", provider.name, str(exc)[:200])
            continue  # move to the next provider (S05 STRUCTURAL VALIDATION / PROVIDERS)
        if parsed.service_id is not None and parsed.service_id not in specs:
            logger.warning("LLM provider %s returned unknown service_id", provider.name)
            continue  # hallucinated service id -- structural failure, not a valid answer
        confirmed = parsed.confirmed and session.awaiting_confirmation  # D-S05-3
        return TurnResult(
            service_id=parsed.service_id,
            fields=parsed.fields,
            confirmed=confirmed,
            ack=parsed.ack if isinstance(parsed.ack, str) else None,
        )

    raise TurnEngineUnavailable("both LLM providers failed")
