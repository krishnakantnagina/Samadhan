"""Row selection in the ticket tables, made safe when the list changes underneath it.

Streamlit remembers a selection as a ROW POSITION under the widget's key. If a filter shrinks or reorders the table
while a row is selected, the old position can be past the end (IndexError, the crash reported 30 Sep) or point at a
different ticket (a silently wrong detail panel). Two guards, both pure so they can be unit tested:

* `table_key` changes whenever the set or order of tickets in the table changes, so a stale selection is dropped.
* `selected_row` never indexes out of range.
"""

import hashlib
from typing import Any

import pandas as pd


def table_key(base: str, df: pd.DataFrame) -> str:
    """`base` plus a short digest of the complaint IDs in order: a new list means a new widget, so no stale selection."""
    ids = "|".join(str(i) for i in df["complaint_id"])
    return f"{base}-{hashlib.sha1(ids.encode('utf-8')).hexdigest()[:10]}"


def selected_row(df: pd.DataFrame, rows: list[int]) -> Any | None:
    """The selected row, or None if nothing is selected or the position is not in `df`."""
    if not rows:
        return None
    position = rows[0]
    return df.iloc[position] if 0 <= position < len(df) else None
