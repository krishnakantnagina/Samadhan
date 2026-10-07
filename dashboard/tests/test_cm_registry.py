import csv
import json

import pytest

from dashboard.cm import registry as R
from dashboard.cm.departments import ALL_DEPARTMENTS, DEPARTMENTS, EXTRA_DEPARTMENTS


def test_department_lists_are_consistent():
    assert len(DEPARTMENTS) == 45 and len(EXTRA_DEPARTMENTS) == 4
    assert len({d[0] for d in ALL_DEPARTMENTS}) == 49  # unique ids
    assert len({R.norm_hi(d[2]) for d in ALL_DEPARTMENTS}) == 49  # distinct after normalisation, so matching is unambiguous


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ऊर्जा विभाग", "energy"),
        ("ऊर्जा, मध्यप्रदेश", "energy"),  # mpedistrict style suffix
        ("तकनिकी शिक्षा,कौशल विकास एवं रोजगार विभाग", "technical_education_skill_employment"),  # typo in CM Helpline
        ("सामाजिक न्याय एवं दिव्यांगजन सशक्तिकरण विभाग", "social_justice_disabled"),  # renamed department
        ("आदिम जाति कल्याण , मध्यप्रदेश", "tribal_affairs"),  # reviewed manual alias
        ("मछुआ कल्याण एवं मत्स्य विकास विभाग", "fisheries"),  # extra (not in the official 45)
    ],
)
def test_department_name_matching(raw, expected):
    assert R.match_department(raw)[0] == expected


def test_unrelated_or_empty_names_do_not_match():
    assert R.match_department("") is None
    assert R.match_department("क्रिकेट संघ") is None


@pytest.fixture
def data_dir(tmp_path):
    (tmp_path / "geography").mkdir()
    (tmp_path / "mpedistrict").mkdir()
    with open(tmp_path / "mp_gov_services.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["title", "category", "department", "apply_url"])
        w.writerow(["बिजली कनेक्शन", "ऊर्जा", "ऊर्जा विभाग", "http://x"])
        w.writerow(["अजीब सेवा", "अन्य", "अज्ञात विभाग", ""])
    (tmp_path / "mpedistrict" / "services.jsonl").write_text(
        json.dumps({"service": "मीटर", "department": "ऊर्जा, मध्यप्रदेश", "deadline_urban": "5 कार्य दिवस", "deadline_rural": "5 कार्य दिवस",
                    "fee_lsk": "20/-", "documents": ["आधार"], "online_link": "", "detail_url": "http://d"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (tmp_path / "geography" / "divisions.csv").write_text("division,std_code\nBhopal,0755\n", encoding="utf-8")
    (tmp_path / "geography" / "districts.csv").write_text(
        "division,district,std_code,area_sq_km,population_2011,headquarters,district_email\nBhopal,Bhopal,0755,2772,2371061,Bhopal,dmbhopal@nic.in\n"
        "Bhopal,Sehore,07562,6578,1311008,Sehore,dmsehore@nic.in\n", encoding="utf-8")
    return tmp_path


LIVE = [{"id": 1, "department": "Bijli Vibhag", "level": "ward", "name": "मिसरोद", "office_name": "Ward Bijli", "active": True},
        {"id": 2, "department": "Human Evaluation", "level": "district", "name": "Bhopal", "office_name": "Desk", "active": True},
        {"id": 3, "department": "Bijli Vibhag", "level": "district", "name": "Bhopal", "office_name": "Bijli District", "active": True}]


def test_build_loads_everything_and_reports_unmatched(data_dir, tmp_path):
    conn = R.connect(tmp_path / "r.db")
    s = R.build(conn, data_dir, LIVE)
    assert s["mp.gov.in"] == 2 and s["mpedistrict"] == 1 and s["districts"] == 2 and s["offices_from_supabase"] == 3
    assert "अज्ञात विभाग" in s["unmatched_departments"]["mp.gov.in"]
    ov = {d["id"]: d for d in R.departments_overview(conn)}
    assert ov["energy"]["services_mp"] == 1 and ov["energy"]["services_mped"] == 1 and ov["energy"]["offices"] == 2
    assert ov["energy"]["status"] == "demo" and ov["revenue"]["status"] == "demo"  # every registry department has a generated spec and DEMO offices now (migration 004)
    svc = R.department_services(conn, "energy", "mpedistrict")[0]
    assert svc["deadline_urban"] == "5 कार्य दिवस" and svc["documents"] == ["आधार"]


def test_rebuild_keeps_manual_edits_and_audit(data_dir, tmp_path):
    conn = R.connect(tmp_path / "r.db")
    R.build(conn, data_dir, LIVE)
    R.set_department(conn, "revenue", status="planned", notes="pilot in Q1", actor="cm.office")
    oid = R.add_office(conn, dept_id="revenue", level="district", district="Sehore", name="Sehore Revenue Office", status="unverified", notes="", actor="cm.office")
    R.build(conn, data_dir, LIVE)  # rebuild
    ov = {d["id"]: d for d in R.departments_overview(conn)}
    assert ov["revenue"]["status"] == "planned" and ov["revenue"]["notes"] == "pilot in Q1" and ov["revenue"]["offices"] == 1
    log = R.rows(conn, "SELECT actor, action FROM audit_log ORDER BY id")
    assert [(r["actor"], r["action"]) for r in log] == [("cm.office", "department.update"), ("cm.office", "office.add")]
    R.delete_office(conn, oid, actor="cm.office")
    assert R.departments_overview(conn)[0] is not None


def test_only_manual_offices_can_be_deleted_and_inputs_are_validated(data_dir, tmp_path):
    conn = R.connect(tmp_path / "r.db")
    R.build(conn, data_dir, LIVE)
    supabase_office = R.rows(conn, "SELECT id FROM offices WHERE source='supabase'")[0]["id"]
    with pytest.raises(ValueError):
        R.delete_office(conn, supabase_office, actor="x")
    with pytest.raises(ValueError):
        R.add_office(conn, dept_id="energy", level="galaxy", district=None, name="x", status="demo", notes="", actor="x")
    with pytest.raises(ValueError):
        R.add_office(conn, dept_id="energy", level="ward", district=None, name="  ", status="demo", notes="", actor="x")
    with pytest.raises(ValueError):
        R.set_department(conn, "energy", status="bogus", notes="", actor="x")
    with pytest.raises(KeyError):
        R.set_department(conn, "nope", status="live", notes="", actor="x")


def test_coverage_matrix_never_invents_an_office(data_dir, tmp_path):
    conn = R.connect(tmp_path / "r.db")
    R.build(conn, data_dir, LIVE)
    m = {r["dept_id"]: r for r in R.coverage_matrix(conn)}
    assert m["energy"]["Bhopal"] == "demo"  # the one real (demo) office
    assert m["energy"]["Sehore"] == "not onboarded"
    assert m["revenue"]["Bhopal"] == "not onboarded"
