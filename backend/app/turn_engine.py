"""S05 — Turn Engine (T12). Spec: docs/specs/S05-turn-engine.md.

One LLM call per citizen turn: Groq primary, Gemini Flash fallback, one attempt each. Output is
untrusted -- S07 (Validator) checks every field against the service spec before anything is stored
or shown (PROJECT.md section 4, S01 section 2).

Either of us can change this file. If you do, update docs/specs/S05-turn-engine.md and tell the
other.
"""

import json
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import LLMConfig, get_llm_config
from app.service_spec import EnumField, IntegerField, LocationField, ServiceSpec, StringField

logger = logging.getLogger(__name__)

PROVIDER_TIMEOUT_SECONDS = 6.0  # S04 section 5 / S05 provider table
TURN_DEADLINE_SECONDS = 14.0  # S26 D-S26-4: stop starting new providers past this
HUMAN_EVALUATION_SERVICE = "human_evaluation"  # S31: the Human Evaluation queue (specs/human_evaluation.yaml); was the S28 "general" triage service
INTENTS = ("complaint", "information", "out_of_context", "status")
FULL_BLOCK_LIMIT = 8  # more services than this and the prompt lists full field details only for the few that matter (see _services_text)
FULL_BLOCKS_WHEN_MANY = 3  # the active service plus the best keyword matches; every other service gets a one-line entry

SYSTEM_INSTRUCTIONS = """\
You extract structured data from ONE message a citizen sent a government grievance chatbot.
Output ONLY a JSON object, no prose, no markdown:
{"intent": "complaint|information|out_of_context|status", "service_id": "<listed id or null>", \
"confidence": <0..1 or null>, "candidates": ["<service_id>", ...], "fields": {"<field_name>": "<value>"}, \
"confirmed": true/false, "urgent": true/false, "ack": "<see rules>" or null, "info_url": "<see rules>" or null}

Rules:
- intent: "complaint" = reports a problem to be registered. "information" = asks how to get or apply for a
  government document, certificate, scheme or service (a question, not a problem). "out_of_context" =
  greeting, chit-chat, joke, general knowledge, anything else. "status" = asks about the progress or status
  of a complaint they already filed (leave fields empty). A short reply that answers the bot's last
  question (yes/no, a place name, a number, a choice) belongs to the current complaint: intent "complaint",
  keep the active service.
- service_id: only for a complaint. The best specific service; "human_evaluation" ONLY if none of the others fits;
  null if not a complaint, or if you cannot decide between specific services (then fill candidates).
  Never invent a service.
- confidence: how sure you are about service_id. candidates: up to 3 specific ids (never "human_evaluation") you are
  torn between, else [].
- fields: only the matched service's field names, only what the citizen gave or changed THIS turn, never a
  value outside the allowed values. Empty unless intent is "complaint".
- Choose enum values by WHAT WENT WRONG, not by a scheme, fund or office that is only named as context or as where the money came from.
  "MGNREGA ka paisa aaya par sadak nahi bani" is a road/construction problem (the road was not built), not an MGNREGA wages problem;
  "pension ke paise se hand pump nahi laga" is a water-facility problem. Use a scheme's own value only when the scheme's benefit is what is missing.
- Corrections: if the citizen corrects something they said earlier ("नहीं, ... है", "मतलब", "I meant", "not X, it is Y", or says what the problem
  really is), put the corrected value in fields for that field THIS turn, even though it was already filled. Never repeat the old value
  after a correction. If the correction fits no allowed value of that field, use the closest "other" value if there is one.
- confirmed: true only if "awaiting confirmation" is true AND the citizen plainly agrees, with no correction.
- location: only a specific place NAME (ward, colony, locality, village name). Generic words (village/गाँव,
  house/घर, hand pump/हैंडपंप, tap/नल, tank/टंकी, "our village"/"हमाए गाँव") name no place: omit the field.
  A yes/no ("हाँ", "नहीं") is never a location.
- If the previous bot turn asked "क्या आप ... बता रहे हैं?": agreement means that service with confidence 1;
  "no" means service_id null and candidates = the other specific services that might fit.
- urgent: true only for immediate danger to life or safety (fire, medical emergency, violence, crime in progress).
- info_url: only for intent "information": ONE https homepage of the most relevant government website, a
  ".gov.in" domain, no path, never a guessed page; else null.
- ack: only when this turn gave NEW information: one short warm sentence in Devanagari Hindi (max 12 words)
  repeating the citizen's own words (symptom, how long). Not a question, not a promise, no fact about
  offices, dates or status ("हम जाँच कर रहे हैं" is a promise: never). Otherwise null.
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
    intent: Literal["complaint", "information", "out_of_context", "status"] = (
        "complaint"  # S28 4.3a, S29
    )
    confidence: float | None = (
        None  # S28 4.3: LLM-reported, uncalibrated, only ever compared to thresholds
    )
    candidates: list[str] = Field(default_factory=list)  # S28: specific services it is torn between
    urgent: bool = False  # S28 Q4: immediate danger -> fixed neutral guidance line
    info_url: str | None = None  # S28 4.6: untrusted, validated in app/info_reply.py


class _RawTurnOutput(BaseModel):
    """Structural shape only (S05 STRUCTURAL VALIDATION). Extra keys ignored (D-S05-5)."""

    model_config = ConfigDict(extra="ignore")

    service_id: str | None = None
    fields: dict[str, Any] = {}
    confirmed: bool = False
    ack: Any = None  # S25: any type accepted here, the validator decides
    intent: Any = "complaint"  # S28: normalised in run_turn, anything unknown means complaint
    confidence: Any = None
    candidates: Any = None
    urgent: Any = False
    info_url: Any = None


class Provider(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...  # raw response text; raises _ProviderError


class _ProviderError(RuntimeError):
    """A provider call failed (timeout, connection error, non-2xx)."""


# --- Prompt construction (S05 section BEHAVIOR 2-3) ---------------------------------------


def _field_vocabulary(field: EnumField | IntegerField | StringField | LocationField) -> str:
    line = f"  - {field.name} ({field.type}, {'required' if field.required else 'optional'})"
    if isinstance(field, EnumField):
        values = ", ".join(f'{v.value} ("{v.en}")' if v.en and v.en != v.value else v.value for v in field.values)  # the meaning next to the id
        line += f": allowed values = [{values}], answer with the id only"
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


def _service_line(spec: ServiceSpec) -> str:
    """One compact line: enough for the model to pick the service, without its field details (keeps the prompt small when there are dozens of services)."""
    return f'- service_id "{spec.service}" ({spec.label.en})'


_STOP = frozenset(
    ["nahi", "nahin", "mil", "raha", "rahi", "rahe", "hai", "hain", "mere", "mera", "meri", "gaon", "gaaon", "gaanv", "aur", "koi", "bahut", "kar", "kiya", "kuch", "bhi", "the", "and", "not", "for", "with", "from", "that", "this", "have", "has", "hum", "aap", "hamare", "hamara", "apna", "ke", "ka", "ki", "me", "mein", "se", "ko", "par", "नहीं", "नही", "रहा", "रही", "रहे", "है", "हैं", "में", "के", "की", "का", "को", "से", "पर", "और", "हमारे", "हमारा", "हमारी", "मेरे", "मेरा", "मेरी", "गाँव", "गांव", "कर", "कुछ", "भी", "तो", "यह", "वह", "हो", "था", "थी", "बहुत", "आ", "रहा"]
)


def _tokens(text: str) -> set[str]:
    # the explicit Devanagari range matters: \w alone splits Hindi words at every vowel sign
    return {t for t in re.findall(r"[\wऀ-ॿ]+", text.lower()) if len(t) >= 3 and t not in _STOP}


def _services_text(session: SessionState, specs: dict[str, ServiceSpec], text: str) -> str:
    """The "Listed services" block. With a handful of services every one is listed in full (unchanged behaviour). With many (one spec per department),
    a prompt with every field list is too large for the model providers (HTTP 413), so only the active service and the best keyword matches for what the citizen said
    get full field details; the rest are one-line entries. If the model picks a one-line service, its fields are listed in full on the next turn (it is then active)."""
    if len(specs) <= FULL_BLOCK_LIMIT:
        return chr(10).join(_service_block(spec) for spec in specs.values())
    words = _tokens(text)
    vocab = {sp.service: _tokens(" ".join([sp.label.en, sp.label.hi, *sp.recognise])) for sp in specs.values()}
    df = {w: sum(1 for toks in vocab.values() if w in toks) for w in set().union(*vocab.values())}
    # a shared word counts for more the fewer services use it (a word used by 15 services, however common in speech, adds almost nothing)
    score = {svc: sum(1.0 / df[w] for w in words & toks) for svc, toks in vocab.items()}
    ranked = sorted(specs.values(), key=lambda sp: score[sp.service], reverse=True)
    full = {session.service_id} if session.service_id in specs else set()
    for spec in ranked:
        if len(full) >= FULL_BLOCKS_WHEN_MANY:
            break
        if score[spec.service] > 0:
            full.add(spec.service)
    return chr(10).join(_service_block(spec) if spec.service in full else _service_line(spec) for spec in specs.values())


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
    services = _services_text(session, specs, text)
    gps_note = "yes" if lat is not None and lng is not None else "no"
    return f"""\
{SYSTEM_INSTRUCTIONS}
Listed services:
{services}

