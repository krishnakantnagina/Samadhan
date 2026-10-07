"""Issue labels per department (audit M5) and the truncation notice (audit M6)."""

from types import SimpleNamespace

import pytest

from dashboard.labels import display_field, issue_label
from dashboard.tickets import count_tickets, truncation_notice


def test_other_reads_as_that_departments_own_other():
    assert issue_label("other", "school_education") == "Other school issue"  # was "Other water issue" for every department
    assert issue_label("other", "water_supply") == "Other water issue"


def test_a_value_only_one_department_uses_needs_no_service_id():
    assert issue_label("village_works") == "Village works, drain or road"
    assert issue_label("mgnrega") == "MGNREGA work or wages not received"


def test_unknown_values_are_tidied_not_shown_raw_or_invented():
    assert issue_label("brand_new_value") == "Brand new value"
    assert issue_label(None) == "-"


def test_ambiguous_other_without_a_service_id_does_not_claim_a_department():
    assert "water" not in issue_label("other").lower()


def test_display_field_uses_the_service_for_issue_type_only():
    assert display_field("issue_type", "other", "school_education") == ("Issue", "Other school issue")
    assert display_field("location", "Kiloda", "school_education") == ("Location", "Kiloda")


def test_every_issue_type_in_every_spec_has_a_label():
    from dashboard.labels import _spec_labels

    by_service, _ = _spec_labels()
    assert len(by_service) > 140  # all departments' issue types, not just the original four
    assert all(label for label in by_service.values())


# --- truncation notice --------------------------------------------------------------------------


def test_no_notice_when_everything_is_loaded_or_the_total_is_unknown():
    assert truncation_notice(120, 120) is None
    assert truncation_notice(120, None) is None
    assert truncation_notice(500, 300) is None


def test_notice_says_how_many_of_how_many():
    text = truncation_notice(500, 1234)
    assert "500 of 1234" in text and "cover only these" in text


class _Client:
    def __init__(self, count=None, boom=False):
        self._count, self._boom = count, boom

    def table(self, _):
        return self

    def select(self, *_a, **_k):
        return self

    def limit(self, _):
        return self

    def execute(self):
        if self._boom:
            raise RuntimeError("db down")
        return SimpleNamespace(count=self._count, data=[])


def test_count_tickets_returns_the_number_or_none_never_raises():
    assert count_tickets(client=_Client(count=1234)) == 1234
    assert count_tickets(client=_Client(count=None)) is None
    assert count_tickets(client=_Client(boom=True)) is None


@pytest.mark.parametrize("value", ["other", "pothole", "village_works"])
def test_issue_label_never_raises(value):
    assert isinstance(issue_label(value, "no_such_service"), str)
