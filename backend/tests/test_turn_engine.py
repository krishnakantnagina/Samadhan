"""S05 Turn Engine (T12): fallback sequencing, structural validation, GPS shortcut, confirmed
forcing -- all against fake providers, no network and no real API keys. Extraction correctness
against real Hindi/Hinglish text is T13's job, not this file's (docs/plans/T12-plan.md section 3).
"""

import json

import pytest

from app.service_spec import ServiceSpec
from app.turn_engine import (
    Message,
    SessionState,
    TurnEngineUnavailable,
    TurnResult,
    _build_prompt,
    _ProviderError,
    run_turn,
)


def make_spec(service: str = "water_supply") -> ServiceSpec:
    return ServiceSpec.model_validate(
        {
            "spec_version": 1,
            "service": service,
            "department": "Jal Vibhag",
            "label": {"hi": "पानी", "en": "Water"},
            "recognise": ["no water"],
            "out_of_scope": {
                "examples": ["electricity"],
                "reply": {"hi": "क्षमा करें", "en": "Sorry"},
            },
            "pilot": {"city": "Bhopal", "wards": 5},
            "routing": {
                "min_confidence": 0.7,
                "fallback_level": "district",
                "fallback_status": "needs_review",
                "max_match_distance_km": 5,
            },
            "confirmation": "required",
            "fields": [
                {
                    "name": "issue_type",
                    "type": "enum",
                    "required": True,
                    "label": {"hi": "समस्या", "en": "Issue"},
                    "question": {"hi": "क्या समस्या है?", "en": "What is the problem?"},
                    "values": [
                        {"value": "no_supply", "hi": "पानी नहीं", "en": "No water"},
                        {"value": "leakage", "hi": "लीकेज", "en": "Leakage"},
                    ],
                },
                {
                    "name": "location",
                    "type": "location",
                    "required": True,
                    "label": {"hi": "स्थान", "en": "Location"},
                    "question": {"hi": "स्थान बताइए", "en": "Where?"},
                    "accepts": {
                        "gps": {"lat": [-90, 90], "lng": [-180, 180]},
                        "place_name": {"min_length": 2, "max_length": 100},
                    },
                },
            ],
        }
    )


SPEC = make_spec()
SPECS = {SPEC.service: SPEC}


def session(**overrides) -> SessionState:
    base = {"service_id": None, "collected_fields": {}, "awaiting_confirmation": False}
    base.update(overrides)
    return SessionState(**base)


class FakeProvider:
    """A Provider that returns a canned response (or raises) and counts calls."""

    def __init__(self, name: str, response: str | None = None, error: Exception | None = None):
        self.name = name
        self._response = response
        self._error = error
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class NeverCalledProvider:
    name = "never"

    def complete(self, prompt: str) -> str:
        raise AssertionError("provider must not be called")


def valid_json(
    service_id: str | None = "water_supply", fields: dict | None = None, confirmed=False
):
    return json.dumps({"service_id": service_id, "fields": fields or {}, "confirmed": confirmed})


# --- GPS-only shortcut (D-S05-1) --------------------------------------------------------------


@pytest.mark.parametrize("text", [None, "", "   "])
def test_gps_only_turn_never_calls_a_provider(text):
    result = run_turn(
        session=session(service_id="water_supply"),
        specs=SPECS,
        text=text,
        lat=23.25,
        lng=77.41,
        providers=[NeverCalledProvider()],
    )
    assert result == TurnResult(service_id="water_supply", fields={}, confirmed=False)


# --- S25: acknowledgement line passes through, untrusted --------------------------------------


def _run_with_raw(raw: str) -> TurnResult:
    return run_turn(
        session=session(),
        specs=SPECS,
        text="paani nahi aa raha",
        lat=None,
        lng=None,
        providers=[FakeProvider("groq", response=raw)],
    )


def test_ack_is_carried_on_the_result():
    raw = json.dumps(
        {"service_id": "water_supply", "fields": {}, "confirmed": False, "ack": "समझ गया।"}
    )
    assert _run_with_raw(raw).ack == "समझ गया।"


def test_missing_or_non_string_ack_becomes_none_not_an_error():
    base = {"service_id": "water_supply", "fields": {}, "confirmed": False}
    assert _run_with_raw(json.dumps(base)).ack is None
    assert _run_with_raw(json.dumps({**base, "ack": 12345})).ack is None
    assert _run_with_raw(json.dumps({**base, "ack": ["x"]})).ack is None


