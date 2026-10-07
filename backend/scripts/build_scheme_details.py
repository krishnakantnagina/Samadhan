"""Turn the raw CM Helpline scrape into the compact file the bot answers from: specs/registry/scheme_details.json.

Input  (git-excluded): local-research/data/scheme_details.json   (made by local-research/scripts/scrape_scheme_details.py)
Output (shipped):      specs/registry/scheme_details.json         keyed by CM Helpline scheme id

Only the text the official page itself gives is kept, whitespace tidied. Nothing is written or guessed here.
Rebuild the embedding index afterwards:  uv run --env-file ../.env python scripts/build_scheme_index.py
"""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "local-research" / "data" / "scheme_details.json"
OUT = ROOT / "specs" / "registry" / "scheme_details.json"

# the page's Hindi label (whitespace-normalised) -> our short key
LABELS = {
    "योजना का उद्येश्य": "objective",
    "लाभार्थी के लिए आवश्यक शर्ते / लाभार्थी चयन प्रक्रिया": "eligibility",
    "लाभार्थी वर्ग": "groups",
    "लाभार्थी का प्रकार": "kind",
    "लाभ की श्रेणी": "benefit_type",
    "आवेदन/संपर्क/पंजीयन/प्रशिक्षण कहाँ करें": "where",
    "आवेदन प्रक्रिया": "process",
    "आवेदन शुल्क": "fee",
    "अनुदान /ऋण /वित्तीय सहायता /पेंशन/लाभ की राशि": "amount",
    "योजना से सम्बंधित दस्तावेज संलग्न करें": "documents",
    "पदभिहित अधिकारी": "officer",
    "समय सीमा": "time_limit",
    "अपील": "appeal",
    "योजना कब से प्रारंभ की गयी": "since",
    "अपडेट दिनांक": "updated",
}
PAYMENT_PREFIX = "हितग्राहियों को राशि के भुगतान"
APPLY_LABEL = "ऑनलाइन आवेदन हेतु लिंक"
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in")
EMPTY = {"", "-", "--", "—", "na", "n/a", "nil", "none", "नहीं", "लागू नहीं", "उपलब्ध नहीं"}


def tidy(text: str) -> str:
    text = text.replace("\t", " ")
    lines = [re.sub(r"[ ]{2,}", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def official_link(text: str) -> str | None:
    """The first https link of a government host in the field, or None."""
    for token in re.findall(r"https?://[^\s,;|)]+", text):
        parts = urlsplit(token.rstrip(".।"))
        host = (parts.hostname or "").lower()
        if parts.scheme == "https" and host.endswith(OFFICIAL_SUFFIXES):
            return token.rstrip(".।")
        if parts.scheme == "http" and host.endswith(OFFICIAL_SUFFIXES):
            return "https" + token[4:].rstrip(".।")
    return None


def convert(row: dict) -> dict:
    out: dict[str, str] = {}
    norm = {re.sub(r"\s+", " ", k).strip(): v for k, v in row["fields"].items()}
    for label, key in LABELS.items():
        value = tidy(norm.get(label, ""))
        if value.lower() not in EMPTY:
            out[key] = value
    for label, value in norm.items():
        if label.startswith(PAYMENT_PREFIX) and tidy(value).lower() not in EMPTY:
            out["payment"] = tidy(value)
    link = official_link(norm.get(APPLY_LABEL, ""))
    if link:
        out["apply_url"] = link
    return out


def main() -> None:
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    details = {}
    for row in rows:
        data = convert(row)
        if data:
            details[row["scheme_id"]] = {"name": row["name"], "department": row["department"], **data}
    OUT.write_text(json.dumps(details, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    useful = sum(1 for d in details.values() if "eligibility" in d or "objective" in d)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB): {len(details)} schemes, {useful} with objective or eligibility text")
    for key in ("objective", "eligibility", "amount", "where", "process", "documents", "fee", "apply_url"):
        print(f"  {key:12s} {sum(1 for d in details.values() if key in d)}")


if __name__ == "__main__":
    main()
