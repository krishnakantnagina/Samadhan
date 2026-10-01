"""S28 5 -- live routing accuracy run. NOT a pytest file: it calls the real LLM. No database writes.

Each message is one independent first turn (empty session). We run the real Turn Engine and the real validator,
then compare the routing outcome to the expected one. Two sources: hand-written cases (below) and a sample of the
SYNTHETIC Bundeli/Malvi files in data/conversations/ (git-ignored; skipped if absent). Results are reported per
category and written to submission/routing-eval-results.json. Run from backend/:

    PYTHONPATH=. uv run --env-file ../.env python tests/prompt/run_routing_eval.py [--per 6] [--pause 3.5]
"""

import argparse
import collections
import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path

from app import service_spec, validator
from app import turn_engine as te

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "submission" / "routing-eval-results.json"
DATA = ROOT / "data" / "conversations"

# (text, expected). expected: a service id | "information" | "out_of_context" | "ask" (a clarify or reconfirm is right)
HAND = [
    ("हमारे घर में तीन दिन से पानी नहीं आ रहा", "water_supply"),
    ("nal se ganda paani aa raha hai", "water_supply"),
    ("पाइपलाइन फट गई है, पानी बह रहा है", "water_supply"),
    ("दो दिन से बिजली नहीं आ रही", "electricity"),
    ("light nahi hai kal se", "electricity"),
    ("ट्रांसफार्मर जल गया है, पूरे मोहल्ले में अंधेरा है", "electricity"),
    ("बिजली का बिल बहुत ज्यादा आया है", "electricity"),
    ("सड़क में बड़ा गड्ढा हो गया है", "roads"),
    ("road bahut kharab hai, gaadi nahi chalti", "roads"),
    ("पुलिया टूट गई है", "roads"),
    ("कचरा तीन दिन से नहीं उठा", "sanitation"),
    ("नाली जाम हो गई है, गंदा पानी सड़क पर आ रहा है", "sanitation"),
    ("गली में बहुत गंदगी है", "sanitation"),
    ("स्कूल में टीचर नहीं आते", "human_evaluation"),
    ("अस्पताल में डॉक्टर नहीं मिलते", "human_evaluation"),
    ("राशन की दुकान वाला राशन नहीं दे रहा", "human_evaluation"),
    ("पेंशन तीन महीने से नहीं मिली", "human_evaluation"),
    ("आय प्रमाण पत्र कैसे बनवाएं?", "information"),
    ("राशन कार्ड के लिए कहाँ आवेदन करें", "information"),
    ("जाति प्रमाण पत्र के लिए क्या दस्तावेज़ चाहिए", "information"),
    ("नमस्ते", "out_of_context"),
    ("एक जोक सुनाओ", "out_of_context"),
    ("भारत की राजधानी क्या है", "out_of_context"),
    ("तुम कौन हो", "out_of_context"),
    ("पानी और नाली दोनों की दिक्कत है, गली में पानी भरा है", "ask"),
    ("बहुत परेशानी है यहाँ", "ask"),
]

# synthetic-file intent -> expected outcome (ambiguous intents are left out)
INTENT_EXPECT = {
    "WATER_SUPPLY": "water_supply", "WATER": "water_supply",
    "ELECTRICITY": "electricity",
    "ROAD": "roads",
    "DRAINAGE": "sanitation", "SANITATION": "sanitation",
    "TEACHER_ABSENCE": "human_evaluation", "HEALTH_SERVICE": "human_evaluation", "POLICE": "human_evaluation", "PENSION": "human_evaluation",
    "RATION": "human_evaluation", "LAND": "human_evaluation", "EDUCATION": "human_evaluation", "HOUSING": "human_evaluation",
    "AGRICULTURE": "human_evaluation", "EMPLOYMENT": "human_evaluation",
    "SCHEME_INFO": "information", "DOCUMENT": "information", "LOST_DOCUMENT": "information",
}  # fmt: skip


