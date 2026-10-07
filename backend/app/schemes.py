"""Scheme lookup (RAG): match an information question to government schemes and give the official CM Helpline link.

Data: `specs/registry/schemes.csv` (362 schemes, scraped from cmhelpline.mp.gov.in on 2026-10-01; names and links only,
no eligibility or amounts). Retrieval: every scheme is embedded once with Gemini (`scripts/build_scheme_index.py` writes
`schemes_index.json`); at question time only the question is embedded and the closest schemes by cosine similarity win, so
Hinglish, English and dialect wording find Hindi scheme names. If the embedding call fails or the index is stale, it falls
back to plain word overlap. Nothing is generated: the reply only ever lists rows of the file. Off unless SCHEME_LOOKUP=1.

Either of us can change this file. If you do, update docs/specs/S36-scheme-lookup.md.
"""

import csv
import hashlib
import json
import logging
import math
import os
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

SCHEMES_FILE = Path(__file__).resolve().parents[2] / "specs" / "registry" / "schemes.csv"
INDEX_FILE = SCHEMES_FILE.with_name("schemes_index.json")
DETAILS_FILE = SCHEMES_FILE.with_name("scheme_details.json")  # official page text per scheme (S37), built by scripts/build_scheme_details.py
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
RERANK_TIMEOUT_SECONDS = 6.0
RERANK_DEADLINE_SECONDS = 9.0
EMBED_TIMEOUT_SECONDS = 4.0  # the citizen is waiting: on a slow answer use the word match instead
MIN_SIMILARITY = (
    0.65  # cosine; calibrated on sample questions (off-topic ones score 0.55-0.63), see S36
)
RERANK_CANDIDATES = 6
MARGIN = 0.06  # keep only results within this of the best one
MAX_RESULTS = 3
MIN_SCORE = 2.0  # one shared common word is never enough
GOV_SUFFIX = ".gov.in"

# Words that appear in many scheme names or in every question: they say nothing about WHICH scheme.
_STOP = frozenset(
    [
        "योजना",
        "योजनाएं",
        "योजनाएँ",
        "योजनाओं",
        "का",
        "की",
        "के",
        "को",
        "में",
        "से",
        "और",
        "या",
        "एवं",
        "एंव",
        "हेतु",
        "लिए",
        "है",
        "हैं",
        "हो",
        "था",
        "थी",
        "कि",
        "क्या",
        "कैसे",
        "कौन",
        "कौनसी",
        "कौन-सी",
        "मुझे",
        "मेरा",
        "मेरी",
        "मेरे",
        "हमें",
        "हमारा",
        "बारे",
        "जानकारी",
        "चाहिए",
        "चाहता",
        "चाहती",
        "बताइए",
        "बताओ",
        "बताइये",
        "मिलेगा",
        "मिलता",
        "मिलती",
        "कैसे",
        "लेना",
        "लें",
        "आवेदन",
        "अनुदान",
        "सहायता",
        "मध्य",
        "प्रदेश",
        "मप्र",
        "शासन",
        "सरकार",
        "विभाग",
        "वर्ग",
        "कक्षा",
        "छात्र",
        "छात्रा",
    ]
)
_WORD = re.compile(r"[\u0900-\u097F]+|[a-z0-9]+")
_MATRA_FIX = str.maketrans(
    {"ँ": "ं", "़": "", "‍": None, "‌": None}
)  # chandrabindu = anusvara; drop nukta and joiners


@dataclass(frozen=True)
class Scheme:
    name: str
    department: str
    url: str

    @property
    def scheme_id(self) -> str | None:
        m = re.search(r"Schemeid=(\d+)", self.url)
        return m.group(1) if m else None


