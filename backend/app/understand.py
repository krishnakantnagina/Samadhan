"""S35 -- understand first. Gemini translates the citizen's first message into standard Hindi and English and says WHAT it is, before anything else runs.

    complaint          a problem with a government service, office or facility that needs action        -> normal flow: Jev finds the department, then it is routed
    question           asks general information                                                          -> the existing information reply (fixed text, validated .gov.in link)
    document_request   wants a certificate, licence, scheme or "how do I apply"                          -> the same information reply
    greeting           hello, thanks, chit-chat                                                          -> the existing out-of-context reply
    unclear            cannot tell what the problem is ("I have a problem")                              -> ask the citizen to tell the complaint again (twice at most)

Why: dialect words ("मारसाब" = master sahab, a teacher) confuse the department router and the turn engine; a standard-Hindi/English translation next to the
original makes both far more accurate, and a vague first message is cheaper to clarify once than to route wrongly.

Switch: UNDERSTAND_FIRST=1 (off by default) and GEMINI_API_KEY. Models: UNDERSTAND_MODELS (comma list, tried in order) else GEMINI_MODEL.
Runs only when a conversation starts (no service chosen yet), never on answers like "हाँ" or a village name. Fail-open: any error returns None and the
existing pipeline runs unchanged. Privacy: the message goes to Gemini like it already does in the turn engine; nothing about it is logged here.

Either of us can change this file. If you do, update docs/specs/S35-understand-first.md.
"""

import json
import logging
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

KINDS = ("complaint", "question", "document_request", "greeting", "unclear")
META_KEY = "_understand"
MIN_CONFIDENCE = 0.5  # below this a "complaint" is treated as unclear
MAX_UNCLEAR_ASKS = 2  # after this many "please tell your complaint again" the normal pipeline takes the message instead of looping
TIMEOUT_SECONDS = 6.0
DEADLINE_SECONDS = 9.0  # stop starting new models after this long: the citizen is waiting (the free Gemini tiers answer 429/503 often, each model has its own quota)
FALLBACK_MODELS = ("gemini-3-flash-preview", "gemini-3.1-flash-lite")  # live-checked 5 Oct 2026; override with UNDERSTAND_MODELS
ASK_AGAIN_HI = "मैं ठीक से समझ नहीं पाया। कृपया अपनी शिकायत फिर से बताइए: क्या समस्या है, और कहाँ?"

PROMPT = """\
You read ONE message a citizen sent a government grievance chatbot in Madhya Pradesh, India. It may be Hindi, Hinglish, English or a dialect
(Bundeli, Malvi, Nimadi, Bagheli, Bhili). Dialect examples: "मारसाब"/"मास्टर साब" = the school teacher (master sahab), "बिजली नी आ री" = no electricity.
Translate it and say what it is. Output ONLY a JSON object, no prose, no markdown:
{"language": "<hindi|hinglish|english|bundeli|malvi|nimadi|bagheli|bhili|other>", "hindi": "<the message in plain standard Hindi, Devanagari>",
 "english": "<the message in plain English>", "kind": "complaint|question|document_request|greeting|unclear", "confidence": <0..1>}
kind:
- "complaint": reports a problem with a government service, office, scheme or facility that needs action (no water, teacher absent, pension not received).
- "question": asks for general information (a rule, a date, an office address, how something works) and reports no problem.
- "document_request": wants a certificate, licence, card, scheme benefit or document, or asks how to apply for one (caste certificate, ration card).
- "greeting": hello, thanks, a joke, chit-chat, anything not about government.
- "unclear": you cannot tell what the problem or request is (too vague, e.g. "I have a problem", or unreadable).
Use the earlier turns, if any, to read this message (the citizen may be repeating their complaint after we asked). Keep the translation faithful: add nothing the
citizen did not say. confidence = how sure you are about "kind".
"""


@dataclass(frozen=True)
class Understanding:
    kind: str
    confidence: float
    hindi: str
    english: str
    language: str

    @property
    def is_complaint(self) -> bool:
        return self.kind == "complaint" and self.confidence >= MIN_CONFIDENCE

    @property
    def is_unclear(self) -> bool:
        return self.kind == "unclear" or (self.kind == "complaint" and self.confidence < MIN_CONFIDENCE)

    def as_meta(self) -> dict[str, Any]:
        return {"kind": self.kind, "confidence": round(self.confidence, 2), "language": self.language, "hindi": self.hindi, "english": self.english}


def enabled() -> bool:
    on = os.environ.get("UNDERSTAND_FIRST", "").strip().lower() in ("1", "true", "yes", "on")
    return on and bool(os.environ.get("GEMINI_API_KEY", "").strip())


def _models() -> list[str]:
    raw = os.environ.get("UNDERSTAND_MODELS", "").strip()
    models = [m.strip() for m in raw.split(",") if m.strip()]
    if models:
        return models
    first = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.6-flash"
    return [first, *[m for m in FALLBACK_MODELS if m != first]]


def engine_text(original: str, u: Understanding | None) -> str:
    """What the turn engine and Jev read: the citizen's own words, then the plain-language translation, so dialect words stop being a guess."""
    if u is None or not (u.hindi or u.english):
        return original
    parts = [p for p in (f"मानक हिंदी: {u.hindi}" if u.hindi else "", f"English: {u.english}" if u.english else "") if p]
    return f"{original}\n({'; '.join(parts)})"


def _turns(recent: Sequence[Any]) -> str:
    lines = [f"{getattr(m, 'role', 'citizen')}: {getattr(m, 'text', '')}" for m in (recent or [])[-4:] if getattr(m, "text", "")]
    return "\n".join(lines) if lines else "(none)"


def _parse(raw: str) -> Understanding | None:
    try:
        data = json.loads(raw)
        kind = str(data["kind"]).strip().lower()
        if kind not in KINDS:
            return None
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        return Understanding(kind, confidence, str(data.get("hindi") or "").strip()[:400], str(data.get("english") or "").strip()[:400],
                             str(data.get("language") or "").strip().lower()[:20])
    except (ValueError, KeyError, TypeError):
        return None


def understand(text: str, recent: Sequence[Any] = (), *, post: Callable[..., httpx.Response] = httpx.post) -> Understanding | None:
    """Translate and classify one message. None = skipped or failed (the caller carries on exactly as before)."""
    if not enabled() or not text or not text.strip():
        return None
    prompt = f"{PROMPT}\nEarlier turns:\n{_turns(recent)}\n\nCitizen's message:\n{text.strip()}\n"
    key = os.environ["GEMINI_API_KEY"].strip()
    started = time.monotonic()
    for model in _models():
        if time.monotonic() - started >= DEADLINE_SECONDS:
            logger.warning("understand: deadline reached, not trying %s", model)
            break
        try:
            response = post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},  # a header, never the URL: httpx puts the URL in its error text
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}},
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            parsed = _parse(response.json()["candidates"][0]["content"]["parts"][0]["text"])
        except httpx.HTTPStatusError as exc:
            logger.warning("understand: %s HTTP %s", model, exc.response.status_code)
            continue
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:  # no message text: it can carry the URL
            logger.warning("understand: %s failed (%s)", model, type(exc).__name__)
            continue
        if parsed is not None:
            return parsed
        logger.warning("understand: %s returned an unusable answer", model)
    return None