def synthetic_cases(per: int, rng: random.Random):
    if not DATA.exists():
        return []
    pool: dict[str, list[str]] = collections.defaultdict(list)
    for name in ("samadhan_bundeli_finetuning_150.json", "samadhan_bundeli_finetuning_v2_185.json"):
        path = DATA / name
        if not path.exists():
            continue
        for e in json.loads(path.read_text(encoding="utf-8"))["examples"]:
            want = INTENT_EXPECT.get(e["metadata"]["intent"])
            text = e["messages"][0]["content"]
            if want and text not in pool[want]:
                pool[want].append(text)
    malvi = DATA / "samadhan_malvi_water_200.json"
    if malvi.exists():
        for e in json.loads(malvi.read_text(encoding="utf-8"))["examples"]:
            text = e["messages"][0]["content"]
            if text not in pool["water_supply"]:
                pool["water_supply"].append(text)
    cases = []
    for want, texts in sorted(pool.items()):
        for text in rng.sample(texts, min(per, len(texts))):
            cases.append((text, want))
    return cases


def outcome(specs, text: str) -> tuple[str, dict]:
    try:
        turn = te.run_turn(
            session=te.SessionState(None, {}, False), specs=specs, text=text, lat=None, lng=None
        )
    except te.TurnEngineUnavailable:
        return "UNAVAILABLE", {}
    snap = validator.SessionSnapshot(None, {}, False, None, None)
    result = validator.apply(specs=specs, session=snap, turn_result=turn, lat=None, lng=None)
    detail = {"intent": turn.intent, "service_id": turn.service_id, "confidence": turn.confidence,
              "candidates": turn.candidates, "urgent": turn.urgent, "info_url": turn.info_url}  # fmt: skip
    if turn.intent == "information" and result.action == validator.ValidatedAction.OUT_OF_SCOPE:
        return "information", detail
    if turn.intent == "out_of_context" and not (turn.confirmed or turn.fields):
        return "out_of_context", detail
    if result.ask_for == "service":
        return "ask", detail
    return result.service_id or "declined", detail


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=6, help="synthetic messages per expected category")
    ap.add_argument("--pause", type=float, default=3.5, help="seconds between calls (rate limits)")
    args = ap.parse_args()
    specs = service_spec.load_specs(ROOT / "specs")
    rng = random.Random(11)
    cases = [("hand", t, w) for t, w in HAND] + [
        ("synthetic", t, w) for t, w in synthetic_cases(args.per, rng)
    ]
    print(f"{len(cases)} cases ({sum(c[0]=='hand' for c in cases)} hand-written, "
          f"{sum(c[0]=='synthetic' for c in cases)} synthetic)", flush=True)  # fmt: skip

    rows = []
    for source, text, want in cases:
        got, detail = outcome(specs, text)
        rows.append({"source": source, "text": text, "expected": want, "got": got, **detail})
        time.sleep(args.pause)

    answered = [r for r in rows if r["got"] != "UNAVAILABLE"]
    print(f"\nunavailable (excluded): {len(rows) - len(answered)}")
    for source in ("hand", "synthetic"):
        sub = [r for r in answered if r["source"] == source]
        if not sub:
            continue
        exact = sum(r["got"] == r["expected"] for r in sub)
        asked = sum(r["got"] == "ask" and r["expected"] != "ask" for r in sub)
        wrong = len(sub) - exact - asked
        print(f"\n[{source}] {len(sub)} answered: correct {exact} ({100 * exact / len(sub):.0f}%), "
              f"asked a question instead {asked}, wrong route {wrong}")  # fmt: skip
        by = collections.defaultdict(lambda: [0, 0])
        for r in sub:
            by[r["expected"]][1] += 1
            by[r["expected"]][0] += r["got"] == r["expected"]
        for k, (ok, n) in sorted(by.items()):
            print(f"   expected {k:15} {ok}/{n}")
    print("\nWRONG ROUTES (not counting a clarifying question):")
    for r in answered:
        if r["got"] not in (r["expected"], "ask"):
            print(f"   expected {r['expected']:14} got {r['got']:14} | {r['text']}")
    print("\nASKED A QUESTION where a route was expected:")
    for r in answered:
        if r["got"] == "ask" and r["expected"] != "ask":
            print(
                f"   expected {r['expected']:14} | {r['text']} | conf={r['confidence']} cands={r['candidates']}"
            )

    OUT.write_text(json.dumps({"run_at": datetime.now(UTC).isoformat(), "note": "synthetic data caveat: see S28",
                               "results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")  # fmt: skip


if __name__ == "__main__":
    main()
