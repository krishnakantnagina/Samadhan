"""S37 scheme answers: grounded explanation from the official page text. Embeddings and Gemini are faked: no network, no key."""

import json

import pytest

from app import scheme_answer as sa
from app import schemes

LADLI = schemes.Scheme(
    "मुख्यमंत्री लाडली बहना योजना",
    "महिला एवं बाल विकास विभाग",
    "https://cmhelpline.mp.gov.in/KnowYourEntitleDetail.aspx?status=ByVibhag&pointvalue=2&Schemeid=964",
)
OTHER = schemes.Scheme(
    "दूसरी योजना",
    "विभाग",
    "https://cmhelpline.mp.gov.in/KnowYourEntitleDetail.aspx?status=ByVibhag&pointvalue=2&Schemeid=2",
)
DETAIL = {
    "objective": "महिलाओं के आर्थिक स्वावलंबन के लिए।",
    "eligibility": "21 वर्ष से अधिक और 60 वर्ष से कम आयु की महिला। परिवार की आय 2.5 लाख से कम हो।",
    "amount": "प्रतिमाह 1250 रुपये",
    "where": "आंगनवाड़ी केन्द्र",
    "fee": "निःशुल्क",
    "apply_url": "https://cmbhopal.mp.gov.in",
}


def test_scheme_id_comes_from_the_url():
    assert LADLI.scheme_id == "964"
    assert schemes.Scheme("x", "y", "https://a.gov.in/x").scheme_id is None


def test_shipped_details_cover_nearly_every_scheme():
    rows = [s for s, _ in schemes._load()]
    covered = [s for s in rows if schemes.detail_for(s)]
    assert len(covered) >= len(rows) - 5
    assert all(
        schemes.detail_for(s).get("objective") or schemes.detail_for(s).get("eligibility")
        for s in covered
    )


def test_template_copies_page_text_under_our_own_headings():
    text = sa.template(LADLI, DETAIL)
    assert text.startswith("मुख्यमंत्री लाडली बहना योजना (महिला एवं बाल विकास विभाग)")
    assert (
        "कौन पात्र है: 21 वर्ष से अधिक" in text
        and "लाभ: प्रतिमाह 1250 रुपये" in text
        and "शुल्क: निःशुल्क" in text
    )
    assert "https" not in text  # links are added separately, from the file


def test_long_sections_are_cut_at_a_sentence_end():
    long = "पहला वाक्य यहाँ है। " * 80
    out = sa._clip(long, 120)
    assert len(out) <= 125 and out.rstrip(" …").endswith("।")


@pytest.mark.parametrize(
    ("answer", "ok"),
    [
        ("21 से 60 वर्ष की महिला को हर महीने 1250 रुपये मिलते हैं।", True),
        ("इक्कीस से साठ वर्ष की महिला।", True),  # no digits at all
        ("हर महीने 1500 रुपये मिलते हैं।", False),  # 1500 is not on the page
        ("१२५० रुपये प्रतिमाह।", True),  # Devanagari digits are read as 1250
        ("देखिए https://example.com", False),
        ("x" * 1000, False),
        ("", False),
    ],
)
def test_grounding_check(answer, ok):
    assert sa.grounded(answer, sa.source_text(DETAIL), "लाडली बहना योजना क्या है") is ok


def test_a_number_the_citizen_said_may_be_repeated():
    assert sa.grounded(
        "आपने 45 साल कहा, पर पेज में 60 साल से कम लिखा है।", sa.source_text(DETAIL), "मेरी उम्र 45 साल है"
    )


class _Resp:
    def __init__(self, answer):
        self._a, self.status_code = answer, 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"answer": self._a})}]}}]}


def test_explain_is_off_unless_switched_on_and_rejects_invented_numbers(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("SCHEME_EXPLAIN", raising=False)
    assert sa.explain("q", DETAIL, post=lambda *a, **k: _Resp("ठीक")) is None
    monkeypatch.setenv("SCHEME_EXPLAIN", "1")
    assert (
        sa.explain("q", DETAIL, post=lambda *a, **k: _Resp("हर महीने 1250 रुपये।"))
        == "हर महीने 1250 रुपये।"
    )
    assert sa.explain("q", DETAIL, post=lambda *a, **k: _Resp("हर महीने 3000 रुपये।")) is None


def _ranked(monkeypatch, scores):
    monkeypatch.setattr(schemes, "ranked", lambda q, **k: scores)
    monkeypatch.setattr(schemes, "detail_for", lambda s: DETAIL if s is LADLI else None)
    monkeypatch.delenv("SCHEME_EXPLAIN", raising=False)


def test_a_clear_match_is_explained_with_links_and_the_disclaimer(monkeypatch):
    _ranked(monkeypatch, [(0.76, LADLI), (0.70, OTHER)])
    text = sa.reply("लाडली बहना")
    assert "कौन पात्र है" in text and "ऑनलाइन आवेदन: https://cmbhopal.mp.gov.in" in text
    assert LADLI.url in text and text.endswith(sa.INFO_DISCLAIMER_HI)


def test_close_scores_list_the_names_and_ask_which(monkeypatch):
    _ranked(monkeypatch, [(0.705, LADLI), (0.704, OTHER)])
    text = sa.reply("छात्रवृत्ति")
    assert (
        LADLI.name in text
        and OTHER.name in text
        and sa.ASK_WHICH_HI in text
        and "कौन पात्र है" not in text
    )


def test_a_clear_match_without_page_text_falls_back_to_the_list(monkeypatch):
    _ranked(monkeypatch, [(0.8, OTHER), (0.6, LADLI)])
    assert sa.ASK_WHICH_HI in sa.reply("दूसरी योजना")


def test_nothing_close_means_no_scheme_answer(monkeypatch):
    _ranked(monkeypatch, [(0.60, LADLI)])
    assert sa.reply("passport kaise banta hai") is None


def test_without_retrieval_the_word_match_lists_names(monkeypatch):
    monkeypatch.setattr(schemes, "ranked", lambda q, **k: None)
    monkeypatch.setattr(schemes, "find_words", lambda q, **k: [LADLI])
    assert LADLI.name in sa.reply("लाडली बहना")
