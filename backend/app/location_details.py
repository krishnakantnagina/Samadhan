"""S31 -- Structured location details: district, tehsil, nearest place (parsed in code, no LLM).

The citizen's answer to "which district / tehsil?" is turned into columns the CM office can analyse. The district is matched against the 55 official
districts (specs/registry/districts.yaml: Hindi, English and alternate spellings) with tolerance for spelling variants; the tehsil and nearest place are
free text until the LGD directory is loaded. "I don't know" is a valid answer and is kept as unknown. Nothing here invents a district: no confident match
means district=None.
"""

import re
import unicodedata
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz

DISTRICTS_PATH = Path(__file__).resolve().parents[2] / "specs" / "registry" / "districts.yaml"
FUZZY_MIN = 88  # rapidfuzz ratio needed for a spelling-variant match (exact normalised matches always count)
# Everyday words that are also district names: only accepted with a "district" marker, or when the whole answer is one or two words.
COMMON_WORDS = {"धार", "सीधी", "पन्ना", "गुना", "सागर"}
DISTRICT_MARKERS = r"(?:जिला|जिले|ज़िला|ज़िले|district|zila|jila|dist)"
TEHSIL_MARKERS = r"(?:तहसील|तहसिल|तेहसील|tehsil|tahsil|tahasil)"
NEAR_MARKERS = r"(?:के\s+पास|के\s+नजदीक|के\s+नज़दीक|नजदीक|नज़दीक|पास\s+में)"
# "सबसे करीब/कने सारंगपुर है": the place comes AFTER the marker (कने = Bundeli for "near")
NEAR_AFTER = r"(?:सबसे\s+(?:पास|करीब|नज़?दीक|कने|कनै)|नज़?दीकी|करीबी|निकटतम|समीप)\s*(?:का|की|के|तो|में|वाला|वाली)?\s*(?:कस्बा|गाँव|गांव|शहर|कसबा)?\s*(?:तो\s+)?(\S+)"
# A word right before "तहसील" that is a connector, not a name: "…है पर तहसील गुलाना है" must give गुलाना, not "पर".
NOT_A_NAME = {"पर", "और", "तथा", "व", "मगर", "लेकिन", "तो", "भी", "है", "की", "का", "के", "में", "से", "यहाँ", "वहाँ", "but", "and", "the", "my", "meri", "mera"}
UNKNOWN_RE = re.compile(r"(पता\s*नहीं|नहीं\s*पता|मालूम\s*नहीं|नहीं\s*मालूम|नहीं\s*बता|याद\s*नहीं|don'?t\s*know|dont\s*know|pata\s*nahi|nahi\s*pata|not\s*sure)", re.IGNORECASE)
TRAILING = {"में", "की", "का", "के", "है", "से", "मे", "ki", "ka", "ke", "hai", "me", "mein"}

_NASAL_CONJUNCT = re.compile(r"[णनमङञ]्(?=[क-ह])")


def norm(text: str) -> str:
    """Comparable form: NFC, no joiners/nukta/anusvara/chandrabindu or nasal conjuncts (भिण्ड = भिंड), long vowels shortened (सीहोर = सिहोर), lower-case."""
    s = unicodedata.normalize("NFC", text or "").replace("‍", "").replace("‌", "").lower()
    s = s.replace("़", "").replace("ं", "").replace("ँ", "")
    s = _NASAL_CONJUNCT.sub("", s).replace("ी", "ि").replace("ू", "ु")
    return re.sub(r"\s+", " ", "".join(c if (c.isspace() or unicodedata.category(c)[0] in "LMN") else " " for c in s)).strip()


@dataclass(frozen=True)
class District:
    code: int
    name_en: str
    name_hi: str
    division: str
    names: tuple[str, ...]  # normalised: Hindi, English and aliases


@lru_cache
def load_districts(path: Path = DISTRICTS_PATH) -> tuple[District, ...]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))["districts"]
    return tuple(District(r["code"], r["name_en"], r["name_hi"], r["division"], tuple({norm(n) for n in [r["name_hi"], r["name_en"], *r.get("aliases", [])]})) for r in rows)