Session state:
- active service_id so far: {session.service_id or "none yet"}
- already collected fields: {json.dumps({k: v for k, v in session.collected_fields.items() if not k.startswith("_")}, ensure_ascii=False)}
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

    def __init__(self, api_key: str, model: str, name: str = "gemini") -> None:
        self._api_key = api_key
        self._model = model
        self.name = name

    def complete(self, prompt: str) -> str:
        try:
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
                headers={"x-goog-api-key": self._api_key},  # a header, never the URL: httpx puts the URL in its error text and these errors are logged
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _ProviderError(f"{self.name}: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:  # the message is left out on purpose: it carries the full URL
            raise _ProviderError(f"{self.name}: {type(exc).__name__}") from exc
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


def _clean_confidence(value: Any) -> float | None:
    """S28: a number in 0..1, else None. bool is an int subclass, reject it first."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if 0.0 <= value <= 1.0 else None


def _clean_candidates(value: Any, specs: dict[str, ServiceSpec]) -> list[str]:
    """S28: only loaded, specific (not general) service ids, no duplicates, at most 3."""
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        if isinstance(item, str) and item in specs and item != HUMAN_EVALUATION_SERVICE and item not in seen:
            seen.append(item)
    return seen[:3]


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
            intent=parsed.intent if parsed.intent in INTENTS else "complaint",
            confidence=_clean_confidence(parsed.confidence),
            candidates=_clean_candidates(parsed.candidates, specs),
            urgent=parsed.urgent is True,
            info_url=parsed.info_url if isinstance(parsed.info_url, str) else None,
        )

    raise TurnEngineUnavailable("both LLM providers failed")
