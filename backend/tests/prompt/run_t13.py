"""T13 -- live prompt accuracy run (spec S21). NOT a pytest file: it calls the real LLM + Supabase.

Run from backend/:  PYTHONPATH=. uv run --env-file ../.env python tests/prompt/run_t13.py
"""

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_client
from app.main import app

ROOT = Path(__file__).resolve().parents[3]
SENTENCES = ROOT / "submission" / "T09-test-sentences.json"
RESULTS = ROOT / "submission" / "T13-prompt-test-results.json"
ALL = {"no_supply", "low_pressure", "dirty_water", "leakage", "other"}

# S21 grading table -- fixed before the first run.
ACCEPTED = {
    "T09-01": {"no_supply"}, "T09-02": {"no_supply"}, "T09-05": {"no_supply"},
    "T09-09": {"no_supply"}, "T09-14": {"no_supply"}, "T09-15": {"no_supply"},
    "T09-07": {"leakage"}, "T09-10": {"low_pressure"}, "T09-12": {"dirty_water"},
    "T09-03": {"no_supply", "low_pressure"},
    "T09-04": {"no_supply", "other"}, "T09-06": {"no_supply", "other"},
    "T09-08": {"no_supply", "other"},
    "T09-13": {"low_pressure", "other"},
    "T09-11": ALL,
}  # fmt: skip


def grade(sentence, body, fields):
    reasons = []
    if body.get("action") != "ask" or body.get("ask_for") != "location":
        reasons.append(f"action={body.get('action')} ask_for={body.get('ask_for')}")
    issue = fields.get("issue_type")
    if issue not in ACCEPTED[sentence["id"]]:
        reasons.append(f"issue_type={issue!r} not in {sorted(ACCEPTED[sentence['id']])}")
    want_days = sentence["expected_fields"].get("duration_days")
    if want_days is not None and fields.get("duration_days") != want_days:
        reasons.append(f"duration_days={fields.get('duration_days')!r} != {want_days}")
    return reasons


def main() -> int:
    sentences = json.loads(SENTENCES.read_text(encoding="utf-8"))["sentences"]
    db = get_client()
    results = []
    with TestClient(app) as client:
        for s in sentences:
            sid = uuid.uuid4()
            r = client.post(
                "/api/v1/message",
                files={
                    "session_id": (None, str(sid)),
                    "message_id": (None, str(uuid.uuid4())),
                    "text": (None, s["text"]),
                },
            )
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            row = db.table("sessions").select("collected_fields").eq("id", str(sid)).maybe_single().execute()
            fields = (row.data or {}).get("collected_fields", {}) if row is not None else {}
            reasons = [f"HTTP {r.status_code}"] if r.status_code != 200 else grade(s, body, fields)
            results.append(
                {"id": s["id"], "text": s["text"], "http": r.status_code, "response": body,
                 "collected_fields": fields, "accepted": sorted(ACCEPTED[s["id"]]),
                 "pass": not reasons, "reasons": reasons}
            )  # fmt: skip
            mark = "PASS" if not reasons else "FAIL"
            print(f"{s['id']} {mark} issue={fields.get('issue_type')} days={fields.get('duration_days')}"
                  f" {'; '.join(reasons)}")  # fmt: skip
    passed = sum(x["pass"] for x in results)
    print(f"\nScore: {passed}/{len(results)} (target >= 13)")
    RESULTS.write_text(
        json.dumps(
            {"ticket": "T13", "run_at": datetime.now(UTC).isoformat(),
             "llm_provider": os.environ.get("LLM_PROVIDER"), "groq_model": os.environ.get("GROQ_MODEL"),
             "gemini_model": os.environ.get("GEMINI_MODEL"), "score": f"{passed}/{len(results)}",
             "results": results},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return 0 if passed >= 13 else 1


if __name__ == "__main__":
    sys.exit(main())
