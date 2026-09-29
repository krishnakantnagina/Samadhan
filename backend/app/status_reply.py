"""S29 -- complaint status inside the chat (typed or spoken).

`extract_complaint_id` is a deterministic parser (no LLM): it finds a complaint number in a short message, in
the forms a citizen actually types or Sarvam writes for speech ("SMD-0022", "एसएमडी 0022", "S M D 0 0 2 2",
"एस एम डी शून्य शून्य दो दो", Devanagari digits). The reply text is fixed and shows only what the public status
endpoint already exposes (status, department, update time; S11 RULES 2).

Either of us can change this file. If you do, update docs/specs/S29-status-in-chat.md.
"""

import re
from datetime import datetime
from typing import Any

MAX_WORDS_WITH_PREFIX = (
    14  # S29 D-S29-4: a long complaint that mentions a number is not a status question
)
MAX_DIGITS = 8

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PUNCTUATION = str.maketrans({c: " " for c in ",.।!?;:()-_/\\'\"“”‘’"})
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b‌‍﻿"))

_DIGIT_WORDS = {
    "शून्य": "0", "ज़ीरो": "0", "जीरो": "0", "zero": "0", "एक": "1", "one": "1", "दो": "2", "two": "2",
    "तीन": "3", "three": "3", "चार": "4", "four": "4", "पाँच": "5", "पांच": "5", "five": "5",
    "छह": "6", "छः": "6", "छे": "6", "छ": "6", "six": "6", "सात": "7", "seven": "7", "आठ": "8",
    "eight": "8", "नौ": "9", "nine": "9",
}  # fmt: skip
_PREFIX_ONE = {"smd", "एसएमडी", "एसमडी", "एसेमडी", "एसएम्डी"}
_PREFIX_LETTERS = (("s", "m", "d"), ("एस", "एम", "डी"), ("एस", "एम", "डि"))
_GLUED = re.compile(r"^smd(\d+)$")

STATUS_LABELS_HI = {
    "new": "नई (दर्ज हो चुकी है)",
    "in_progress": "प्रक्रिया में है",
    "resolved": "हल हो चुकी है",
    "needs_review": "समीक्षा के लिए भेजी गई है",
}
NEED_ID_REPLY_HI = (
    "अपनी शिकायत की स्थिति बताने के लिए मुझे शिकायत क्रमांक चाहिए (जैसे SMD-0022)। "
    "कृपया क्रमांक बोलकर या लिखकर बताइए। आप ऊपर दिए 'अपनी शिकायत की स्थिति जानें' लिंक से भी देख सकते हैं।"
)


def _tokens(text: str) -> list[str]:
    cleaned = (
        text.translate(_ZERO_WIDTH).lower().translate(_DEVANAGARI_DIGITS).translate(_PUNCTUATION)
    )
    return cleaned.split()


def _digits_after(tokens: list[str], start: int) -> str:
    """Join the digits / digit words that follow the prefix; the first other word ends the number."""
    digits = ""
    for token in tokens[start:]:
        if token.isdigit():
            digits += token
        elif token in _DIGIT_WORDS:
            digits += _DIGIT_WORDS[token]
        else:
            break
    return digits[:MAX_DIGITS]


def _format(digits: str) -> str | None:
    return f"SMD-{int(digits):04d}" if digits else None


def extract_complaint_id(text: str | None, *, allow_bare: bool = False) -> str | None:
    """`SMD-0022`-style id from a short message, or None. With `allow_bare` (the LLM already said this is a
    status question) a plain number such as "मेरी शिकायत 22 की स्थिति" is accepted too."""
    if not text:
        return None
    tokens = _tokens(text)
    if not tokens:
        return None
    if len(tokens) <= MAX_WORDS_WITH_PREFIX:
        for i, token in enumerate(tokens):
            glued = _GLUED.match(token)
            if glued:
                return _format(glued.group(1)[:MAX_DIGITS])
            if token in _PREFIX_ONE:
                found = _format(_digits_after(tokens, i + 1))
                if found:
                    return found
            for letters in _PREFIX_LETTERS:
                if tuple(tokens[i : i + 3]) == letters:
                    found = _format(_digits_after(tokens, i + 3))
                    if found:
                        return found
    if allow_bare:
        for i, token in enumerate(tokens):
            if token.isdigit() or token in _DIGIT_WORDS:
                found = _format(_digits_after(tokens, i))
                if found:
                    return found
    return None


def _date_of(updated_at: Any) -> str:
    try:
        return datetime.fromisoformat(str(updated_at)).strftime("%d-%m-%Y")
    except ValueError:
        return "-"


def build_status_reply(complaint_id: str, row: dict[str, Any] | None) -> str:
    if row is None:
        return f"मुझे शिकायत क्रमांक {complaint_id} नहीं मिला। कृपया क्रमांक दोबारा जाँचें।"
    label = STATUS_LABELS_HI.get(row.get("status"), str(row.get("status")))
    return (
        f"आपकी शिकायत {complaint_id} की स्थिति: {label}।\n"
        f"विभाग: {row.get('department')}।\n"
        f"आखिरी अपडेट: {_date_of(row.get('updated_at'))}।"
    )
