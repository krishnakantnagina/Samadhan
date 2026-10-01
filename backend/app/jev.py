"""S30 -- TypeSafe Jev client for the intake router. Docs: https://docs.typesafe.ai (POST /v1/systemone).

Jev makes DECISIONS only: which department owns a complaint (one Choice over the registry), whether the message describes immediate danger, and whether a
citizen's short reply agrees with a question we asked (Noul). It never writes text and never routes by itself: app/intake.py owns the flow and thresholds.

Failure is never fatal: any network, HTTP or parsing problem raises JevUnavailable and the caller falls back to the existing LLM path for that turn.
Privacy: only the citizen's message and the last few turns are sent, and nothing about them is logged here (no text, no key). The whole path is off unless
INTAKE_V2 is on AND TYPESAFE_API_KEY is set.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
TIMEOUT_SECONDS = 8.0  # same order as the ASR/LLM provider timeouts (S05)

DEPT_INSTRUCTIONS = (
    "Which government department should handle this citizen's complaint or request? Use the whole conversation. The message may be in a Hindi dialect."
)
URGENT_INSTRUCTIONS = "The citizen describes immediate danger to life or safety, such as a fire, a medical emergency, violence or a crime in progress."


class JevUnavailable(RuntimeError):
    """Jev could not answer (network, timeout, HTTP error, unexpected response). The caller falls back; nothing is lost."""


@dataclass(frozen=True)
class DeptDecision:
    top: tuple[tuple[str, float], ...]  # (department id, probability), best first, at most 3
    confidence: float  # Jev's own 0-1 confidence (how peaked the distribution is), not a probability of being right
    urgent: float  # probability the message describes immediate danger


class Decider(Protocol):
    def decide(self, state: dict[str, Any], departments: list[dict[str, Any]]) -> DeptDecision: ...

    def agrees(self, state: dict[str, Any], statement: str) -> float: ...


def department_criteria(departments: list[dict[str, Any]]) -> dict[str, str]:
    """Choice options: id -> 'English name: hint | Hindi name' (the hints are what made department routing accurate in the benchmark)."""
    out = {}
    for d in departments:
        hint = f": {d['hint']}" if d.get("hint") else ""
        out[d["id"]] = f"{d['name_en']}{hint} | {d['name_hi']}"
    return out


class JevDecider:
    def __init__(self, api_key: str, *, model: str = DEFAULT_MODEL, timeout: float = TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self._key, self._model, self._timeout = api_key, model, timeout
        self._client = client or httpx.Client(timeout=timeout)

    def _ask(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(
                URL, headers={"Authorization": f"Bearer {self._key}"}, json={"model": self._model, "state": state, "questions": questions}, timeout=self._timeout
            )
            response.raise_for_status()
            return response.json()["answers"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("jev unavailable: %s", exc.__class__.__name__)  # class only: never the text, never the key
            raise JevUnavailable(exc.__class__.__name__) from exc

    def decide(self, state: dict[str, Any], departments: list[dict[str, Any]]) -> DeptDecision:
        answers = self._ask(state, {
            "dept": {"type": "choice", "instructions": DEPT_INSTRUCTIONS, "criteria": department_criteria(departments)},
            "urgent": {"type": "noul", "instructions": URGENT_INSTRUCTIONS},
        })
        try:
            dept = answers["dept"]
            top = tuple(sorted(dept["probabilities"].items(), key=lambda kv: -kv[1])[:3])
            return DeptDecision(top=top, confidence=float(dept["confidence"]), urgent=float(answers["urgent"]["noul"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise JevUnavailable("unexpected response shape") from exc

    def agrees(self, state: dict[str, Any], statement: str) -> float:
        answers = self._ask(state, {"agrees": {"type": "noul", "instructions": statement}})
        try:
            return float(answers["agrees"]["noul"])
        except (KeyError, TypeError, ValueError) as exc:
            raise JevUnavailable("unexpected response shape") from exc


def from_env() -> JevDecider | None:
    """A decider when TYPESAFE_API_KEY is set, else None (the caller then keeps the existing behaviour)."""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        return None
    return JevDecider(key, model=os.environ.get("TYPESAFE_MODEL", "").strip() or DEFAULT_MODEL)
