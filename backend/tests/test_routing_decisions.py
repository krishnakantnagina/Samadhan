"""S28: intent, confidence, clarify / reconfirm, general triage, service switch, urgent line.
Runs the validator against the REAL spec files (specs/*.yaml), so it also proves they work together.
No network, no fakes needed (the validator is a pure function)."""

from pathlib import Path

import pytest

from app import info_reply
from app.service_spec import load_specs
from app.turn_engine import TurnResult
from app.validator import SessionSnapshot, ValidatedAction, apply

SPECS = load_specs(Path(__file__).resolve().parents[2] / "specs")


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


def turn(**overrides) -> TurnResult:
    base = {"service_id": None, "fields": {}, "confirmed": False}
    base.update(overrides)
    return TurnResult(**base)


def run(sess=None, **turn_kwargs):
    return apply(
        specs=SPECS, session=sess or session(), turn_result=turn(**turn_kwargs), lat=None, lng=None
    )


# --- 1. the kind of message -----------------------------------------------------------------


def test_information_question_gets_the_fixed_reply_and_no_ticket_flow():
    result = run(intent="information", info_url="https://evil.example.com")

    assert result.action == ValidatedAction.OUT_OF_SCOPE
    assert result.reply_text.split("\n") == [
        info_reply.INFO_MESSAGE_HI,
        info_reply.INFO_DISCLAIMER_HI,
    ]
    assert result.summary is None and result.collected_fields == {}


def test_out_of_context_gets_the_fixed_unable_reply():
    result = run(intent="out_of_context")

    assert result.action == ValidatedAction.OUT_OF_SCOPE
    assert result.reply_text == info_reply.OUT_OF_CONTEXT_REPLY_HI


@pytest.mark.parametrize("intent", ["information", "out_of_context"])
def test_side_question_mid_complaint_leaves_the_complaint_untouched(intent):
    active = session(
        service_id="water_supply",
        collected_fields={"issue_type": "no_supply", "location": "मिसरोद"},
        awaiting_confirmation=True,
    )
    result = run(active, intent=intent)

    assert result.service_id == "water_supply"
    assert result.collected_fields == {"issue_type": "no_supply", "location": "मिसरोद"}
    assert result.awaiting_confirmation is True


def test_a_confirmation_is_never_chit_chat_even_if_mislabelled():
    """'haan' at the summary must submit, whatever intent the model attached."""
    active = session(
        service_id="water_supply",
        collected_fields={"issue_type": "no_supply", "location": "मिसरोद"},
        awaiting_confirmation=True,
    )
    result = run(active, service_id="water_supply", confirmed=True, intent="out_of_context")

    assert result.action == ValidatedAction.READY_TO_SUBMIT


def test_a_turn_that_carries_fields_is_a_complaint_even_if_mislabelled():
    result = run(service_id="electricity", fields={"issue_type": "no_power"}, intent="information")
    assert result.service_id == "electricity"
    assert result.collected_fields == {"issue_type": "no_power"}


# --- 2. confidence: route, reconfirm, clarify -----------------------------------------------


def test_confident_service_routes_straight_to_its_own_questions():
    result = run(service_id="electricity", fields={"issue_type": "no_power"}, confidence=0.95)

    assert result.action == ValidatedAction.ASK
    assert result.ask_for == "location"
    assert result.service_id == "electricity"


def test_missing_confidence_is_treated_as_confident():
    assert run(service_id="roads", fields={"issue_type": "pothole"}).ask_for == "location"


def test_fairly_sure_reconfirms_the_department_with_a_question_built_from_the_spec_label():
    result = run(service_id="electricity", fields={"issue_type": "no_power"}, confidence=0.6)

    assert result.action == ValidatedAction.ASK
    assert result.ask_for == "service"
    assert result.reply_text == f"क्या आप {SPECS['electricity'].label.hi} बता रहे हैं?"
    assert result.service_id == "electricity"  # tentative
    assert result.collected_fields == {"issue_type": "no_power"}  # nothing the citizen said is lost


def test_unsure_single_guess_is_still_reconfirmed_not_routed():
    result = run(service_id="roads", confidence=0.3)
    assert result.ask_for == "service" and "सड़क" in result.reply_text


def test_torn_between_two_departments_asks_which_one():
    result = run(candidates=["water_supply", "sanitation"])

    assert result.action == ValidatedAction.ASK and result.ask_for == "service"
    assert result.reply_text == (
        f"क्या यह {SPECS['water_supply'].label.hi} या {SPECS['sanitation'].label.hi} है?"
    )
    assert result.service_id is None


