"""Ticket table selection: the crash and the wrong-ticket bug when a filter changes the list."""

import pandas as pd

from dashboard.table_state import selected_row, table_key


def frame(*ids):
    return pd.DataFrame({"complaint_id": list(ids), "status": ["new"] * len(ids)})


def test_selected_row_returns_the_row_in_range():
    df = frame("SMD-0001", "SMD-0002")
    assert selected_row(df, [1])["complaint_id"] == "SMD-0002"


def test_stale_position_after_the_list_shrinks_is_ignored_not_a_crash():
    """The reported crash: row 5 was selected, then a filter left 2 rows."""
    df = frame("SMD-0001", "SMD-0002")
    assert selected_row(df, [5]) is None


def test_nothing_selected_and_negative_positions():
    df = frame("SMD-0001")
    assert selected_row(df, []) is None
    assert selected_row(df, [-1]) is None


def test_empty_table():
    assert selected_row(frame(), [0]) is None


def test_key_changes_when_the_list_changes_so_a_stale_selection_cannot_survive():
    full = frame("SMD-0001", "SMD-0002", "SMD-0003")
    filtered = frame("SMD-0002", "SMD-0003")
    assert table_key("all-tickets", full) != table_key("all-tickets", filtered)


def test_key_changes_when_only_the_order_changes():
    """Same tickets, different order: position 0 now means a different ticket."""
    assert table_key("t", frame("SMD-0001", "SMD-0002")) != table_key("t", frame("SMD-0002", "SMD-0001"))


def test_key_is_stable_for_the_same_list_and_separate_per_table():
    df = frame("SMD-0001", "SMD-0002")
    assert table_key("all-tickets", df) == table_key("all-tickets", df)
    assert table_key("all-tickets", df) != table_key("review-queue", df)