def match_district(text: str, *, strict: bool = False, districts: tuple[District, ...] | None = None) -> District | None:
    """The district named in `text`, or None. `strict` (no marker, longer answer) rejects the everyday-word names and weak fuzzy matches."""
    districts = districts or load_districts()
    words = norm(text).split()
    best: tuple[float, int, District] | None = None
    for size in (3, 2, 1):  # longest phrase first: "अशोक नगर", "आगर मालवा"
        for i in range(len(words) - size + 1):
            gram = " ".join(words[i : i + size])
            for d in districts:
                for name in d.names:
                    score = 100.0 if gram == name else (fuzz.ratio(gram, name) if len(gram) >= 5 and len(name) >= 5 else 0.0)
                    if score < (100 if strict else FUZZY_MIN):
                        continue
                    if strict and gram in {norm(w) for w in COMMON_WORDS}:
                        continue
                    if best is None or (score, size) > (best[0], best[1]):
                        best = (score, size, d)
    return best[2] if best else None


@dataclass(frozen=True)
class LocationDetails:
    district: str | None = None  # English name, canonical
    district_hi: str | None = None
    division: str | None = None
    tehsil: str | None = None
    nearest_place: str | None = None
    unknown: bool = False  # the citizen said they do not know
    raw: str = ""

    @property
    def any(self) -> bool:
        return bool(self.district or self.tehsil or self.nearest_place)

    def as_meta(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", False)} | ({"unknown": True} if self.unknown else {})


def _clean(span: str | None) -> str | None:
    if not span:
        return None
    words = [w for w in span.replace(",", " ").split() if w not in TRAILING]
    out = " ".join(words).strip(" -:.।")
    return out[:80] or None


_FILLER = {"मेरा", "मेरी", "मेरे", "है", "हमारा", "हमारी", "हमारे", "का", "की", "के"}


def parse(text: str) -> LocationDetails:
    """Turn a free answer into district / tehsil / nearest place. Never raises; an unreadable answer is kept as the nearest place."""
    raw = (text or "").strip()[:120]
    if not raw:
        return LocationDetails(raw="")
    low = raw
    unknown = bool(UNKNOWN_RE.search(low))
    district = None
    named = None
    for pattern in (rf"(\S+(?:\s+\S+)?)\s*{DISTRICT_MARKERS}", rf"{DISTRICT_MARKERS}\s*(?:है|:|-)?\s*(\S+(?:\s+\S+)?)"):
        m = re.search(pattern, low, re.IGNORECASE)
        if m and (district := match_district(m.group(1))):
            break
        if m and named is None:
            words = (_clean(m.group(1)) or "").split()
            while words and words[-1] in _FILLER:
                words.pop()
            if words and words[0] not in _FILLER:
                named = " ".join(words)  # a district was named but it is not one of the 55 (e.g. outside MP): keep just its name
    if district is None:
        district = match_district(low, strict=len(low.split()) > 2)
    tehsil = None
    m = re.search(rf"(\S+)\s*{TEHSIL_MARKERS}", low, re.IGNORECASE)
    if m and norm(m.group(1)) in {norm(w) for w in NOT_A_NAME}:
        m = None  # the word before the marker is a connector: the name follows it
    m = m or re.search(rf"{TEHSIL_MARKERS}\s*(?:है|:|-)?\s*(\S+)", low, re.IGNORECASE)
    if m:
        tehsil = _clean(m.group(1))
        if tehsil and district and match_district(tehsil) is district:  # "रीवा जिला तहसील" etc.: the word was the district, not a tehsil
            tehsil = None
    nearest = None
    for clause in re.split(r"[,;।\n]", low):  # look inside one phrase only: "पता नहीं, रामपुर के पास" must not read across the comma
        m = (
            re.search(NEAR_AFTER, clause)  # first: "सबसे नजदीक कस्बा बैरसिया" must not read "सबसे" as the place
            or re.search(rf"(\S+(?:\s+\S+)?)\s*{NEAR_MARKERS}", clause)
            or re.search(r"(?:near|nearest)\s+(\S+(?:\s+\S+)?)", clause, re.IGNORECASE)
        )
        if m:
            nearest = _clean(m.group(1))
            break
    if named and not (district or tehsil or nearest):
        nearest = f"{named} (जिला)"
    if not (district or tehsil or nearest) and not unknown:
        nearest = _clean(raw)  # something place-like we could not classify: keep it for the officer
    return LocationDetails(district.name_en if district else None, district.name_hi if district else None, district.division if district else None,
                           tehsil, nearest, unknown and not (district or tehsil or nearest), raw)
