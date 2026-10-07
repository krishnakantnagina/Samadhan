"""S36 scheme lookup: word-overlap matching on the real scheme file. No network, no LLM."""

import csv

import pytest

from app import info_reply, schemes


def test_file_loads_and_links_are_gov_in():
    rows = schemes._load()
    assert len(rows) >= 300
    assert all(s.url.startswith("https://") and ".gov.in" in s.url for s, _ in rows)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("मुझे लाडली बहना योजना की जानकारी चाहिए", "लाडली"),
        ("मनरेगा में काम कैसे मिलेगा", "मनरेगा"),
        ("छात्रावास में प्रवेश कैसे मिलेगा", "छात्रावास"),
    ],
)
def test_finds_the_named_scheme(question, expected):
    found = schemes.find_words(question)
    if not found:
        pytest.skip(f"{expected!r} is not in the scraped file")
    assert any(expected in s.name for s in found)


@pytest.mark.parametrize(
    "question", ["", "   ", "क्या", "योजना की जानकारी चाहिए", "मेरे गाँव में सड़क खराब है"]
)
def test_generic_words_match_nothing(question):
    assert schemes.find_words(question) == []


def test_never_more_than_limit_and_never_raises():
    assert len(schemes.find_words("छात्रवृत्ति पोस्ट मैट्रिक", limit=2)) <= 2
    assert schemes.find_words("छात्रवृत्ति", path="no/such/file.csv") == []


def test_custom_file(tmp_path):
    f = tmp_path / "s.csv"
    with open(f, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["department_id", "department", "scheme_id", "scheme", "url"])
        w.writerow([1, "विभाग", 1, "कन्यादान विवाह सहायता योजना", "https://cmhelpline.mp.gov.in/x"])
        w.writerow(
            [1, "विभाग", 2, "कन्यादान विवाह", "http://evil.example.com/x"]
        )  # not https .gov.in: dropped
    schemes._load.cache_clear()
    try:
        got = schemes.find_words("कन्यादान विवाह कैसे करें", path=str(f))
        assert [s.url for s in got] == ["https://cmhelpline.mp.gov.in/x"]
    finally:
        schemes._load.cache_clear()


def test_enabled_flag(monkeypatch):
    monkeypatch.delenv("SCHEME_LOOKUP", raising=False)
    assert not schemes.enabled()
    monkeypatch.setenv("SCHEME_LOOKUP", "1")
    assert schemes.enabled()


def test_reply_lists_only_matches_and_ends_with_disclaimer():
    s = schemes.Scheme("टेस्ट योजना", "विभाग", "https://cmhelpline.mp.gov.in/a")
    text = info_reply.build_scheme_reply([s])
    assert "टेस्ट योजना" in text and "https://cmhelpline.mp.gov.in/a" in text
    assert text.endswith(info_reply.INFO_DISCLAIMER_HI)


# --- RAG retrieval (embeddings faked: no network, no key) ---
class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code != 200:
            import httpx

            raise httpx.HTTPStatusError("x", request=None, response=self)

    def json(self):
        return self._p


def _unit(i):
    v = [0.0] * schemes.EMBED_DIM
    v[i] = 1.0
    return v


@pytest.fixture
def fake_index(monkeypatch):
    rows = schemes._load()
    vectors = [_unit(i % schemes.EMBED_DIM) for i in range(len(rows))]
    monkeypatch.setattr(schemes, "_index", lambda: vectors)
    return rows


def test_semantic_returns_closest_and_applies_threshold_and_margin(fake_index):
    got = schemes.find_semantic("q", embed=lambda q: _unit(5), use_rerank=False)
    assert got == [
        fake_index[5][0]
    ]  # exact match only: the others have cosine 0, below the threshold
    assert (
        schemes.find_semantic("q", embed=lambda q: _unit(400), use_rerank=False) == []
    )  # nothing close


def test_semantic_none_when_it_cannot_run(fake_index, monkeypatch):
    assert schemes.find_semantic("q", embed=lambda q: None) is None
    monkeypatch.setattr(schemes, "_index", lambda: None)
    assert schemes.find_semantic("q", embed=lambda q: _unit(1)) is None


def test_find_falls_back_to_word_match_only_when_retrieval_cannot_run(monkeypatch):
    monkeypatch.setattr(schemes, "find_semantic", lambda *a, **k: None)
    assert schemes.find("छात्रवृत्ति") == schemes.find_words("छात्रवृत्ति")
    monkeypatch.setattr(schemes, "find_semantic", lambda *a, **k: [])
    assert schemes.find("छात्रवृत्ति") == []  # ran and found nothing close: do not guess with words


def test_embed_query_survives_failures(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert schemes.embed_query("x", post=lambda *a, **k: _Resp({}, 429)) is None
    assert (
        schemes.embed_query("x", post=lambda *a, **k: _Resp({"embedding": {"values": [1.0]}}))
        is None
    )  # wrong size
    ok = _Resp({"embedding": {"values": _unit(3)}})
    assert schemes.embed_query("x", post=lambda *a, **k: ok)[3] == pytest.approx(1.0)
    monkeypatch.delenv("GEMINI_API_KEY")
    assert schemes.embed_query("x") is None


def test_rerank_can_only_choose_from_the_candidates(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("SCHEME_RERANK", "1")
    cands = [schemes.Scheme(f"s{i}", "d", "https://a.gov.in") for i in range(4)]

    def reply(text):
        return lambda *a, **k: _Resp({"candidates": [{"content": {"parts": [{"text": text}]}}]})

    assert schemes.rerank("q", cands, post=reply('{"relevant": [3, 1, 99, 0, 3]}')) == [
        cands[2],
        cands[0],
    ]
    assert schemes.rerank("q", cands, post=reply('{"relevant": []}')) == []
    assert schemes.rerank("q", cands, post=reply("not json")) is None
    monkeypatch.setenv("SCHEME_RERANK", "0")
    assert schemes.rerank("q", cands, post=reply('{"relevant": [1]}')) is None  # off


def test_shipped_index_matches_the_csv():
    assert schemes._index() is not None, "run scripts/build_scheme_index.py"
