"""Safe output for text a citizen wrote (place names, addresses, complaint text, summaries).

Citizens type anything into the chat, and the officer dashboards show it. Streamlit renders Markdown, and with `unsafe_allow_html=True` raw HTML, so an
unescaped value could inject markup, fake links or images into an officer's screen. Run every citizen-controlled value through one of these before it is
placed into `st.markdown` / `st.write` / an HTML string:

  h(value)   for HTML you build yourself (st.markdown(..., unsafe_allow_html=True))
  md(value)  for plain Markdown (st.write / st.markdown without HTML): every Markdown and HTML special character is backslash-escaped
"""

import html
import re

_MD_SPECIAL = "\`*_{}[]()#+-.!|~>:@<&\"'"
_MD_RE = re.compile("([" + re.escape(_MD_SPECIAL) + "])")
_PHONE_RE = re.compile(r"^\+?\d{10,15}$")


def h(value: object) -> str:
    """HTML-escape (also quotes, so it is safe inside an attribute such as title="...")."""
    return html.escape(str(value if value is not None else ""), quote=True)


def md(value: object) -> str:
    """Show `value` as literal text in Markdown: no links, images, bold, headings, HTML or autolinks. Line breaks become spaces."""
    text = " ".join(str(value if value is not None else "").split())
    return _MD_RE.sub(lambda match: "\\" + match.group(1), text)


def tel_link(phone: object) -> str | None:
    """A `tel:` Markdown link for a well-formed phone number, else None (show it as plain text)."""
    text = str(phone or "").strip()
    return f"[{text}](tel:{text})" if _PHONE_RE.match(text) else None
