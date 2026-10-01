import pandas as pd

from dashboard.cm import ui


def test_labels_are_capitals_with_spaces():
    assert ui.label("avg_days_to_resolve") == "AVG DAYS TO RESOLVE"
    assert ui.label("complaint_id") == "COMPLAINT ID" and ui.label("district") == "DISTRICT"


def test_table_shows_capital_column_names_and_hides_a_plain_index(monkeypatch):
    seen = {}
    monkeypatch.setattr(ui.st, "dataframe", lambda data, **kw: seen.update(data=data, kw=kw) or "event")
    df = pd.DataFrame({"complaint_id": ["a"], "eval_reason": ["x"]})
    assert ui.table(df, key="k") == "event"
    assert list(seen["data"].columns) == ["COMPLAINT ID", "EVAL REASON"] and list(df.columns) == ["complaint_id", "eval_reason"]  # original untouched
    assert seen["kw"]["hide_index"] is True and seen["kw"]["width"] == "stretch" and seen["kw"]["key"] == "k"


def test_a_named_index_is_kept_and_styler_headers_are_capitalised(monkeypatch):
    seen = {}
    monkeypatch.setattr(ui.st, "dataframe", lambda data, **kw: seen.update(data=data, kw=kw))
    heat = pd.DataFrame({"jal_vibhag": [1, 2]}, index=pd.Index(["Sagar", "Rewa"], name="district"))
    ui.table(heat)
    assert seen["kw"]["hide_index"] is False  # district names live in the index: do not hide them
    ui.table(heat.style.map(lambda v: "color:red"))
    html = seen["data"].to_html()
    assert "JAL VIBHAG" in html and "jal_vibhag" not in html