def test_three_candidates_are_listed_and_unknown_or_general_ids_are_ignored():
    result = run(candidates=["water_supply", "electricity", "roads", "human_evaluation", "nonsense"])
    labels = [SPECS[k].label.hi for k in ("water_supply", "electricity", "roads")]
    assert result.reply_text == f"क्या यह {labels[0]}, {labels[1]} या {labels[2]} है?"

    only_general = run(candidates=["human_evaluation", "nonsense"])
    assert only_general.service_id == "human_evaluation"  # nothing valid left -> Human Evaluation


def test_clarify_keeps_the_location_the_citizen_already_gave():
    result = run(candidates=["water_supply", "sanitation"], fields={"location": "मिसरोद"})
    assert result.collected_fields == {"location": "मिसरोद"}


def test_clarify_drops_a_field_that_is_not_valid_for_every_candidate():
    result = run(
        candidates=["water_supply", "roads"],
        fields={"issue_type": "no_supply", "location": "मिसरोद"},
    )
    assert result.collected_fields == {"location": "मिसरोद"}  # 'no_supply' is not a roads value


# --- 3. no department fits: general triage --------------------------------------------------


def test_a_complaint_that_fits_nothing_goes_to_general_triage_not_a_decline():
    result = run(fields={"description": "स्कूल में टीचर नहीं आते"})

    assert result.service_id == "human_evaluation"
    assert result.action == ValidatedAction.ASK and result.ask_for == "location"


def test_general_asks_for_the_description_first():
    result = run()
    assert result.service_id == "human_evaluation" and result.ask_for == "description"


def test_general_with_description_and_location_reaches_the_summary():
    result = run(fields={"description": "स्कूल में टीचर नहीं आते", "location": "मिसरोद"})

    assert result.action == ValidatedAction.CONFIRM
    assert result.summary["description"] == "स्कूल में टीचर नहीं आते"


def test_no_matching_service_mid_complaint_keeps_the_current_complaint():
    active = session(service_id="water_supply", collected_fields={"issue_type": "no_supply"})
    result = run(active)

    assert result.service_id == "water_supply" and result.ask_for == "location"


# --- 4. switching department mid-complaint ---------------------------------------------------


def test_switching_department_carries_the_location_and_drops_the_other_departments_enum():
    active = session(
        service_id="water_supply",
        collected_fields={"issue_type": "no_supply", "location": "मिसरोद"},
    )
    result = run(
        active, service_id="electricity", fields={"issue_type": "no_power"}, confidence=0.95
    )

    assert result.service_id == "electricity"
    assert result.collected_fields == {"issue_type": "no_power", "location": "मिसरोद"}
    assert result.action == ValidatedAction.CONFIRM
    assert result.summary["issue_type"] == "बिजली नहीं आ रही"  # no crash, right department's label


def test_switching_without_a_new_issue_asks_the_new_departments_own_question():
    active = session(
        service_id="water_supply",
        collected_fields={"issue_type": "no_supply", "location": "मिसरोद"},
    )
    result = run(active, service_id="roads", confidence=0.95)

    assert result.ask_for == "issue_type"
    assert result.collected_fields == {"location": "मिसरोद"}
    assert "सड़क" in result.reply_text


def test_a_switch_is_never_a_confirmation():
    active = session(
        service_id="water_supply",
        collected_fields={"issue_type": "no_supply", "location": "मिसरोद"},
        awaiting_confirmation=True,
    )
    result = run(
        active,
        service_id="electricity",
        fields={"issue_type": "no_power"},
        confirmed=True,
        confidence=0.95,
    )

    assert result.action == ValidatedAction.CONFIRM  # shown again, not submitted
    assert result.awaiting_confirmation is True


def test_the_active_service_is_sticky_even_at_low_confidence():
    active = session(service_id="water_supply", collected_fields={"issue_type": "no_supply"})
    result = run(active, service_id="water_supply", confidence=0.2)

    assert result.service_id == "water_supply" and result.ask_for == "location"


# --- 5. urgent ------------------------------------------------------------------------------


def test_urgent_adds_the_fixed_neutral_line_and_no_phone_number():
    result = run(
        service_id="electricity", fields={"issue_type": "pole_wire"}, urgent=True, confidence=0.95
    )

    assert result.reply_text.startswith(info_reply.URGENT_LINE_HI)
    assert not any(ch.isdigit() for ch in info_reply.URGENT_LINE_HI)


def test_urgent_line_also_prefixes_a_decline():
    assert run(intent="out_of_context", urgent=True).reply_text.startswith(
        info_reply.URGENT_LINE_HI
    )


# --- 6. single-service deployments behave exactly as before ---------------------------------


def test_without_a_general_spec_an_unmatched_message_is_still_a_polite_decline():
    water_only = {"water_supply": SPECS["water_supply"]}
    result = apply(
        specs=water_only, session=session(), turn_result=turn(service_id=None), lat=None, lng=None
    )

    assert result.action == ValidatedAction.OUT_OF_SCOPE
    assert result.reply_text == SPECS["water_supply"].out_of_scope.reply.hi
