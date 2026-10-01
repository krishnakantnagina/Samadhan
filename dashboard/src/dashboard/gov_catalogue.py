"""MP government service catalogue for the "Govt Structure" tab.

Reads the scraped CSVs in `local-research/data/` (git-excluded, so it exists only on machines that
were given the folder). When the files are missing the tab shows a hint instead of failing.
Sources: mp.gov.in/services (2,070 services, 45 departments, 12 categories) and
cmhelpline.mp.gov.in (362 schemes, 28 departments). The two sites name departments differently.
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "local-research" / "data"


def load_services(data_dir: Path = DATA_DIR) -> pd.DataFrame | None:
    """Every service on mp.gov.in/services, or None if the research file is not on this machine."""
    path = data_dir / "mp_gov_services.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, encoding="utf-8-sig").fillna("")


def load_schemes(data_dir: Path = DATA_DIR) -> pd.DataFrame | None:
    path = data_dir / "cmhelpline_schemes.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, encoding="utf-8-sig").fillna("")


def department_coverage(services: pd.DataFrame, live_departments: set[str]) -> pd.DataFrame:
    """Per catalogue department: services listed, categories, services with an apply link, and whether
    Samadhan handles it yet. `live_departments` are the department names in our own tickets/offices;
    the match is on exact text, so it will say 'catalogued only' until names are mapped (see
    docs/ARCHITECTURE_DEPARTMENTS.md). The catalogue is in Hindi, our departments in English/Hinglish."""
    g = services[services["department"] != ""].groupby("department")
    out = pd.DataFrame(
        {
            "services": g.size(),
            "categories": g["category"].nunique(),
            "with_apply_link": g["apply_url"].apply(lambda s: int((s != "").sum())),
        }
    ).reset_index()
    out["samadhan_status"] = out["department"].map(lambda d: "live" if d in live_departments else "catalogued only")
    return out.sort_values("services", ascending=False, ignore_index=True)
