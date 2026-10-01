from dashboard.labels import intake_notes


def test_old_tickets_have_no_notes():
    assert intake_notes(None) == [] and intake_notes({}) == [] and intake_notes("junk") == []


def test_notes_are_readable_and_complete():
    lines = intake_notes({
        "reason": "department_unconfirmed", "suggested_department": {"id": "energy", "name_en": "Energy", "name_hi": "ऊर्जा विभाग"},
        "jev": [{"id": "energy", "p": 0.55}, {"id": "finance", "p": 0.4}], "questions_asked": 1, "location_details": {"district": "Sagar", "tehsil": "रहली"},
    })
    text = "\n".join(lines)
    assert "needs a person" in text and "Energy (ऊर्जा विभाग)" in text and "energy 55%, finance 40%" in text
    assert "questions asked:** 1" in text and "district Sagar, tehsil रहली" in text


def test_unknown_reason_is_shown_as_is_and_missing_parts_are_skipped():
    assert intake_notes({"reason": "something_new"}) == ["**Why:** something_new"]
    assert intake_notes({"jev": "not a list", "suggested_department": "x"}) == []
