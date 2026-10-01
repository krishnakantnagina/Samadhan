import csv
import json

from dashboard.cm import home


def test_indian_number_grouping():
    assert home.indian(40100547) == "4,01,00,547"
    assert home.indian(39551910) == "3,95,51,910"
    assert home.indian(999) == "999" and home.indian(1000) == "1,000" and home.indian(123456) == "1,23,456"


def test_every_quote_carries_the_project_name_in_both_languages():
    assert len(home.QUOTES) >= 6
    for en, hi in home.QUOTES:
        assert "Samadhan" in en and "समाधान" in hi, (en, hi)
    assert home.pick_quote(0) != home.pick_quote(1) and home.pick_quote(0) == home.pick_quote(len(home.QUOTES))


def test_load_reads_real_files_and_computes_rate(tmp_path):
    (tmp_path / "cmhelpline_overview.json").write_text(json.dumps({"headline": {"कुल दर्ज शिकायतें": 100, "कुल निराकृत शिकायतें": 90}}, ensure_ascii=False), encoding="utf-8")
    with open(tmp_path / "cmhelpline_schemes.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["department_id", "department", "scheme_id", "scheme", "url"])
        for i, (dep, name) in enumerate([("A", "लाडली लक्ष्मी योजना"), ("A", "x"), ("B", "y"), ("B", "z"), ("B", "q")]):
            w.writerow([i, dep, i, name, "http://u"])
    d = home.load(tmp_path)
    assert (d.registered, d.resolved, d.resolution_rate) == (100, 90, 90.0)
    assert d.by_department[0] == ("B", 3) and len(d.schemes) == 5
    s = home.spotlight(d, n=3, seed=1)
    assert s[0]["scheme"] == "लाडली लक्ष्मी योजना" and len(s) == 3  # a featured scheme comes first
    assert home.spotlight(d, 3, seed=1) == home.spotlight(d, 3, seed=1)  # deterministic per seed


def test_missing_files_fall_back_without_crashing(tmp_path):
    d = home.load(tmp_path)
    assert d.registered is None and d.resolution_rate is None and "unavailable" in d.source_note
    assert [s["scheme"] for s in home.spotlight(d)] == home.FEATURED  # names only, nothing invented
