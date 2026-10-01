import pandas as pd
import pytest

from dashboard.cm import registry as R
from dashboard.cm import search as S

LIVE = [{"id": 1, "department": "Bijli Vibhag", "level": "ward", "name": "मिसरोद", "office_name": "Ward Misrod Bijli Office", "active": True}]


@pytest.fixture
def index(tmp_path):
    import csv
    import json

    d = tmp_path / "data"
    (d / "geography").mkdir(parents=True)
    (d / "mpedistrict").mkdir()
    with open(d / "mp_gov_services.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["title", "category", "department", "apply_url"])
        w.writerow(["नवीन बिजली कनेक्शन", "ऊर्जा", "ऊर्जा विभाग", ""])
        w.writerow(["जाति प्रमाण पत्र", "प्रमाणपत्र", "सामान्य प्रशासन विभाग", ""])
        w.writerow(["हैंडपंप सुधार", "जल", "लोक स्वास्थ्य यांत्रिकी विभाग", ""])
    (d / "mpedistrict" / "services.jsonl").write_text(json.dumps({"service": "विवादित बिजली बिल की शिकायत", "department": "ऊर्जा, मध्यप्रदेश", "deadline_urban": "5 कार्य दिवस",
        "deadline_rural": "5 कार्य दिवस", "fee_lsk": "", "documents": [], "online_link": "", "detail_url": ""}, ensure_ascii=False) + "\n", encoding="utf-8")
    with open(d / "cmhelpline_schemes.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["department_id", "department", "scheme_id", "scheme", "url"])
        w.writerow(["1", "सामान्‍य प्रशासन विभाग", "9", "लाडली लक्ष्मी योजना", ""])
    (d / "geography" / "divisions.csv").write_text("division,std_code\nSagar,0758\n", encoding="utf-8")
    (d / "geography" / "districts.csv").write_text("division,district,std_code,area_sq_km,population_2011,headquarters,district_email\nSagar,Sagar,07582,10252,2378295,Sagar,x@nic.in\n", encoding="utf-8")
    conn = R.connect(tmp_path / "r.db")
    R.build(conn, d, LIVE)
    return S.build_index(conn)


def titles(res, kind):
    return [h.entry.title for h in res.get(kind, [])]


def test_english_roman_and_hindi_words_find_the_same_things(index):
    for q in ("electricity", "bijli", "बिजली", "power connection", "new connection"):
        res = S.search(index, q)
        assert any("बिजली" in t for t in titles(res, "service")), q
        if " " not in q:  # the department itself has no word "connection", so only single words must reach it
            assert "Energy" in titles(res, "department"), q


def test_prefix_and_typo_matching(index):
    assert "Energy" in titles(S.search(index, "electr"), "department")
    assert "Energy" in titles(S.search(index, "electrcity"), "department")  # typo
    assert S.search(index, "qwertyzz") == {}


def test_all_words_must_match(index):
    assert titles(S.search(index, "बिजली बिल"), "service") == ["विवादित बिजली बिल की शिकायत"]
    assert S.search(index, "बिजली लाडली") == {}


def test_each_kind_is_searchable_and_deadline_is_shown(index):
    assert "लाडली लक्ष्मी योजना" in titles(S.search(index, "ladli लक्ष्मी"), "scheme")
    assert "Sagar" in titles(S.search(index, "sagar"), "district")
    assert "मिसरोद" not in "".join(titles(S.search(index, "zzz"), "office"))
    svc = S.search(index, "बिल")["service"][0].entry
    assert "5 कार्य दिवस" in svc.subtitle
    assert "हैंडपंप सुधार" in titles(S.search(index, "water"), "service")  # synonym water -> handpump


def test_tickets_exact_id_wins_and_scope_is_respected():
    df = pd.DataFrame({"complaint_id": ["SMD-0007", "SMD-0070"], "department": ["Jal Vibhag", "Bijli Vibhag"], "status": ["new", "new"],
                       "summary_en": ["Issue: No water", "Issue: Power cut"], "office_name": ["o", "o"]})
    entries = S.ticket_entries(df)
    res = S.search(entries, "SMD-0007")
    assert res["ticket"][0].entry.title == "SMD-0007" and res["ticket"][0].score == 100.0
    assert titles(S.search(entries, "power"), "ticket") == ["SMD-0070"]
    assert S.ticket_entries(pd.DataFrame()) == []


def test_role_visibility(index):
    energy = next(e for e in index if e.kind == "department" and e.title == "Energy")
    revenue = next(e for e in index if e.kind == "department" and e.title == "Revenue")
    assert S.visible(energy, "dept_head", "energy") and not S.visible(revenue, "dept_head", "energy")
    assert S.visible(revenue, "cm_admin", None)
    assert "department" not in S.allowed_kinds("office_officer") and "ticket" in S.allowed_kinds("office_officer")
    assert S.allowed_kinds("unknown-role") == ()


def test_hindi_words_are_not_split_into_fragments():
    """Regression: matras/virama are combining marks; stripping them as punctuation broke every Devanagari word."""
    assert S.words("जाति प्रमाण-पत्र, हैंडपंप!") == ["जाति", "प्रमाण", "पत्र", "हैंडपंप"]
    assert S.words("SMD-0007 / Ward_52") == ["smd", "0007", "ward", "52"]
