"""Content for the CM-office home / login page: hero quote, public CM Helpline figures, scheme spotlight.

Real data only where it is real: the headline totals and the 362 scheme names come from cmhelpline.mp.gov.in (scraped 2026-10-01, local-research/data).
No scheme descriptions are written here: a scheme card shows the name, its department and where the official details live, nothing invented.
The quotes are original lines written for this project (not attributed to anyone else). If the scraped files are missing the page still renders with
a clearly-marked fallback.
"""

import csv
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from dashboard.cm import registry as R

QUOTES: list[tuple[str, str]] = [  # (English, Hindi), original, each carries the project name
    ("Samadhan: a solution begins the moment someone is heard.", "समाधान: समाधान वहीं शुरू होता है, जहाँ किसी की बात सुनी जाती है।"),
    ("Every village, every dialect, one Samadhan.", "हर गाँव, हर बोली, एक समाधान।"),
    ("Speak in your own words. Samadhan finds the right door.", "अपनी बोली में बोलिए। समाधान सही दरवाज़ा ढूँढ लेगा।"),
    ("When a complaint reaches the right desk, a problem becomes a Samadhan.", "जब शिकायत सही मेज़ तक पहुँचती है, तब समस्या समाधान बन जाती है।"),
    ("Good governance is listening at scale. Samadhan counts every voice.", "सुशासन का मतलब है बड़े पैमाने पर सुनना। समाधान हर आवाज़ गिनता है।"),
    ("No complaint lost, no citizen turned away: that is what Samadhan aims for.", "कोई शिकायत खोए नहीं, कोई नागरिक लौटे नहीं: समाधान का यही लक्ष्य है।"),
    ("The distance between a village and a department should be one message. Samadhan.", "गाँव और विभाग के बीच की दूरी बस एक संदेश की हो। समाधान।"),
]
FEATURED = ["प्रधानमंत्री आवास योजना", "जननी सुरक्षा योजना", "कन्या विवाह/निकाह योजना", "लाडली लक्ष्मी योजना"]  # the four CM Helpline itself features on its home page
FALLBACK = {"registered": None, "resolved": None, "schemes": [], "departments": 0}
SCHEME_PAGE = "https://cmhelpline.mp.gov.in/SchemeDashboard.aspx"


@dataclass
class HomeData:
    registered: int | None = None
    resolved: int | None = None
    schemes: list[dict] = field(default_factory=list)
    by_department: list[tuple[str, int]] = field(default_factory=list)
    source_note: str = ""

    @property
    def resolution_rate(self) -> float | None:
        return round(self.resolved / self.registered * 100, 1) if self.registered and self.resolved else None


def indian(n: int) -> str:
    """4,01,00,547 style grouping used in India."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def load(data_dir: Path = R.DATA_DIR) -> HomeData:
    d = HomeData()
    overview = data_dir / "cmhelpline_overview.json"
    if overview.exists():
        h = json.loads(overview.read_text(encoding="utf-8")).get("headline", {})
        d.registered, d.resolved = h.get("कुल दर्ज शिकायतें"), h.get("कुल निराकृत शिकायतें")
        d.source_note = "Public CM Helpline 181 totals as scraped on 1 Oct 2026 from cmhelpline.mp.gov.in. Not Samadhan's own data."
    schemes = data_dir / "cmhelpline_schemes.csv"
    if schemes.exists():
        d.schemes = list(csv.DictReader(schemes.open(encoding="utf-8-sig")))
        counts: dict[str, int] = {}
        for s in d.schemes:
            counts[s["department"]] = counts.get(s["department"], 0) + 1
        d.by_department = sorted(counts.items(), key=lambda kv: -kv[1])
    return d


def pick_quote(seed: int) -> tuple[str, str]:
    return QUOTES[seed % len(QUOTES)]


def spotlight(d: HomeData, n: int = 4, seed: int = 0) -> list[dict]:
    """n real schemes: the ones CM Helpline features first (if present in the data), then a seeded random draw so the page changes per visit."""
    by_name = {s["scheme"]: s for s in d.schemes}
    chosen = [by_name[name] for name in FEATURED if name in by_name][:n]
    rest = [s for s in d.schemes if s not in chosen]
    random.Random(seed).shuffle(rest)
    return (chosen + rest)[:n] if d.schemes else [{"scheme": name, "department": "", "url": SCHEME_PAGE} for name in FEATURED][:n]
