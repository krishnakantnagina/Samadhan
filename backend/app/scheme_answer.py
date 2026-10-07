"""S37 -- explain a scheme from its official CM Helpline page (RAG answer step).

`schemes.py` finds WHICH scheme; this module says WHAT it is, using only the text of that scheme's official page
(`specs/registry/scheme_details.json`, built by scripts/build_scheme_details.py from cmhelpline.mp.gov.in).

Two ways to write the explanation, both grounded in that text:
  - fixed template (default): objective, who is eligible, the benefit, where to apply, fee, official links, each cut to a readable length;
  - Gemini plain-Hindi summary (SCHEME_EXPLAIN=1): the model may only restate the page. The answer is rejected, and the fixed template used instead,
    if it contains a number that is not in the page or the question, a link, or is too long, and on any provider failure.
Whatever is written, the official page link and the "this may be wrong, check the official site" note always follow.

When the question fits several schemes about equally ("छात्रवृत्ति"), no scheme is explained: the names are listed and the citizen is asked which one.
Off unless SCHEME_LOOKUP=1 (the same switch as S36).

Either of us can change this file. If you do, update docs/specs/S37-scheme-answers.md.
"""

import json
import logging
import os
import re
import time
from collections.abc import Callable

import httpx

from app import schemes
from app.info_reply import INFO_DISCLAIMER_HI, build_scheme_reply

logger = logging.getLogger(__name__)

EXPLAIN_TIMEOUT_SECONDS = 7.0
EXPLAIN_DEADLINE_SECONDS = 10.0
MAX_ANSWER_CHARS = 900
SOURCE_CHARS = 4500  # what the model gets to read (the longest official pages are longer)
CONFIDENT_SIMILARITY = 0.68  # the best scheme must be at least this close to the question ...
CONFIDENT_GAP = (
    0.03  # ... and clearly ahead of the second one, else we list the names and ask which
)

ASK_WHICH_HI = "इनमें से किस योजना के बारे में जानना है? उसका नाम बताइए।"
# (key in the details file, label shown to the citizen, characters kept in the fixed template)
SECTIONS = (
    ("objective", "उद्देश्य", 260),
    ("eligibility", "कौन पात्र है", 520),
    ("amount", "लाभ", 300),
    ("where", "आवेदन कहाँ करें", 260),
    ("process", "आवेदन प्रक्रिया और अपात्रता", 340),
    ("fee", "शुल्क", 80),
    ("documents", "ज़रूरी दस्तावेज़", 260),
)
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

PROMPT = """\
You explain ONE Madhya Pradesh government scheme to a villager who asked a question. Use ONLY the official page text below. Output ONLY JSON:
{"answer": "<plain, simple Hindi in Devanagari, at most 6 short sentences>"}
Rules:
- Say what the scheme gives, who can get it, and how or where to apply, if the page says so. Answer the citizen's own question first.
- Every number, amount, age, date or limit you write must appear in the page text. Never add a fact, number, link, phone number or office that is not in it.
- If the page does not say what they asked, say that the page does not say, and do not guess.
- No greetings, no promises, no links, no advice beyond the page.
"""


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind("।"), cut.rfind(". "))
    return (cut[: stop + 1] if stop > limit * 0.5 else cut.rsplit(" ", 1)[0]) + " …"


def template(scheme: schemes.Scheme, detail: dict) -> str:
    """The explanation as fixed text: headings we wrote, values copied from the official page."""
    lines = [f"{scheme.name} ({scheme.department})"]
    for key, label, limit in SECTIONS:
        if detail.get(key):
            lines.append(f"{label}: {_clip(detail[key], limit)}")
    return chr(10).join(lines)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text.translate(_DIGITS))}


def source_text(detail: dict) -> str:
    parts = [f"{label}: {detail[key]}" for key, label, _ in SECTIONS if detail.get(key)]
    for key, label in (
        ("groups", "लाभार्थी वर्ग"),
        ("payment", "भुगतान"),
        ("time_limit", "समय सीमा"),
        ("since", "प्रारंभ"),
    ):
        if detail.get(key):
            parts.append(f"{label}: {detail[key]}")
    return chr(10).join(parts)[:SOURCE_CHARS]


def grounded(answer: str, source: str, question: str) -> bool:
    """True if the model's answer is safe to show: short, no link, and no number the page (or the citizen) did not give."""
    if (
        not answer
        or len(answer) > MAX_ANSWER_CHARS
        or re.search(r"https?://|www\.|\.gov\.in|@", answer, re.IGNORECASE)
    ):
        return False
    return _numbers(answer) <= _numbers(source) | _numbers(question)


def explain(
    question: str, detail: dict, *, post: Callable[..., httpx.Response] = httpx.post
) -> str | None:
    """Gemini's plain-Hindi summary of the page, or None (off, no key, failure, or not grounded)."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or os.environ.get("SCHEME_EXPLAIN", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return None
    source = source_text(detail)
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"{PROMPT}{chr(10)}Citizen's question: {question[:400]}{chr(10)}{chr(10)}Official page text:{chr(10)}{source}"
                    }
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    started = time.monotonic()
    for model in schemes._models():
        if time.monotonic() - started >= EXPLAIN_DEADLINE_SECONDS:
            break
        try:
            r = post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json=body,
                timeout=EXPLAIN_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            answer = str(
                json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])["answer"]
            ).strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            logger.warning("scheme explain with %s failed (%s)", model, type(exc).__name__)
            continue
        if grounded(answer, source, question):
            return answer
        logger.warning("scheme explain with %s rejected: not grounded in the official page", model)
        return None  # a model that invents numbers once is not asked again
    return None


def links_block(scheme: schemes.Scheme, detail: dict) -> str:
    lines = []
    if detail.get("apply_url"):
        lines.append(f"ऑनलाइन आवेदन: {detail['apply_url']}")
    lines.append(f"पूरी जानकारी (आधिकारिक पेज): {scheme.url}")
    return chr(10).join(lines)


def reply(question: str, *, allow_llm: bool = True) -> str | None:
    """The chatbot's answer to a scheme question, or None when nothing matched (the caller keeps the normal information reply).
    `allow_llm=False` (the request is already slow) skips the optional Gemini summary and uses the fixed template."""
    ranked = schemes.ranked(question)
    if ranked is None:  # retrieval could not run (no key / index): names only, from the word match
        found = schemes.find_words(question)
        return build_scheme_reply(found) if found else None
    if not ranked or ranked[0][0] < schemes.MIN_SIMILARITY:
        return None
    best_sim, best = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    detail = schemes.detail_for(best)
    if detail and best_sim >= CONFIDENT_SIMILARITY and best_sim - second >= CONFIDENT_GAP:
        summary = explain(question, detail) if allow_llm else None
        body = (
            f"{best.name} ({best.department}){chr(10)}{summary}"
            if summary
            else template(best, detail)
        )
        return chr(10).join([body, links_block(best, detail), INFO_DISCLAIMER_HI])
    close = [
        sch
        for sim, sch in ranked[: schemes.MAX_RESULTS]
        if sim >= schemes.MIN_SIMILARITY and sim >= best_sim - schemes.MARGIN
    ]
    return build_scheme_reply(close, ask=ASK_WHICH_HI)
