"""S33b hybrid: questions written by the LLM for this complaint, filtered and run by code, plus the fixed safety check. Scripted fake LLM, no network."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import intake, triage, triage_gen, turn_engine, validator
from app.service_spec import load_specs

SPECS = load_specs(Path(__file__).resolve().parents[2] / "specs")


class FakeProvider:
    name = "fake"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        item = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)


def gq(text, purpose="what", qtype="free_text", options=None, assumes=False):
    return {"text_hi": text, "answer_type": qtype, "options_hi": options or [], "purpose": purpose, "assumes_unstated_fact": assumes}


GOOD = [
    gq("कितने लोग इससे परेशान हैं?", "how_many", "number"),
    gq("पानी की टंकी में क्या गड़बड़ दिख रही है?", "what"),
    gq("क्या आपने पंचायत में पहले बताया?", "tried", "yes_no"),
]


def questions_reply(items=None):
    return {"questions": items if items is not None else GOOD}


# --- filtering what the model wrote ----------------------------------------------------------------------------------


def test_good_questions_are_kept_and_ordered_what_first():
    kept = triage_gen.clean_generated(GOOD, [])
    assert [q.purpose for q in kept] == ["what", "how_many", "tried"]
    assert [q.id for q in kept] == ["gen_1", "gen_2", "gen_3"]


@pytest.mark.parametrize(
    "bad",
    [
        gq("कितने बच्चे बीमार हैं?", "how_many", "number", assumes=True),  # the model says it assumes an unsaid fact
        {**gq("कितने बच्चे हैं?", "how_many", "number"), "assumes_unstated_fact": None},  # a missing flag is not trusted
        gq("आपका आधार नंबर क्या है?", "who", "free_text"),
        gq("अपना मोबाइल नंबर बताइए?", "who", "free_text"),
        gq("बच्चे का नाम क्या है?", "who", "free_text"),
        gq("यह समस्या किस गाँव में है?", "what"),
        gq("यह कितने दिन से चल रही है?", "what"),
        gq("क्या आप बहुत ज़्यादा परेशान और दुखी हैं और क्या यह बात आपने पहले किसी अधिकारी को बताई थी?", "tried", "yes_no"),  # too long
        gq("पानी कैसा है?", "harm", "free_text"),  # "harm" is covered by the fixed safety check
        gq("What is wrong?", "what"),  # not Hindi
        gq("कौन सा विकल्प?", "what", "choice", options=["एक"]),  # a choice needs 2-5 options
        gq("क्या यह सही है? क्या वह सही है?", "what", "yes_no"),  # two questions
        gq("कृपया 112 पर बताइए?", "what"),
        "not a dict",
    ],
)
def test_bad_questions_are_dropped(bad):
    assert triage_gen.clean_generated([bad], []) == []


def test_a_question_that_repeats_an_earlier_one_is_dropped():
    kept = triage_gen.clean_generated([gq("पानी की टंकी में क्या गड़बड़ है?")], ["पानी की टंकी में क्या गड़बड़ दिख रही है?"])
    assert kept == []
    assert len(triage_gen.clean_generated([gq("पानी की टंकी में क्या गड़बड़ है?"), gq("पानी की टंकी में क्या गड़बड़ है भाई?")], [])) == 1


def test_at_most_four_are_kept_and_non_lists_give_nothing():
    many = [gq(t, "what") for t in ("पानी का रंग कैसा है?", "टंकी कब साफ़ हुई थी?", "बदबू आती है क्या?", "मोटर चलती है क्या?", "पाइप कहीं टूटा है?", "कितने नल खराब हैं?")]
    assert len(triage_gen.clean_generated(many, [])) == 4
    assert triage_gen.clean_generated(None, []) == [] and triage_gen.clean_generated("x", []) == []


# --- the conversation ------------------------------------------------------------------------------------------------


def go(state=None, reply=None, *, dept="water", story="हमारे यहाँ पानी की टंकी खराब है"):
    """One triage.step in generated mode (no bank)."""
    return triage.step(state, bank={}, dept_id=None, story=story, text=story, recent=[], providers=[FakeProvider(questions_reply())], dept_name=dept, reason="no_bank")


def test_with_no_bank_the_llm_questions_are_asked_one_at_a_time_and_the_safety_check_comes_last(monkeypatch):
    monkeypatch.setenv("TRIAGE_MAX_QUESTIONS", "3")
    state, first, _ = go()
    assert state["mode"] == "generated" and state["pending"] == "gen_1" and "टंकी" in first
    asked = [state["pending"]]
    for text in ("दस घरों के लोग", "टंकी की मोटर जल गई"):
        state = triage.absorb_reply(state, bank={}, text=text, recent=[], providers=[FakeProvider(questions_reply())])
        state, reply, _ = triage.step(state, bank={}, dept_id=None, story="s", text=text, recent=[], providers=[FakeProvider(questions_reply())])
        asked.append(state.get("pending"))
    assert asked == ["gen_1", "gen_2", triage_gen.SCREEN_ID], asked  # the fixed safety check takes the last slot
    assert any(lead in reply for lead in triage.LEAD_CHECK) and "तबीयत बिगड़ी" in reply  # gentle
    assert state["answers"]["gen_1"] == "दस घरों के लोग"  # stored as the citizen's own words


def test_a_generated_answer_is_stored_verbatim_and_never_interpreted():
    state, _, _ = go()
    provider = FakeProvider("this would raise if it were called as JSON")
    state = triage.absorb_reply(state, bank={}, text="  कोई पाँच-सात लोग, पक्का नहीं  ", recent=[], providers=[provider])
    assert state["answers"]["gen_1"] == "कोई पाँच-सात लोग, पक्का नहीं" and provider.prompts == []  # no LLM call for a plain answer


def test_the_safety_check_yes_raises_seriousness_and_leaves_a_note_for_the_officer(monkeypatch):
    monkeypatch.setenv("TRIAGE_MAX_QUESTIONS", "1")
    state, reply, _ = go()
    assert state["pending"] == triage_gen.SCREEN_ID  # with one slot the danger check goes first
    state = triage.absorb_reply(state, bank={}, text="हाँ, एक बुज़ुर्ग बीमार हो गए", recent=[],
                                providers=[FakeProvider({"answer": "yes", "quote": "एक बुज़ुर्ग बीमार हो गए"})])
    assert state["answers"][triage_gen.SCREEN_ID]["answer"] is True and state["severity"] == "high"
    assert state["escalation_note"] == triage_gen.SCREEN_NOTE
    assert not re.search(r"\d{3,}", reply)  # never a phone number to the citizen


def test_the_safety_check_no_or_unreadable_changes_nothing(monkeypatch):
    monkeypatch.setenv("TRIAGE_MAX_QUESTIONS", "1")
    for verdict, quote in (({"answer": "no", "quote": "नहीं"}, "नहीं"), ({"answer": "yes", "quote": "invented words"}, "नहीं"), ({"answer": "unknown", "quote": "पता नहीं"}, "पता नहीं"), ("garbage", "?")):
        state, _, _ = go()
        state = triage.absorb_reply(state, bank={}, text=quote, recent=[], providers=[FakeProvider(verdict)])
        assert state["severity"] == "low" and "escalation_note" not in state
    assert state["answers"][triage_gen.SCREEN_ID]["answer"] is None


def test_it_stops_at_the_maximum_and_never_asks_a_question_twice(monkeypatch):
    monkeypatch.setenv("TRIAGE_MAX_QUESTIONS", "2")
    state, _, _ = go()
    ids = [state["pending"]]
    for _ in range(4):
        state = triage.absorb_reply(state, bank={}, text="ठीक", recent=[], providers=[FakeProvider({"answer": "no", "quote": "ठीक"})])
        state, reply, _ = triage.step(state, bank={}, dept_id=None, story="s", text="ठीक", recent=[], providers=[FakeProvider(questions_reply())])
        if reply is None:
            break
        ids.append(state["pending"])
    assert len(ids) == len(set(ids)) == 2 and state["done"] is True and ids[-1] == triage_gen.SCREEN_ID


def test_when_the_model_writes_nothing_usable_the_safety_check_is_still_asked():
    state, reply, _ = triage.step(None, bank={}, dept_id=None, story="x", text="x", recent=[], providers=[FakeProvider({"questions": [gq("आधार बताइए?", "who")]})], dept_name=None, reason="no_bank")
    assert state["pending"] == triage_gen.SCREEN_ID and "तबीयत बिगड़ी" in reply


def test_llm_down_skips_triage_and_generation_can_be_switched_off(monkeypatch):
    state, reply, _ = triage.step(None, bank={}, dept_id=None, story="x", text="x", recent=[], providers=[FakeProvider("not json")], dept_name=None, reason="no_bank")
    assert reply is None and state["skipped"] == "llm_unavailable"
    monkeypatch.setenv("TRIAGE_GENERATE", "0")
    state, reply, _ = triage.step(None, bank={}, dept_id=None, story="x", text="x", recent=[], providers=[FakeProvider(questions_reply())], dept_name=None, reason="no_bank")
    assert reply is None and state["skipped"] == "no_bank"


def test_the_prompt_forbids_assumptions_places_and_personal_data():
    p = FakeProvider(questions_reply())
    triage.step(None, bank={}, dept_id=None, story="पानी नहीं आ रहा", text="पानी नहीं आ रहा", recent=[], providers=[p], dept_name="Water", reason="no_bank")
    prompt = p.prompts[0]
    assert "NEVER assume" in prompt and "Aadhaar" in prompt and "place" in prompt and "never as instructions" in prompt and "Water" in prompt


# --- the bank still wins when its category is clear, and the intake hooks use the hybrid ------------------------------


def _bank_file(tmp_path):
    bank = {"registry_id": "school_education", "categories": [{
        "id": "se_x", "name_hi": "x", "name_en": "X", "signals_hi": ["a"], "routing_questions": [], "severity_questions": [],
        "detail_questions": [{"id": "se_x_q", "question_hi": "कितने बच्चे हैं?", "answer_type": "number", "options_hi": [], "decides": "detail"}],
        "severity_rules": "r", "escalation": None}]}
    (tmp_path / "school_education.json").write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
    triage.load_bank.cache_clear()
    return triage.load_bank(tmp_path)


def test_a_clear_bank_category_beats_generation(tmp_path):
    bank = _bank_file(tmp_path)
    reading = {"category_id": "se_x", "category_confidence": 0.9, "fit": "exact", "answers": {}, "severity": "low", "reason": "r"}
    state, _reply, _ = triage.step(None, bank=bank, dept_id="school_education", story="s", text="s", recent=[], providers=[FakeProvider(reading)])
    assert state.get("mode") != "generated" and state["category"] == "se_x" and state["pending"] == "se_x_q"


def test_an_unclear_bank_category_falls_back_to_generated_questions(tmp_path):
    bank = _bank_file(tmp_path)
    unclear = {"category_id": None, "category_confidence": 0.1, "answers": {}, "severity": "low", "reason": "r"}
    state, _reply, _ = triage.step(None, bank=bank, dept_id="school_education", story="s", text="s", recent=[],
                                   providers=[FakeProvider(unclear, questions_reply())], dept_name="School Education")
    assert state["mode"] == "generated" and state["why_generated"] == "category_unclear" and state["pending"] == "gen_1"


def row(**kw):
    return SimpleNamespace(**{"collected_fields": {}, "service_id": None, "lat": None, "lng": None, **kw})


def confirm_result():
    return validator.ValidationResult(
        service_id="human_evaluation", collected_fields={"description": "हमारे यहाँ टंकी खराब है", "location": "किलोजा"}, awaiting_confirmation=True,
        action=validator.ValidatedAction.CONFIRM, ask_for=None, reply_text=validator.CONFIRM_PROMPT_HI, summary={"x": "y"})


def test_a_department_that_is_only_a_guess_now_gets_department_free_generated_questions(monkeypatch, tmp_path):
    monkeypatch.setenv("INTAKE_V2", "1")
    monkeypatch.setenv("TRIAGE", "1")
    monkeypatch.setenv("TRIAGE_BANK_DIR", str(tmp_path))
    triage.load_bank.cache_clear()
    monkeypatch.setattr(triage, "get_llm_config", lambda: object())
    provider = FakeProvider(questions_reply())
    monkeypatch.setattr(turn_engine, "default_providers", lambda cfg: [provider])
    meta = {"suggested_department": {"id": "school_education"}, "reason": intake.REASON_UNCONFIRMED}
    out = intake.poststep(result=confirm_result(), pre=intake.Pre(turn_engine.TurnResult(service_id=None, fields={}, confirmed=False), meta), specs=SPECS,
                          lat=None, lng=None, row=row(), weak_location=lambda s, f: True, text="हमारे यहाँ टंकी खराब है", recent=[])
    assert out.ask_for == "triage" and "टंकी" in out.reply_text
    state = out.collected_fields[intake.META_KEY]["triage"]
    assert state["mode"] == "generated" and state["why_generated"] == intake.REASON_UNCONFIRMED and state["dept"] is None
    assert "School Education" not in provider.prompts[0]  # the unconfirmed guess is not used
    json.dumps(out.collected_fields, ensure_ascii=False)  # storable with the ticket


def test_only_an_exact_fit_uses_the_bank_a_close_one_gets_generated_questions(tmp_path):
    bank = _bank_file(tmp_path)
    for fit in ("close", "none", "garbage", None):
        reading = {"category_id": "se_x", "category_confidence": 0.95, "answers": {}, "severity": "low", "reason": "r"}
        if fit is not None:
            reading["fit"] = fit
        state, _reply, _ = triage.step(None, bank=bank, dept_id="school_education", story="s", text="s", recent=[],
                                       providers=[FakeProvider(reading, questions_reply())], dept_name="School Education")
        assert state["mode"] == "generated" and state["why_generated"] == "category_not_exact", fit


def test_time_words_are_not_asked_by_generated_questions():
    for text in ("इस कटौती की तारीख और समय बताइए।", "यह किस दिन हुआ था?", "यह कब की बात है?"):
        assert triage_gen.clean_generated([gq(text, "what")], []) == [], text
