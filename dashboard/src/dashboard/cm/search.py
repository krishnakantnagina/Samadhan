"""Global search for the CM-office system: departments, services, schemes, districts, sub-offices and tickets, in English and Hindi.

How it matches (no external service, runs in milliseconds over ~3,000 records):
  * text is normalised (NFC, joiners removed, lower-case, punctuation -> spaces), then split into words;
  * every query word must match (AND) some word of the record by PREFIX, after expanding it with synonyms in both scripts
    (bijli = बिजली = electricity = power ...), so "bijli", "बिजली" and "electricity" find the same things;
  * a word with no match is retried as a typo (similarity >= 0.8);
  * words in the title count double; department hits get a small boost; an exact complaint id wins outright.
Results are filtered by the signed-in role (see allowed_kinds / visible), so a department head cannot search their way into another department.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from dashboard.cm import registry as R

KINDS = ("department", "service", "scheme", "district", "office", "ticket")

# Groups of equal meaning across scripts/spellings. Each group expands any member into all members.
SYNONYM_GROUPS = [
    ["electricity", "power", "bijli", "बिजली", "विद्युत", "ऊर्जा", "energy", "light", "लाइट", "meter", "मीटर"],
    ["water", "paani", "pani", "पानी", "जल", "नल", "handpump", "हैंडपंप", "पेयजल", "tap"],
    ["road", "sadak", "सड़क", "रोड", "पथ", "pothole", "गड्ढा"],
    ["ration", "राशन", "food", "खाद्य", "अनाज"],
    ["pension", "पेंशन", "वृद्धावस्था", "विधवा"],
    ["school", "स्कूल", "विद्यालय", "शिक्षा", "education", "teacher", "शिक्षक"],
    ["health", "स्वास्थ्य", "hospital", "अस्पताल", "doctor", "डॉक्टर", "medicine", "दवा", "ambulance", "एम्बुलेंस"],
    ["land", "भूमि", "जमीन", "khasra", "खसरा", "revenue", "राजस्व", "patwari", "पटवारी", "नामांतरण", "mutation"],
    ["certificate", "praman", "प्रमाण", "प्रमाणपत्र", "प्रमाण-पत्र"],
    ["caste", "जाति", "jati"],
    ["income", "आय"],
    ["domicile", "निवास", "मूल"],
    ["birth", "जन्म"],
    ["death", "मृत्यु"],
    ["marriage", "विवाह", "shaadi", "शादी", "कन्या", "निकाह"],
    ["farmer", "kisan", "किसान", "कृषि", "agriculture", "खेती", "fertiliser", "खाद", "बीज", "seed", "फसल", "crop"],
    ["police", "पुलिस", "थाना", "home", "गृह", "fir", "crime", "अपराध", "cyber", "साइबर"],
    ["garbage", "kachra", "कचरा", "सफाई", "sanitation", "drain", "नाली", "sewage", "स्वच्छ"],
    ["loan", "ऋण", "कर्ज", "credit", "साख"],
    ["scholarship", "छात्रवृत्ति", "स्कॉलरशिप"],
    ["housing", "awas", "आवास", "house", "मकान", "घर"],
    ["women", "mahila", "महिला", "child", "बाल", "anganwadi", "आंगनवाड़ी"],
    ["transport", "परिवहन", "bus", "बस", "licence", "license", "लाइसेंस", "vehicle", "वाहन"],
    ["labour", "labor", "श्रम", "मजदूर", "mazdoor", "mgnrega", "मनरेगा", "worker"],
    ["tribal", "जनजातीय", "आदिवासी", "adivasi"],
    ["forest", "वन", "जंगल"],
    ["tax", "कर", "gst", "वाणिज्यिक"],
    ["animal", "पशु", "पशुपालन", "cattle", "मवेशी", "dairy", "डेयरी"],
    ["urban", "नगरीय", "city", "शहर", "nagar", "नगर", "municipal", "नगर-निगम"],
    ["village", "गाँव", "गांव", "gram", "ग्राम", "panchayat", "पंचायत", "rural", "ग्रामीण"],
    ["connection", "कनेक्शन", "कनेक्सन"],
    ["bill", "बिल", "billing"],
    ["new", "नवीन", "नया", "नई"],
    ["complaint", "शिकायत", "grievance", "परिवाद"],
    ["application", "आवेदन", "apply"],
    ["ladli", "लाडली", "laxmi", "lakshmi", "लक्ष्मी"],
    ["janani", "जननी", "suraksha", "सुरक्षा", "delivery", "प्रसूति", "sambal", "संबल"],
    ["kanya", "कन्या", "vivah", "विवाह", "nikah", "निकाह"],
    ["yojana", "योजना", "scheme", "सीएम", "cm"],
]
_EXPAND: dict[str, set[str]] = {}
for _g in SYNONYM_GROUPS:
    _norm = {unicodedata.normalize("NFC", w).lower() for w in _g}
    for _w in _norm:
        _EXPAND.setdefault(_w, set()).update(_norm)


def normalise(text: str) -> str:
    """Lower-case, NFC, joiners removed, punctuation and symbols turned into spaces. Letters, numbers AND combining marks are kept: Devanagari vowel
    signs and virama are category M*, so a regex like [^\\w] would shatter every Hindi word."""
    s = unicodedata.normalize("NFC", str(text or "")).replace("‍", "").replace("‌", "").lower()
    return re.sub(r"\s+", " ", "".join(ch if ch.isspace() or unicodedata.category(ch)[0] in "LMN" else " " for ch in s)).strip()


def words(text: str) -> list[str]:
    return normalise(text).split()


@dataclass(frozen=True)
class Entry:
    kind: str
    title: str
    subtitle: str
    body: str = ""
    ref: str = ""  # id the page can open (department id, district name, complaint id)
    dept_id: str | None = None
    title_words: tuple = field(default=(), compare=False)
    body_words: tuple = field(default=(), compare=False)


@dataclass(frozen=True)
class Hit:
    entry: Entry
    score: float


def _entry(kind: str, title: str, subtitle: str, body: str = "", ref: str = "", dept_id: str | None = None) -> Entry:
    return Entry(kind, title, subtitle, body, ref, dept_id, tuple(words(title)), tuple(words(f"{subtitle} {body}")))


def build_index(conn) -> list[Entry]:
    """Everything searchable in the registry. Cheap to rebuild; callers cache it and drop the cache when the registry is edited."""
    out: list[Entry] = []
    aliases: dict[str, list[str]] = {}
    for a in R.rows(conn, "SELECT dept_id, alias FROM aliases"):
        aliases.setdefault(a["dept_id"], []).append(a["alias"])
    for d in R.departments_overview(conn):
        out.append(_entry("department", d["name_en"], f"{d['name_hi']} · {d['status']} · {d['services_mp'] + d['services_mped']} services", " ".join(aliases.get(d["id"], [])) + f" {d['notes']}", d["id"], d["id"]))
    names = {d["id"]: d["name_en"] for d in R.rows(conn, "SELECT id, name_en FROM departments")}
    for s in R.rows(conn, "SELECT title, source, dept_id, deadline_urban, raw_department, category FROM services"):
        dept = names.get(s["dept_id"], s["raw_department"] or "unassigned")
        if s["source"] == "cmhelpline":
            out.append(_entry("scheme", s["title"], f"{dept} · CM Helpline scheme", "", s["dept_id"] or "", s["dept_id"]))
        else:
            sla = f" · deadline {s['deadline_urban']}" if s["deadline_urban"] else ""
            out.append(_entry("service", s["title"], f"{dept}{sla}", f"{s['category']} {s['source']}", s["dept_id"] or "", s["dept_id"]))
    for d in R.rows(conn, "SELECT name, division, headquarters, population_2011 FROM districts"):
        out.append(_entry("district", d["name"], f"{d['division']} division · HQ {d['headquarters']} · population {d['population_2011'] or '?'}", "", d["name"]))
    for o in R.rows(conn, "SELECT name, level, district, status, dept_id, source FROM offices"):
        out.append(_entry("office", o["name"], f"{names.get(o['dept_id'], 'system desk')} · {o['level']} · {o['district'] or '-'} · {o['status']}", o["source"], o["dept_id"] or "", o["dept_id"]))
    return out


def ticket_entries(df: pd.DataFrame) -> list[Entry]:
    if df is None or df.empty:
        return []
    out = []
    for r in df.to_dict("records"):
        extra = " ".join(str(r.get(k, "")) for k in ("issue", "district", "office_name", "status", "department", "citizen_message", "eval_reason") if r.get(k) is not None)
        out.append(_entry("ticket", str(r["complaint_id"]), f"{r.get('department', '')} · {r.get('status', '')}", f"{r.get('summary_en', '')} {extra}", str(r["complaint_id"])))
    return out


def _variants(word: str) -> set[str]:
    """The word, its synonyms, and (for 4+ letters) the synonyms of any known term it is the start of: 'electr' -> electricity -> बिजली."""
    out = _EXPAND.get(word, {word}) | {word}
    if len(word) >= 4:
        for known, group in _EXPAND.items():
            if known.startswith(word):
                out |= group
        if len(out) == 1:  # nothing known: treat it as a typo of the closest known term ('electrcity' -> electricity)
            near = difflib.get_close_matches(word, _EXPAND, n=1, cutoff=0.8)
            if near:
                out |= _EXPAND[near[0]]
    return out


def _match_word(variants: set[str], entry_words: tuple) -> float:
    """0 = no match, 1 = exact word, 0.7 = prefix, 0.5 = typo."""
    best = 0.0
    for ew in entry_words:
        for v in variants:
            if ew == v:
                return 1.0
            if len(v) >= 2 and ew.startswith(v):
                best = max(best, 0.7)
            elif len(v) >= 4 and len(ew) >= 4 and best < 0.5 and difflib.SequenceMatcher(None, v, ew).ratio() >= 0.8:
                best = 0.5
    return best


def score(entry: Entry, query_words: list[str], raw_query: str) -> float:
    if not query_words:
        return 0.0
    if entry.kind == "ticket" and normalise(entry.title) == normalise(raw_query):
        return 100.0
    total = 0.0
    for qw in query_words:
        v = _variants(qw)
        in_title, in_body = _match_word(v, entry.title_words), _match_word(v, entry.body_words)
        if in_title == 0 and in_body == 0:
            return 0.0  # AND: every word must match something
        total += max(in_title * 2, in_body)
    return total * (1.25 if entry.kind == "department" else 1.0) / len(query_words)


def search(index: list[Entry], query: str, kinds: tuple[str, ...] = KINDS, per_kind: int = 8) -> dict[str, list[Hit]]:
    """Hits grouped by kind, best first, at most `per_kind` each."""
    qw = words(query)
    hits: dict[str, list[Hit]] = {k: [] for k in kinds}
    for e in index:
        if e.kind in hits:
            s = score(e, qw, query)
            if s > 0:
                hits[e.kind].append(Hit(e, s))
    return {k: sorted(v, key=lambda h: -h.score)[:per_kind] for k, v in hits.items() if v}


def allowed_kinds(role: str) -> tuple[str, ...]:
    return {"cm_admin": KINDS, "triage": KINDS, "dept_head": ("department", "service", "scheme", "district", "office", "ticket"),
            "office_officer": ("service", "scheme", "ticket")}.get(role, ())


def visible(entry: Entry, role: str, dept_id: str | None) -> bool:
    """A department head only sees their own department's departments/offices (public services and schemes stay visible to everyone allowed to search)."""
    if role == "dept_head" and entry.kind in ("department", "office"):
        return entry.dept_id == dept_id
    return True
