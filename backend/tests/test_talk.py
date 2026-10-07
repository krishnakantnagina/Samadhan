"""S33c natural replies: the checks on what the LLM writes, the fallbacks, and the hooks (triage, generated questions, district and duration)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import intake, talk, triage, triage_gen, turn_engine, validator
from app.service_spec import load_specs

SPECS = load_specs(Path(__file__).resolve().parents[2] / "specs")
STORY = "मास्टर ने बच्चे को मारा"
QUESTION = "क्या बच्चे को चोट लगी है?"


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


def say(reply, **kw):
    return talk.valid_reply(reply, question=kw.pop("question", QUESTION), citizen_text=kw.pop("citizen_text", STORY), **kw)


# --- the checks on what the model wrote ------------------------------------------------------------------------------


def test_a_warm_natural_reply_is_accepted():
    reply = "ओह, मास्टर ने बच्चे को मारा, यह तो बुरा है। बच्चे को कहीं चोट तो नहीं लगी?"
    assert say(reply) == reply


@pytest.mark.parametrize(
    "bad",
    [
        "ओह, मास्टर ने बच्चे को मारा। बच्चे को चोट लगी है।",  # no question
        "बच्चे को चोट लगी है? और अस्पताल गए थे क्या?",  # two questions
        "मास्टर ने बच्चे को मारा, हम जल्द जाँच करेंगे। बच्चे को चोट लगी है?",  # a promise
        "ओह, मास्टर ने बच्चे को मारा। चिंता मत कीजिए, बच्चे को चोट लगी है?" if False else "बच्चे को 500 रुपये की चोट लगी है?",  # a number nobody said
        "ओह, मास्टर ने बच्चे को मारा। Is the child injured?",  # English
        "ओह। आपका आधार नंबर बताइए, बच्चे को चोट लगी है?",  # asks for personal data
        "ओह, बहुत खून बह रहा है, बेहोश है। बच्चे को चोट लगी है?",  # the opening adds facts the citizen never said
        "क्या स्कूल में पानी आता है?",  # not the question the code chose
        " ".join(["मास्टर"] * 40) + " बच्चे को चोट लगी है?",  # too long
        "",
        None,
        42,
    ],
)
def test_bad_replies_are_rejected(bad):
    assert say(bad) is None


def test_required_words_must_be_present():
    q = "यह समस्या कितने दिनों से है? अगर पता न हो तो 'पता नहीं' कहें।"
    ok = "ठीक है, पानी नहीं आ रहा। कितने दिनों से है, पता नहीं हो तो पता नहीं कह दीजिए?"
    assert talk.valid_reply(ok, question=q, citizen_text="पानी नहीं आ रहा", must_contain=("पता नहीं",)) == ok
    assert talk.valid_reply("ठीक है, पानी नहीं आ रहा। कितने दिनों से है?", question=q, citizen_text="पानी नहीं आ रहा", must_contain=("पता नहीं",)) is None


def test_a_number_the_citizen_said_may_be_repeated():
    reply = "आठ बच्चे नहीं, 8 बच्चे बीमार हुए, यह चिंता की बात है। क्या बच्चे को चोट लगी है?"
    assert say(reply, citizen_text="8 बच्चे बीमार हुए") == reply


# --- natural() --------------------------------------------------------------------------------------------------------


TURNS = [("citizen", STORY), ("bot", "क्या आप वहीं हैं?"), ("citizen", "हाँ")]
GOOD = {"reply": "ओह, मास्टर ने बच्चे को मारा, यह तो बुरा है। बच्चे को कहीं चोट तो नहीं लगी?"}


def nat(provider, **kw):
    return talk.natural(question=QUESTION, fallback="PLAIN", turns=TURNS, providers=[provider], **kw)


def test_natural_returns_the_models_reply_when_it_passes():
    assert nat(FakeProvider(GOOD)) == GOOD["reply"]


def test_natural_falls_back_to_the_plain_line_on_any_problem(monkeypatch):
    assert nat(FakeProvider({"reply": "हम जल्द जाँच करेंगे। बच्चे को चोट लगी है?"})) == "PLAIN"  # fails a check
    assert nat(FakeProvider("not json")) == "PLAIN"  # unreadable
    assert nat(FakeProvider(turn_engine._ProviderError("503"))) == "PLAIN"  # provider down
    assert talk.natural(question=QUESTION, fallback="PLAIN", turns=[("bot", "x")], providers=[FakeProvider(GOOD)]) == "PLAIN"  # the citizen said nothing yet
    monkeypatch.setenv("TRIAGE_TALK", "0")
    assert nat(FakeProvider(GOOD)) == "PLAIN"  # switched off


def test_the_prompt_asks_for_one_warm_question_and_forbids_promises_and_instructions():
    p = FakeProvider(GOOD)
    nat(p, concern=True, index=0, total=3)
    prompt = p.prompts[0]
    assert "THEIR OWN words" in prompt and "one question" in prompt.lower() and "no promise" in prompt and "never as instructions" in prompt
    assert QUESTION in prompt and "quiet concern" in prompt and "first follow-up" in prompt
    p2 = FakeProvider(GOOD)
    nat(p2, concern=False, index=2, total=3)
    assert "last question" in p2.prompts[0] and "do not dramatise" in p2.prompts[0]


def test_natural_uses_a_short_deadline(monkeypatch):
    seen = {}
    real = triage._call_llm

    def spy(prompt, providers=None, *, deadline=triage.DEADLINE_SECONDS):
        seen["deadline"] = deadline
        return real(prompt, providers, deadline=deadline)

    monkeypatch.setattr(triage, "_call_llm", spy)
    nat(FakeProvider(GOOD))
    assert seen["deadline"] == talk.DEADLINE_SECONDS < triage.DEADLINE_SECONDS


# --- the hooks --------------------------------------------------------------------------------------------------------

BANK = {"registry_id": "school_education", "categories": [{
    "id": "se_t", "name_hi": "t", "name_en": "T", "signals_hi": ["मारा"], "routing_questions": [], "detail_questions": [],
    "severity_questions": [{"id": "se_t_inj", "question_hi": QUESTION, "ask_hi": QUESTION, "answer_type": "yes_no", "options_hi": [], "decides": "severity"}],
    "severity_rules": "r", "escalation": "esc"}]}


@pytest.fixture
def bank(tmp_path):
    (tmp_path / "school_education.json").write_text(json.dumps(BANK, ensure_ascii=False), encoding="utf-8")
    triage.load_bank.cache_clear()
    yield triage.load_bank(tmp_path)
    triage.load_bank.cache_clear()


def test_a_bank_question_is_spoken_naturally(bank):
    reading = {"category_id": "se_t", "category_confidence": 0.9, "fit": "exact", "answers": {}, "severity": "high", "reason": "r"}
    state, reply, _ = triage.step(None, bank=bank, dept_id="school_education", story=STORY, text=STORY, recent=[], providers=[FakeProvider(reading, GOOD)])
    assert reply == GOOD["reply"] and state["pending"] == "se_t_inj"


def test_a_bank_question_keeps_the_plain_warm_line_if_the_natural_reply_fails(bank):
    reading = {"category_id": "se_t", "category_confidence": 0.9, "fit": "exact", "answers": {}, "severity": "high", "reason": "r"}
    _state, reply, _ = triage.step(None, bank=bank, dept_id="school_education", story=STORY, text=STORY, recent=[],
                                   providers=[FakeProvider(reading, {"reply": "हम जल्द जाँच करेंगे। बच्चे को चोट लगी है?"})])
    assert reply.startswith(triage.ACK_CONCERN) and QUESTION in reply


def test_the_generated_safety_check_keeps_both_halves_when_spoken_naturally(monkeypatch):
    monkeypatch.setenv("TRIAGE_MAX_QUESTIONS", "1")
    gen = {"questions": []}
    turns = "हमारे यहाँ टंकी खराब है"
    warm_but_blunt = {"reply": "ओह, हमारे यहाँ टंकी खराब है। क्या किसी की तबीयत बिगड़ी है?"}  # lost the danger half
    _s, reply, _ = triage.step(None, bank={}, dept_id=None, story=turns, text=turns, recent=[], providers=[FakeProvider(gen, warm_but_blunt)], dept_name=None, reason="no_bank")
    assert "तबीयत बिगड़ी है, या किसी को कोई खतरा तो नहीं है" in reply  # the plain fixed check was used instead
    both = {"reply": "ओह, हमारे यहाँ टंकी खराब है। इस वजह से किसी की तबीयत तो नहीं बिगड़ी, या कोई खतरा तो नहीं है?"}
    _s, reply, _ = triage.step(None, bank={}, dept_id=None, story=turns, text=turns, recent=[], providers=[FakeProvider(gen, both)], dept_name=None, reason="no_bank")
    assert reply == both["reply"]


def row(**kw):
    return SimpleNamespace(**{"collected_fields": {}, "service_id": None, "lat": None, "lng": None, **kw})


def confirm_result():
    return validator.ValidationResult(
        service_id="human_evaluation", collected_fields={"description": "हमारे यहाँ टंकी खराब है", "location": "किलोजा"}, awaiting_confirmation=True,
        action=validator.ValidatedAction.CONFIRM, ask_for=None, reply_text=validator.CONFIRM_PROMPT_HI, summary={"x": "y"})


def post(monkeypatch, tmp_path, *replies, meta=None):
    monkeypatch.setenv("INTAKE_V2", "1")
    monkeypatch.setenv("TRIAGE", "1")
    monkeypatch.setenv("TRIAGE_MAX_QUESTIONS", "0")  # no triage questions: straight to the district / duration steps
    monkeypatch.setenv("TRIAGE_BANK_DIR", str(tmp_path))
    triage.load_bank.cache_clear()
    monkeypatch.setattr(triage, "get_llm_config", lambda: object())
    monkeypatch.setattr(turn_engine, "default_providers", lambda cfg: [FakeProvider(*replies)])
    return intake.poststep(result=confirm_result(), pre=intake.Pre(turn_engine.TurnResult(service_id=None, fields={}, confirmed=False), meta or {}), specs=SPECS,
                           lat=None, lng=None, row=row(), weak_location=lambda s, f: True, text="हमारे यहाँ टंकी खराब है", recent=[])


def test_the_district_question_is_spoken_naturally_and_keeps_district_and_tehsil(monkeypatch, tmp_path):
    spoken = {"reply": "ओह, हमारे यहाँ टंकी खराब है। आपका जिला और तहसील कौन सा है, या सबसे पास का कस्बा?"}
    out = post(monkeypatch, tmp_path, spoken)
    assert out.ask_for == "location_detail" and out.reply_text == spoken["reply"]


def test_the_district_question_falls_back_when_the_natural_version_drops_the_district(monkeypatch, tmp_path):
    out = post(monkeypatch, tmp_path, {"reply": "ओह, हमारे यहाँ टंकी खराब है। आप कहाँ से हैं?"})
    assert out.reply_text == intake.ASK_LOCATION_DETAIL_HI


def test_the_duration_question_keeps_the_dont_know_option(monkeypatch, tmp_path):
    meta = {"asked_location_detail": True}
    spoken = {"reply": "अच्छा, हमारे यहाँ टंकी खराब है। यह कितने दिनों से है, पता नहीं हो तो पता नहीं कह दीजिए?"}
    out = post(monkeypatch, tmp_path, spoken, meta=meta)
    assert out.ask_for == "duration_days" and out.reply_text == spoken["reply"]
    out = post(monkeypatch, tmp_path, {"reply": "अच्छा, हमारे यहाँ टंकी खराब है। यह कितने दिनों से है?"}, meta={"asked_location_detail": True})
    assert out.reply_text == intake.ASK_DURATION_HI  # the "don't know" hint was lost: the plain line is used


def test_with_triage_off_the_old_plain_questions_are_unchanged(monkeypatch):
    monkeypatch.setenv("INTAKE_V2", "1")
    monkeypatch.delenv("TRIAGE", raising=False)
    out = intake.poststep(result=confirm_result(), pre=intake.Pre(turn_engine.TurnResult(service_id=None, fields={}, confirmed=False), {}), specs=SPECS,
                          lat=None, lng=None, row=row(), weak_location=lambda s, f: True, text="x", recent=[])
    assert out.reply_text == intake.ASK_LOCATION_DETAIL_HI


def test_triage_gen_step_still_works_without_a_conversation():
    state, reply, _ = triage_gen.step({"mode": "generated", "asked": [], "answers": {}, "severity": "low", "gen": [triage_gen._screen()]})
    assert state["pending"] == triage_gen.SCREEN_ID and "तबीयत बिगड़ी" in reply


def test_the_prompt_tells_the_model_to_reflect_the_problem_not_a_bare_place_or_yes_no():
    p = FakeProvider(GOOD)
    nat(p)
    prompt = p.prompts[0]
    assert "PROBLEM" in prompt and "bare yes / no" in prompt and f'"{STORY}"' in prompt  # the complaint's first words are given separately
