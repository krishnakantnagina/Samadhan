"""Citizen text must reach the officer screens as plain text, never as markup (stored-injection fix, audit H5)."""

import re

import pytest

from dashboard.safe import h, md, tel_link

PAYLOADS = [
    "<img src=x onerror=alert(document.domain)>",
    "<script>alert(1)</script>",
    "[click here](https://evil.example/phish)",
    "![beacon](https://evil.example/track.png)",
    "**bold** _it_ `code` # heading > quote",
    "https://evil.example/login and mail me@evil.example",
    '" onmouseover="alert(1)',
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_h_leaves_no_html_tag_or_quote(payload):
    out = h(payload)
    assert "<" not in out and ">" not in out and '"' not in out


@pytest.mark.parametrize("payload", PAYLOADS)
def test_md_escapes_every_markdown_and_html_special(payload):
    out = md(payload)
    # every special character is preceded by a backslash, so Markdown shows it literally
    for i, ch in enumerate(out):
        if ch in "<>[]()*_`#!:@&\"'" and (i == 0 or out[i - 1] != "\\"):
            pytest.fail(f"unescaped {ch!r} at {i} in {out!r}")


@pytest.mark.parametrize("payload", PAYLOADS)
def test_md_is_lossless_unescaping_gives_the_original_text_back(payload):
    assert re.sub(r"\\(.)", r"\1", md(payload)) == " ".join(payload.split())


def test_hindi_text_and_numbers_pass_through_readable():
    assert md("मेरा गाँव किलोदा, 15 दिन") == "मेरा गाँव किलोदा, 15 दिन"
    assert h("मेरा गाँव") == "मेरा गाँव"


def test_none_and_line_breaks_are_handled():
    assert h(None) == "" and md(None) == ""
    assert md("line one\nline two") == "line one line two"


def test_tel_link_only_for_well_formed_phone_numbers():
    assert tel_link("+919876543210") == "[+919876543210](tel:+919876543210)"
    assert tel_link("9876543210") == "[9876543210](tel:9876543210)"
    assert tel_link("javascript:alert(1)") is None
    assert tel_link("98765 43210)(evil") is None
    assert tel_link(None) is None
