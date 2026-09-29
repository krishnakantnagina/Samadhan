"""S28 4.6 info reply + .gov.in link validation. DNS is faked: no network."""

import pytest

from app import info_reply
from app.info_reply import build_info_reply, clean_info_url

YES = lambda host: True
NO = lambda host: False


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("https://mponline.gov.in", "https://mponline.gov.in"),
        (
            "https://mponline.gov.in/some/deep/path?x=1#frag",
            "https://mponline.gov.in",
        ),  # homepage only
        ("HTTPS://DigiLocker.GOV.IN/", "https://digilocker.gov.in"),
        ("https://cmhelpline.mp.gov.in/apply", "https://cmhelpline.mp.gov.in"),
        ("  https://edistrict.mp.gov.in  ", "https://edistrict.mp.gov.in"),
    ],
)
def test_real_gov_in_homepages_are_kept(given, kept):
    assert clean_info_url(given, resolves=YES) == kept


@pytest.mark.parametrize(
    "bad",
    [
        "http://mponline.gov.in",  # not https
        "https://gov.in.evil.com",  # suffix trick
        "https://evilgov.in",  # no label boundary
        "https://mponline.gov.in.evil.com",
        "https://x.nic.in",  # only .gov.in
        "https://example.com",
        "https://gov.in",  # bare suffix, not a host under it
        "https://user@x.gov.in",  # userinfo
        "https://user:pw@x.gov.in",
        "https://x.gov.in:8080",  # port
        "https://x.gov.in:notaport",
        "https://127.0.0.1",
        "https://[::1]",
        "javascript:alert(1)",
        "//x.gov.in",
        "https://x..gov.in",  # empty label
        "https://-bad.gov.in",  # bad label
        "https://exämple.gov.in",  # non-ascii host
        "",
        "not a url",
        None,
        123,
    ],
)
def test_everything_else_is_rejected(bad):
    assert clean_info_url(bad, resolves=YES) is None


def test_a_gov_in_host_that_does_not_resolve_is_dropped():
    assert clean_info_url("https://totally-made-up-portal.gov.in", resolves=NO) is None


def test_reply_has_message_link_and_disclaimer_in_order():
    reply = build_info_reply("https://mponline.gov.in/x", resolves=YES)
    lines = reply.split("\n")
    assert lines[0] == info_reply.INFO_MESSAGE_HI
    assert lines[1] == f"{info_reply.INFO_LINK_LINE_HI} https://mponline.gov.in"
    assert lines[2] == info_reply.INFO_DISCLAIMER_HI


@pytest.mark.parametrize("bad", [None, "https://evil.com", "https://x.gov.in:99"])
def test_reply_without_a_valid_link_still_has_message_and_disclaimer(bad):
    reply = build_info_reply(bad, resolves=YES)
    assert reply.split("\n") == [info_reply.INFO_MESSAGE_HI, info_reply.INFO_DISCLAIMER_HI]
    assert "http" not in reply


def test_reply_link_line_with_unresolvable_host_is_omitted():
    reply = build_info_reply("https://invented.gov.in", resolves=NO)
    assert "http" not in reply and info_reply.INFO_DISCLAIMER_HI in reply


def test_host_resolves_is_false_for_a_bad_host_and_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("no such host")

    monkeypatch.setattr(info_reply.socket, "getaddrinfo", boom)
    assert info_reply.host_resolves("nothing.gov.in") is False


def test_host_resolves_times_out(monkeypatch):
    import time

    monkeypatch.setattr(info_reply.socket, "getaddrinfo", lambda *a, **k: time.sleep(2))
    started = time.monotonic()
    assert info_reply.host_resolves("slow.gov.in", timeout=0.1) is False
    assert time.monotonic() - started < 1.0
