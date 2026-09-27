"""S07 Validator (T15): every branch against hand-built specs -- no I/O, no fakes needed."""

from app.service_spec import ServiceSpec
from app.turn_engine import TurnResult
from app.validator import (
    GPS_LOCATION_LABEL_HI,
    SessionSnapshot,
    ValidatedAction,
    apply,
)

SPEC = ServiceSpec.model_validate(
    {
        "spec_version": 1,
        "service": "water_supply",
        "department": "Jal Vibhag",
        "label": {"hi": "पानी", "en": "Water"},
        "recognise": ["no water"],
        "out_of_scope": {
            "examples": ["electricity"],
            "reply": {"hi": "क्षमा करें, यह सेवा उपलब्ध नहीं है।", "en": "Sorry, not supported."},
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
                    {"value": "no_supply", "hi": "पानी नहीं आ रहा", "en": "No water"},
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
            {
                "name": "duration_days",
                "type": "integer",
                "required": False,
                "min": 0,
                "max": 365,
                "label": {"hi": "कितने दिनों से", "en": "Days affected"},
            },
        ],
    }
)
SPECS = {SPEC.service: SPEC}


def session(**overrides) -> SessionSnapshot:
    base = {
        "service_id": None,
        "collected_fields": {},
        "awaiting_confirmation": False,
        "lat": None,
        "lng": None,
    }
    base.update(overrides)
    return SessionSnapshot(**base)


def turn_result(**overrides) -> TurnResult:
    base = {"service_id": "water_supply", "fields": {}, "confirmed": False}
    base.update(overrides)
    return TurnResult(**base)


# --- ask -----------------------------------------------------------------------------------


def test_missing_required_field_asks():
    result = apply(specs=SPECS, session=session(), turn_result=turn_result(), lat=None, lng=None)

    assert result.action == ValidatedAction.ASK
    assert result.ask_for == "issue_type"
    assert result.reply_text == "क्या समस्या है?"
    assert result.awaiting_confirmation is False


def test_location_missing_asks_for_location():
    result = apply(
        specs=SPECS,
        session=session(collected_fields={"issue_type": "no_supply"}),
        turn_result=turn_result(),
        lat=None,
        lng=None,
    )

    assert result.action == ValidatedAction.ASK
    assert result.ask_for == "location"


# --- confirm / ready_to_submit --------------------------------------------------------------


def test_all_fields_in_one_turn_goes_straight_to_confirm():
    result = apply(
        specs=SPECS,
        session=session(),
        turn_result=turn_result(fields={"issue_type": "no_supply", "location": "Ward 12"}),
        lat=None,
        lng=None,
    )

    assert result.action == ValidatedAction.CONFIRM
    assert result.awaiting_confirmation is True
    assert result.summary == {"issue_type": "पानी नहीं आ रहा", "location": "Ward 12"}


def test_gps_satisfies_location_without_a_place_name():
    result = apply(
        specs=SPECS,
        session=session(collected_fields={"issue_type": "no_supply"}),
        turn_result=turn_result(),
        lat=23.25,
        lng=77.41,
    )

    assert result.action == ValidatedAction.CONFIRM
    assert result.summary["location"] == GPS_LOCATION_LABEL_HI


def test_gps_from_a_previous_turn_still_satisfies_location():
    result = apply(
        specs=SPECS,
        session=session(collected_fields={"issue_type": "no_supply"}, lat=23.25, lng=77.41),
        turn_result=turn_result(),
        lat=None,
        lng=None,
    )

    assert result.action == ValidatedAction.CONFIRM
    assert result.summary["location"] == GPS_LOCATION_LABEL_HI


def test_correction_at_confirmation_stays_confirm_not_ready():
    result = apply(
        specs=SPECS,
        session=session(
            collected_fields={"issue_type": "no_supply", "location": "Ward 12"},
            awaiting_confirmation=True,
        ),
        turn_result=turn_result(fields={"location": "Ward 24"}, confirmed=False),
        lat=None,
        lng=None,
    )

    assert result.action == ValidatedAction.CONFIRM
    assert result.summary["location"] == "Ward 24"


def test_confirmed_turn_reaches_ready_to_submit():
    result = apply(
        specs=SPECS,
        session=session(
            collected_fields={"issue_type": "no_supply", "location": "Ward 12"},
            awaiting_confirmation=True,
        ),
        turn_result=turn_result(confirmed=True),
        lat=None,
        lng=None,
    )

    assert result.action == ValidatedAction.READY_TO_SUBMIT
    assert result.reply_text is None
    assert result.awaiting_confirmation is False


# --- dropped/invalid values ------------------------------------------------------------------


def test_invalid_enum_value_is_dropped_field_stays_missing():
    result = apply(
        specs=SPECS,
        session=session(),
        turn_result=turn_result(fields={"issue_type": "electricity"}),
        lat=None,
        lng=None,
    )

    assert result.action == ValidatedAction.ASK
    assert result.ask_for == "issue_type"
    assert "issue_type" not in result.collected_fields


def test_invalid_value_does_not_erase_existing_valid_one():
    result = apply(
        specs=SPECS,
        session=session(collected_fields={"issue_type": "no_supply"}),
        turn_result=turn_result(fields={"issue_type": "not_a_real_value"}),
        lat=None,
        lng=None,
    )

    assert result.collected_fields["issue_type"] == "no_supply"


def test_integer_field_rejects_bool():
    result = apply(
        specs=SPECS,
        session=session(collected_fields={"issue_type": "no_supply", "location": "Ward 12"}),
        turn_result=turn_result(fields={"duration_days": True}),
        lat=None,
        lng=None,
    )

    assert "duration_days" not in result.collected_fields


def test_enum_summary_shows_localized_label_not_raw_value():
    result = apply(
        specs=SPECS,
        session=session(collected_fields={"issue_type": "no_supply", "location": "Ward 12"}),
        turn_result=turn_result(confirmed=False),
        lat=None,
        lng=None,
    )

    assert result.summary["issue_type"] == "पानी नहीं आ रहा"


# --- out_of_scope ----------------------------------------------------------------------------


def test_out_of_scope_preserves_session_state():
    existing = {"issue_type": "no_supply"}
    result = apply(
        specs=SPECS,
        session=session(
            service_id="water_supply", collected_fields=existing, awaiting_confirmation=True
        ),
        turn_result=turn_result(service_id=None, fields={}),
        lat=None,
        lng=None,
    )

    assert result.action == ValidatedAction.OUT_OF_SCOPE
    assert result.service_id == "water_supply"
    assert result.collected_fields == existing
    assert result.awaiting_confirmation is True


def test_out_of_scope_before_any_service_identified():
    result = apply(
        specs=SPECS, session=session(), turn_result=turn_result(service_id=None), lat=None, lng=None
    )

    assert result.action == ValidatedAction.OUT_OF_SCOPE
    assert result.service_id is None
    assert result.reply_text == "क्षमा करें, यह सेवा उपलब्ध नहीं है।"
