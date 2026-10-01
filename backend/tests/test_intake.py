"""S30 intake v2: the Lead's flow, tested with a fake Jev (no network). Real specs and the real registry file are used."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import intake, jev, routes, session, turn_engine, validator
from app.service_spec import load_specs
from mock.errors import register_error_handlers

SPECS = load_specs(Path(__file__).resolve().parents[2] / "specs")
REG = intake.load_registry()


class FakeDecider:
    def __init__(self, top=(("phe", 0.95), ("panchayat_rural_development", 0.04)), confidence=0.95, urgent=0.0, agree=1.0, fail=False):
        self.top, self.confidence, self.urgent, self.agree, self.fail = tuple(top), confidence, urgent, agree, fail
        self.decide_calls = self.agree_calls = 0

    def decide(self, state, departments):
        self.decide_calls += 1
        if self.fail:
            raise jev.JevUnavailable("down")
        return jev.DeptDecision(self.top, self.confidence, self.urgent)

    def agrees(self, state, statement):
        self.agree_calls += 1
        if self.fail:
            raise jev.JevUnavailable("down")
        return self.agree


def row(**kw):
    return SimpleNamespace(**{"collected_fields": {}, "service_id": None, "lat": None, "lng": None, **kw})


def turn(**kw):
    return turn_engine.TurnResult(**{"service_id": None, "fields": {}, "confirmed": False, **kw})


@pytest.fixture(autouse=True)
def flag_on(monkeypatch):
    monkeypatch.setenv("INTAKE_V2", "1")


def pre(decider, r=None, t=None, text="पानी नहीं आ रहा", specs=SPECS):
    return intake.prestep(row=r or row(), specs=specs, text=text, recent=[], turn_result=t or turn(), decider=decider, registry=REG)


# --- registry ----------------------------------------------------------------------------------------------------

def test_registry_matches_the_real_specs():
    assert len(REG.departments) == 49 and (REG.route, REG.reconfirm) == (0.8, 0.5)
    assert set(REG.live_specs.values()) <= set(SPECS) and set(REG.live_specs) <= set(REG.by_id)  # every live department has a real spec
    assert all(d["name_hi"] and d["name_en"] for d in REG.departments)


# --- prestep: off / fail-open ------------------------------------------------------------------------------------

def test_flag_off_changes_nothing(monkeypatch):
    monkeypatch.setenv("INTAKE_V2", "")
    t = turn()
    result = pre(FakeDecider(fail=True), t=t)
    assert result.turn_result is t and result.meta is None and result.ask is None


def test_no_key_means_no_decider_and_nothing_changes(monkeypatch):
    monkeypatch.setattr(intake, "default_decider", lambda: None)
    t = turn()
    result = intake.prestep(row=row(), specs=SPECS, text="x", recent=[], turn_result=t)
    assert result.turn_result is t and result.meta is None


def test_without_a_general_spec_it_stays_off():
    only_water = {"water_supply": SPECS["water_supply"]}
    d = FakeDecider()
    assert pre(d, specs=only_water).meta is None and d.decide_calls == 0


def test_jev_down_fails_open_to_the_existing_path():
    t = turn(service_id="water_supply", confidence=0.4)
    result = pre(FakeDecider(fail=True), t=t)
    assert result.turn_result is t and result.meta is None and result.ask is None


def test_a_complaint_in_progress_and_non_complaints_never_call_jev():
    d = FakeDecider()
    assert pre(d, r=row(service_id="water_supply")).turn_result.service_id is None and d.decide_calls == 0
    assert pre(d, t=turn(intent="information")).meta is None and d.decide_calls == 0
    assert pre(d, t=turn(intent="out_of_context")).meta is None and d.decide_calls == 0


# --- prestep: Jev decides ----------------------------------------------------------------------------------------

def test_confident_live_department_uses_its_spec():
    out = pre(FakeDecider())
    assert (out.turn_result.service_id, out.turn_result.confidence, out.turn_result.candidates) == ("water_supply", 1.0, [])
    assert out.ask is None and out.meta["reason"] == "confident" and out.meta["suggested_department"]["id"] == "phe"
    assert out.meta["jev"][0] == {"id": "phe", "p": 0.95}


def test_confident_department_without_a_spec_goes_to_general_triage_with_the_suggestion():
    out = pre(FakeDecider(top=(("school_education", 0.93), ("higher_education", 0.05))))
    assert out.turn_result.service_id == "human_evaluation" and out.ask is None
    assert out.meta["reason"] == "department_not_live" and out.meta["suggested_department"]["name_en"] == "School Education"


def test_unsure_asks_one_question_about_the_top_department():
    out = pre(FakeDecider(top=(("school_education", 0.55), ("higher_education", 0.40)), confidence=0.6))
    assert out.ask is not None and "स्कूल शिक्षा विभाग" in out.ask and out.ask_for == "service"
    assert out.meta["pending_dept"] == "school_education" and out.meta["questions_asked"] == 1
    assert out.turn_result.service_id is None  # nothing routed yet


def test_citizen_says_yes_so_the_suggested_department_is_confirmed():
    r = row(collected_fields={intake.META_KEY: {"pending_dept": "energy", "questions_asked": 1}})
    out = pre(FakeDecider(agree=0.9), r=r, text="हाँ")
    assert out.turn_result.service_id == "electricity" and out.ask is None
    assert out.meta["reason"] == "confirmed_by_citizen" and out.meta["confirmed_by_citizen"] is True and out.meta["pending_dept"] is None


def test_citizen_says_no_goes_to_human_evaluation_and_never_a_second_question():
    r = row(collected_fields={intake.META_KEY: {"pending_dept": "energy", "questions_asked": 1}})
    d = FakeDecider(agree=0.1)
    out = pre(d, r=r, text="नहीं")
    assert out.turn_result.service_id == "human_evaluation" and out.ask is None and d.decide_calls == 0  # no new department question
    assert out.meta["reason"] == "department_unconfirmed" and out.meta["suggested_department"]["id"] == "energy"
    assert out.meta["questions_asked"] == 1


def test_urgent_danger_is_flagged_and_keeps_the_safety_line_on_the_question():
    out = pre(FakeDecider(top=(("home", 0.5), ("finance", 0.4)), confidence=0.55, urgent=0.9))
    assert out.turn_result.urgent is True and out.ask.startswith(validator.URGENT_LINE_HI)


def test_location_detail_answer_never_replaces_the_village_the_citizen_named():
    r = row(service_id="water_supply", collected_fields={intake.META_KEY: {"awaiting_location_detail": True}})
    out = pre(FakeDecider(), r=r, t=turn(fields={"location": "सागर", "duration_days": 3}), text="सागर जिला")
    assert out.turn_result.fields == {"duration_days": 3}  # the location the LLM re-read is dropped, other details are kept
    assert out.meta["location_details"]["district"] == "Sagar"


def test_location_detail_answer_is_kept_for_the_officer():
    r = row(service_id="water_supply", collected_fields={intake.META_KEY: {"awaiting_location_detail": True}})
    out = pre(FakeDecider(), r=r, text="  सागर जिला, रहली तहसील  ")
    assert out.meta["location_details"] == {"district": "Sagar", "district_hi": "सागर", "division": "Sagar", "tehsil": "रहली", "raw": "सागर जिला, रहली तहसील"}
    assert out.meta["awaiting_location_detail"] is False


# --- poststep: location detail and duration, once each ------------------------------------------------------------

def confirm_result(fields=None, service="water_supply"):
    return validator.ValidationResult(
        service_id=service, collected_fields=fields or {"issue_type": "no_supply", "location": "किलोजा"}, awaiting_confirmation=True,
        action=validator.ValidatedAction.CONFIRM, ask_for=None, reply_text=validator.CONFIRM_PROMPT_HI, summary={"x": "y"},
    )


def post(result, meta, probe=lambda spec, fields: True, lat=None, lng=None, r=None):
    return intake.poststep(result=result, pre=intake.Pre(turn(), meta), specs=SPECS, lat=lat, lng=lng, row=r or row(), weak_location=probe)


def test_poststep_does_nothing_when_intake_was_not_active():
    r = confirm_result()
    assert intake.poststep(result=r, pre=intake.Pre(turn(), None), specs=SPECS, lat=None, lng=None, row=row()) is r


def test_unclear_place_asks_district_tehsil_once_then_duration_once_then_confirms():
    meta = {"v": 2}
    first = post(confirm_result(), meta)
    assert (first.action, first.ask_for) == (validator.ValidatedAction.ASK, "location_detail") and "जिला" in first.reply_text
    assert first.collected_fields[intake.META_KEY]["awaiting_location_detail"] is True
    meta = first.collected_fields[intake.META_KEY]
    second = post(confirm_result(), meta)  # location asked already: now the duration
    assert (second.action, second.ask_for) == (validator.ValidatedAction.ASK, "duration_days")
    meta = second.collected_fields[intake.META_KEY]
    third = post(confirm_result(), meta)  # both asked: the normal confirmation goes ahead, with the notes attached
    assert third.action is validator.ValidatedAction.CONFIRM and third.collected_fields[intake.META_KEY]["asked_duration"] is True


def test_gps_or_a_clear_place_skips_the_location_question():
    assert post(confirm_result(), {}, lat=23.2, lng=77.4).ask_for == "duration_days"  # GPS: straight to duration
    assert post(confirm_result(), {}, probe=lambda s, f: False).ask_for == "duration_days"  # place resolves: straight to duration
    assert post(confirm_result(), {}, r=row(lat=23.2, lng=77.4)).ask_for == "duration_days"  # GPS shared earlier in the session


def test_a_duration_already_given_is_never_asked_again():
    fields = {"issue_type": "no_supply", "location": "किलोजा", "duration_days": 3}
    out = post(confirm_result(fields), {"asked_location_detail": True})
    assert out.action is validator.ValidatedAction.CONFIRM


def test_notes_travel_with_every_outcome_including_ready_to_submit():
    ready = confirm_result().model_copy(update={"action": validator.ValidatedAction.READY_TO_SUBMIT, "reply_text": None})
    out = post(ready, {"reason": "confident", "asked_duration": True, "asked_location_detail": True})
    assert out.action is validator.ValidatedAction.READY_TO_SUBMIT and out.collected_fields[intake.META_KEY]["reason"] == "confident"


def test_extra_questions_only_happen_at_the_confirmation_step():
    ask = confirm_result().model_copy(update={"action": validator.ValidatedAction.ASK, "ask_for": "issue_type", "reply_text": "समस्या?"})
    out = post(ask, {})
    assert out.ask_for == "issue_type" and intake.META_KEY in out.collected_fields  # the required detail still comes first


# --- the Jev client (no network: httpx mock transport) --------------------------------------------------------------

def make_client(handler):
    return jev.JevDecider("secret-key", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_client_sends_one_choice_over_all_departments_and_parses_the_answer():
    seen = {}

    def handler(request):
        seen["auth"], seen["body"] = request.headers["authorization"], __import__("json").loads(request.content)
        return httpx.Response(200, json={"answers": {"dept": {"choice": "phe", "confidence": 0.9, "probabilities": {"phe": 0.9, "energy": 0.07, "home": 0.03}},
                                                     "urgent": {"noul": 0.1}}})

    d = make_client(handler).decide({"citizen_message": "x"}, REG.departments)
    assert seen["auth"] == "Bearer secret-key" and len(seen["body"]["questions"]["dept"]["criteria"]) == 49 and seen["body"]["model"] == "jev-latest"
    assert d.top[0] == ("phe", 0.9) and len(d.top) == 3 and d.confidence == 0.9 and d.urgent == 0.1


@pytest.mark.parametrize("response", [httpx.Response(500), httpx.Response(200, json={"oops": 1}), httpx.Response(200, text="not json")])
def test_client_turns_any_failure_into_jev_unavailable(response):
    with pytest.raises(jev.JevUnavailable):
        make_client(lambda request: response).decide({}, REG.departments)
    with pytest.raises(jev.JevUnavailable):
        make_client(lambda request: response).agrees({}, "x")


def test_client_failure_logs_neither_the_text_nor_the_key(caplog):
    with caplog.at_level("WARNING"), pytest.raises(jev.JevUnavailable):
        make_client(lambda request: httpx.Response(500)).decide({"citizen_message": "मेरा नाम गुप्त है"}, REG.departments)
    assert "गुप्त" not in caplog.text and "secret-key" not in caplog.text


def test_from_env_needs_a_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jev.from_env() is None
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert isinstance(jev.from_env(), jev.JevDecider)


# --- route wiring (real validator and specs, fake Jev) -----------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    saved = {}
    monkeypatch.setattr(routes.session, "get_or_create_session", lambda sid: session.Session(
        id=sid, status=session.SessionStatus.ACTIVE, service_id=None, collected_fields={}, awaiting_confirmation=False, lat=None, lng=None,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC), last_active_at=__import__("datetime").datetime.now(__import__("datetime").UTC)))
    monkeypatch.setattr(routes.session, "find_stored_response", lambda sid, mid: None)
    monkeypatch.setattr(routes.session, "get_recent_messages", lambda sid, limit=4: [])
    monkeypatch.setattr(routes.session, "save_turn", lambda **kw: saved.update(kw))
    monkeypatch.setattr(routes.turn_engine, "run_turn", lambda **kw: turn())
    monkeypatch.setattr(intake.jev, "from_env", lambda: None)
    app = FastAPI()
    register_error_handlers(app)
    app.state.specs = SPECS
    app.include_router(routes.router, prefix="/api/v1")
    c = TestClient(app, raise_server_exceptions=False)
    c.saved = saved
    return c


def send(client, text="कुछ समस्या है"):
    sid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    return client.post("/api/v1/message", files={"session_id": (None, sid), "message_id": (None, mid), "text": (None, text)})


def test_route_unsure_asks_the_department_question_and_stores_the_notes(client, monkeypatch):
    monkeypatch.setattr(intake, "default_decider", lambda: FakeDecider(top=(("revenue", 0.5), ("general_administration", 0.4)), confidence=0.55))
    monkeypatch.setattr(routes.validator, "apply", lambda **kw: (_ for _ in ()).throw(AssertionError("validator must not run for the early question")))
    r = send(client)
    body = r.json()
    assert r.status_code == 200 and body["action"] == "ask" and body["ask_for"] == "service" and "राजस्व विभाग" in body["reply_text"]
    saved = client.saved["session_update"]
    assert saved.collected_fields[intake.META_KEY]["pending_dept"] == "revenue" and saved.service_id is None


def test_route_confident_live_department_flows_through_the_real_validator(client, monkeypatch):
    monkeypatch.setattr(intake, "default_decider", lambda: FakeDecider())
    body = send(client).json()
    assert body["action"] == "ask" and body["ask_for"] == "issue_type"  # water spec's first required detail
    saved = client.saved["session_update"]
    assert saved.service_id == "water_supply" and saved.collected_fields[intake.META_KEY]["suggested_department"]["id"] == "phe"


def test_route_confident_department_without_a_spec_lands_in_general_with_the_suggestion(client, monkeypatch):
    monkeypatch.setattr(intake, "default_decider", lambda: FakeDecider(top=(("school_education", 0.93), ("higher_education", 0.05))))
    body = send(client).json()
    assert body["action"] == "ask" and body["ask_for"] == "description"  # Human Evaluation asks for the description first
    saved = client.saved["session_update"]
    assert saved.service_id == "human_evaluation" and saved.collected_fields[intake.META_KEY]["reason"] == "department_not_live"


def test_route_flag_off_never_touches_jev(client, monkeypatch):
    monkeypatch.setenv("INTAKE_V2", "")
    monkeypatch.setattr(intake, "default_decider", lambda: (_ for _ in ()).throw(AssertionError("Jev must not be created")))
    assert send(client).status_code == 200


def test_the_llm_prompt_never_contains_the_internal_notes():
    prompt = turn_engine._build_prompt(
        turn_engine.SessionState("water_supply", {"issue_type": "no_supply", intake.META_KEY: {"pending_dept": "energy"}}, False), SPECS, "x", None, None, [])
    assert "no_supply" in prompt and "pending_dept" not in prompt and intake.META_KEY not in prompt
