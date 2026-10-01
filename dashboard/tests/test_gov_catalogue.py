import pandas as pd

from dashboard.gov_catalogue import department_coverage, load_schemes, load_services


def test_missing_research_files_return_none(tmp_path):
    assert load_services(tmp_path) is None
    assert load_schemes(tmp_path) is None


def test_load_services_reads_hindi_csv(tmp_path):
    (tmp_path / "mp_gov_services.csv").write_text(
        "title,category,department,apply_url\nजाति प्रमाण पत्र,प्रमाणपत्र,राजस्व विभाग,http://x\n", encoding="utf-8-sig"
    )
    df = load_services(tmp_path)
    assert df.loc[0, "department"] == "राजस्व विभाग"


def test_department_coverage_counts_and_live_flag():
    services = pd.DataFrame(
        {
            "title": ["a", "b", "c", "d"],
            "category": ["c1", "c2", "c1", "c1"],
            "department": ["Revenue", "Revenue", "Labour", ""],
            "apply_url": ["http://x", "", "http://y", ""],
        }
    )
    cov = department_coverage(services, {"Labour"}).set_index("department")
    assert list(cov.index) == ["Revenue", "Labour"]  # blank department dropped, biggest first
    assert cov.loc["Revenue", ["services", "categories", "with_apply_link"]].tolist() == [2, 2, 1]
    assert cov.loc["Labour", "samadhan_status"] == "live"
    assert cov.loc["Revenue", "samadhan_status"] == "catalogued only"