@lru_cache(maxsize=1)
def _details() -> dict[str, dict]:
    try:
        return json.loads(DETAILS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def detail_for(scheme: Scheme) -> dict | None:
    """What the official page says about this scheme (objective, eligibility, amount, where to apply ...), or None."""
    return _details().get(scheme.scheme_id or "")


def enabled() -> bool:
    return os.environ.get("SCHEME_LOOKUP", "").strip().lower() in ("1", "true", "yes", "on")


def _tokens(text: str) -> set[str]:
    text = (
        unicodedata.normalize("NFC", text)
        .lower()
        .replace("200d", "")
        .replace("200c", "")
        .translate(_MATRA_FIX)
    )
    return {w for w in _WORD.findall(text) if w not in _STOP and len(w) > 1}


@lru_cache(maxsize=1)
def _load(path: str = str(SCHEMES_FILE)) -> tuple[tuple[Scheme, frozenset[str]], ...]:
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            url = r["url"].strip()
            parts = urlsplit(url)
            if parts.scheme != "https" or not (parts.hostname or "").endswith(GOV_SUFFIX):
                continue  # only ever link a real *.gov.in host
            scheme = Scheme(r["scheme"].strip(), r["department"].strip(), url)
            rows.append((scheme, frozenset(_tokens(scheme.name))))
    return tuple(rows)


def find_words(question: str, *, limit: int = MAX_RESULTS, path: str | None = None) -> list[Scheme]:
    """Schemes whose name shares enough words with `question`, best first. Never raises."""
    try:
        words = _tokens(question or "")
        if not words:
            return []
        scored = []
        for scheme, name_words in _load(path) if path else _load():
            shared = words & name_words
            if not shared:
                continue
            # a word that is rare across scheme names is worth more; a scheme fully covered by the question gets a bonus
            score = sum(1.0 + min(len(w), 8) / 8 for w in shared) + (
                1.0 if name_words <= words else 0.0
            )
            scored.append((score, scheme))
        scored.sort(key=lambda s: (-s[0], s[1].name))
        return [s for score, s in scored if score >= MIN_SCORE][:limit]
    except Exception:  # noqa: BLE001 -- a missing or broken file must never block an answer
        return []


def doc_text(scheme: Scheme) -> str:
    """What is embedded for a scheme: name and department, plus the start of its objective and who it is for, so a question about the PURPOSE finds it."""
    detail = detail_for(scheme) or {}
    extra = " ".join(part for part in (detail.get("objective", "")[:300], detail.get("kind", ""), detail.get("groups", "")) if part)
    return f"{scheme.name} ({scheme.department}) {extra}".strip()


def normalise(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def csv_hash(path: Path = SCHEMES_FILE) -> str:
    """Fingerprint of everything the index was built from (the scheme list and the details file): change either and the index is stale."""
    digest = hashlib.sha256(path.read_bytes())
    if DETAILS_FILE.exists():
        digest.update(DETAILS_FILE.read_bytes())
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _index() -> list[list[float]] | None:
    """The stored scheme vectors, or None if missing, built from another model, or older than schemes.csv."""
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        vectors = data["vectors"]
        if (
            data["model"] != EMBED_MODEL
            or data["dim"] != EMBED_DIM
            or data["csv_sha256"] != csv_hash()
            or len(vectors) != len(_load())
        ):
            logger.warning(
                "schemes: index is stale, using the word match (run scripts/build_scheme_index.py)"
            )
            return None
        return vectors
    except (OSError, ValueError, KeyError, TypeError):
        return None


def embed_query(
    text: str, *, post: Callable[..., httpx.Response] = httpx.post
) -> list[float] | None:
    """One Gemini embedding for the question; None on any failure."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    try:
        r = post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:embedContent",
            headers={
                "x-goog-api-key": key
            },  # a header, never the URL: httpx puts the URL in its error text
            json={
                "content": {"parts": [{"text": text[:1000]}]},
                "taskType": "RETRIEVAL_QUERY",
                "outputDimensionality": EMBED_DIM,
            },
            timeout=EMBED_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        values = r.json()["embedding"]["values"]
        return normalise(values) if len(values) == EMBED_DIM else None
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        logger.warning("schemes: embedding failed (%s)", type(exc).__name__)
        return None


def ranked(
    question: str, *, embed: Callable[[str], list[float] | None] = embed_query
) -> list[tuple[float, Scheme]] | None:
    """Every scheme with its cosine similarity to the question, best first. None = could not run (no index, no key, API down)."""
    vectors = _index()
    query = embed(question) if vectors is not None else None
    if vectors is None or query is None:
        return None
    rows = _load()
    scored = [
        (sum(a * b for a, b in zip(query, v, strict=True)), rows[i][0])
        for i, v in enumerate(vectors)
    ]
    scored.sort(key=lambda s: -s[0])
    return scored


RERANK_PROMPT = """A citizen of Madhya Pradesh asked a question about government schemes. Below are candidate schemes found by search. Pick ONLY the candidates that
really answer the question (the same benefit, for the same kind of person). Output ONLY JSON: {"relevant": [<numbers>]}, best first, at most 3.
Use [] if none fits. Do not invent anything and do not write any other text.
"""


def _models() -> list[str]:
    """RERANK_MODELS (comma list), else GEMINI_MODEL, then the free-tier fallbacks the other Gemini steps use."""
    raw = os.environ.get("RERANK_MODELS", "").strip()
    models = [m.strip() for m in raw.split(",") if m.strip()]
    if models:
        return models
    first = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.6-flash"
    return [first, *[m for m in ("gemini-3-flash-preview", "gemini-3.1-flash-lite") if m != first]]


def rerank(
    question: str, candidates: list[Scheme], *, post: Callable[..., httpx.Response] = httpx.post
) -> list[Scheme] | None:
    """Gemini picks, by number, which retrieved candidates answer the question. It can only choose from the list. None = could not run."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if (
        not key
        or os.environ.get("SCHEME_RERANK", "").strip().lower() not in ("1", "true", "yes", "on")
        or len(candidates) < 2
    ):
        return None
    listing = chr(10).join(f"{i}. {doc_text(c)}" for i, c in enumerate(candidates, 1))
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"{RERANK_PROMPT}{chr(10)}Question: {question[:500]}{chr(10)}Candidates:{chr(10)}{listing}"
                    }
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    started = time.monotonic()
    for model in _models():
        if time.monotonic() - started >= RERANK_DEADLINE_SECONDS:
            break
        try:
            r = post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json=body,
                timeout=RERANK_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            picked = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])[
                "relevant"
            ]
            order = [
                int(n)
                for n in picked
                if isinstance(n, int | float) and 1 <= int(n) <= len(candidates)
            ]
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            logger.warning("schemes: rerank with %s failed (%s)", model, type(exc).__name__)
            continue
        return [candidates[n - 1] for n in dict.fromkeys(order)][:MAX_RESULTS]
    return None


def find_semantic(
    question: str,
    *,
    embed: Callable[[str], list[float] | None] = embed_query,
    limit: int = MAX_RESULTS,
    use_rerank: bool = True,
) -> list[Scheme] | None:
    """Closest schemes by meaning, optionally filtered by the rerank. None = could not run; [] = ran and found nothing close enough."""
    scored = ranked(question, embed=embed)
    if scored is None:
        return None
    if not scored or scored[0][0] < MIN_SIMILARITY:
        return []
    best = scored[0][0]
    close = [s for sim, s in scored[:limit] if sim >= best - MARGIN]
    if use_rerank:
        picked = rerank(
            question, [s for sim, s in scored[:RERANK_CANDIDATES] if sim >= MIN_SIMILARITY]
        )
        if picked is not None:
            return picked[:limit]
    return close


def find(question: str, *, limit: int = MAX_RESULTS) -> list[Scheme]:
    """RAG retrieval, falling back to the word match only when retrieval could not run. Never raises."""
    try:
        if not (question or "").strip():
            return []
        found = find_semantic(question, limit=limit)
        return found if found is not None else find_words(question, limit=limit)
    except Exception:  # noqa: BLE001 -- a broken index or file must never block an answer
        return []
