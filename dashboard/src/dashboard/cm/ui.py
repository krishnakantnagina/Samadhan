"""Small UI helpers shared by every table in the CM-office system.

Column headers are drawn on a canvas by Streamlit's grid, so CSS cannot change their case; instead every table goes through `table()`, which shows
the column names in CAPITALS (underscores become spaces). Border and header colours come from the theme in .streamlit/config.toml.
"""

import pandas as pd
import streamlit as st


def label(name) -> str:
    return str(name).replace("_", " ").upper()


def table(data, **kwargs):
    """st.dataframe with capitalised column names, full width, and the row index hidden when it is just 0..n. Accepts a DataFrame or a Styler."""
    kwargs.setdefault("width", "stretch")
    if isinstance(data, pd.DataFrame):
        shown = data.rename(columns=label)
        kwargs.setdefault("hide_index", isinstance(data.index, pd.RangeIndex))
    elif hasattr(data, "format_index"):  # pandas Styler: change the displayed header only
        shown = data.format_index(label, axis=1)
        kwargs.setdefault("hide_index", isinstance(data.data.index, pd.RangeIndex))
    else:
        shown = data
    return st.dataframe(shown, **kwargs)