def test_prompt_states_the_ack_rules():
    prompt = _build_prompt(session(), SPECS, "paani nahi aa raha", None, None, [])
    assert '"ack"' in prompt and "NEW information" in prompt


# --- Fallback sequencing -----------------------------------------------------------------------


def test_primary_success_skips_fallback():
    groq = FakeProvider("groq", response=valid_json(fields={"issue_type": "no_supply"}))
    gemini = NeverCalledProvider()

    result = run_turn(
        session=session(),
        specs=SPECS,
        text="paani nahi aa raha",
        lat=None,
        lng=None,
        providers=[groq, gemini],
    )

    assert result.service_id == "water_supply"
    assert result.fields == {"issue_type": "no_supply"}
    assert groq.calls == 1


def test_primary_failure_calls_fallback_once():
    groq = FakeProvider("groq", error=_ProviderError("timeout"))
    gemini = FakeProvider("gemini", response=valid_json(fields={"issue_type": "leakage"}))

    result = run_turn(
        session=session(),
        specs=SPECS,
        text="pipe leak",
        lat=None,
        lng=None,
        providers=[groq, gemini],
    )

    assert result.fields == {"issue_type": "leakage"}
    assert groq.calls == 1
    assert gemini.calls == 1


def test_malformed_json_treated_as_failure():
    groq = FakeProvider("groq", response="not json at all")
    gemini = FakeProvider("gemini", response=valid_json())

    run_turn(
        session=session(), specs=SPECS, text="hi", lat=None, lng=None, providers=[groq, gemini]
    )

    assert groq.calls == 1
    assert gemini.calls == 1


def test_hallucinated_service_id_treated_as_failure():
    groq = FakeProvider("groq", response=valid_json(service_id="electricity"))
    gemini = FakeProvider("gemini", response=valid_json(service_id="water_supply"))

    result = run_turn(
        session=session(), specs=SPECS, text="hi", lat=None, lng=None, providers=[groq, gemini]
    )

    assert result.service_id == "water_supply"
    assert groq.calls == 1
    assert gemini.calls == 1


def test_both_fail_raises_unavailable_no_third_attempt():
    groq = FakeProvider("groq", error=_ProviderError("down"))
    gemini = FakeProvider("gemini", error=_ProviderError("down"))

    with pytest.raises(TurnEngineUnavailable):
        run_turn(
            session=session(), specs=SPECS, text="hi", lat=None, lng=None, providers=[groq, gemini]
        )

    assert groq.calls == 1
    assert gemini.calls == 1


def test_extra_json_keys_ignored():
    payload = json.loads(valid_json(fields={"issue_type": "no_supply"}))
    payload["reasoning"] = "the citizen described no water for three days"
    groq = FakeProvider("groq", response=json.dumps(payload))
    gemini = NeverCalledProvider()

    result = run_turn(
        session=session(), specs=SPECS, text="hi", lat=None, lng=None, providers=[groq, gemini]
    )

    assert result.fields == {"issue_type": "no_supply"}


# --- confirmed forcing (D-S05-3) ----------------------------------------------------------------


def test_confirmed_forced_false_when_not_awaiting():
    groq = FakeProvider("groq", response=valid_json(confirmed=True))

    result = run_turn(
        session=session(awaiting_confirmation=False),
        specs=SPECS,
        text="haan",
        lat=None,
        lng=None,
        providers=[groq],
    )

    assert result.confirmed is False


def test_confirmed_true_when_awaiting_and_affirmed():
    groq = FakeProvider("groq", response=valid_json(confirmed=True))

    result = run_turn(
        session=session(awaiting_confirmation=True),
        specs=SPECS,
        text="haan",
        lat=None,
        lng=None,
        providers=[groq],
    )

    assert result.confirmed is True


# --- Prompt content smoke check -----------------------------------------------------------------


def test_prompt_includes_field_vocabulary_and_recent_messages():
    prompt = _build_prompt(
        session=session(service_id="water_supply", collected_fields={"issue_type": "no_supply"}),
        specs=SPECS,
        text="ward 12",
        lat=None,
        lng=None,
        recent_messages=[Message(role="citizen", text="no water since 3 days")],
    )

    assert "issue_type" in prompt
    assert "location" in prompt
    assert "no_supply" in prompt  # already-collected field surfaced in session state
    assert "no water since 3 days" in prompt  # recent message surfaced
    assert "ward 12" in prompt  # this turn's text
