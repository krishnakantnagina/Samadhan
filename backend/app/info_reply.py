"""S28 4.6 -- the fixed replies for non-complaints, and the validated `.gov.in` link.

The LLM may *propose* a link for an information question; nothing it says is trusted. `clean_info_url` keeps
a link only if it is an https `*.gov.in` host (label boundary), homepage only, that also resolves in DNS.
Everything else is fixed text written by us, never generated (S28 D-S28-2, D-S28-6, D-S28-7).

Either of us can change this file. If you do, update docs/specs/S28-multi-department-routing.md.
"""

import ipaddress
import re
import socket
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

GOV_SUFFIX = ".gov.in"
DNS_TIMEOUT_SECONDS = 2.0
_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

INFO_MESSAGE_HI = (
    "मेरे पास अभी इसकी कोई आधिकारिक जानकारी नहीं है। जब मेरे डेवलपर को सरकार के साथ काम करने का "
    "मौका मिलेगा, तब मैं आपकी मदद करने की पूरी कोशिश करूँगा।"
)
INFO_LINK_LINE_HI = "आप यहाँ देख सकते हैं:"
INFO_DISCLAIMER_HI = (
    "ध्यान दें: मैं कोई आधिकारिक स्रोत नहीं हूँ, इसलिए यह जानकारी सही न भी हो सकती है। "
    "कृपया आधिकारिक वेबसाइट पर जाँच लें।"
)
OUT_OF_CONTEXT_REPLY_HI = (
    "माफ़ कीजिए, मैं इस तरह के सवाल का जवाब नहीं दे सकता। अगर आपकी कोई समस्या या शिकायत है तो मुझे बताइए।"
)
URGENT_LINE_HI = "यह आपात स्थिति हो सकती है। कृपया तुरंत अपनी स्थानीय आपातकालीन सेवा से संपर्क करें।"


def host_resolves(host: str, timeout: float = DNS_TIMEOUT_SECONDS) -> bool:
    """True if `host` has a DNS record. Bounded by `timeout` (getaddrinfo itself has no timeout)."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(socket.getaddrinfo, host, 443, 0, socket.SOCK_STREAM)
        future.result(timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 -- timeout, NXDOMAIN, no network: all mean "do not link"
        return False
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def clean_info_url(url: object, *, resolves: Callable[[str], bool] = host_resolves) -> str | None:
    """The homepage of a real `*.gov.in` host, or None. Never raises."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        port = parts.port  # raises ValueError on a malformed port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password or port is not None:
        return None
    if not host.isascii() or not host.endswith(GOV_SUFFIX) or len(host) <= len(GOV_SUFFIX):
        return None
    try:
        ipaddress.ip_address(host)
        return None  # an IP literal, never a government hostname
    except ValueError:
        pass
    if not all(_LABEL.match(label) for label in host.split(".")):
        return None
    return f"https://{host}" if resolves(host) else None


def build_info_reply(url: object, *, resolves: Callable[[str], bool] = host_resolves) -> str:
    """Message, then the link line (only if the link passed), then the disclaimer, always."""
    lines = [INFO_MESSAGE_HI]
    cleaned = clean_info_url(url, resolves=resolves)
    if cleaned:
        lines.append(f"{INFO_LINK_LINE_HI} {cleaned}")
    lines.append(INFO_DISCLAIMER_HI)
    return "\n".join(lines)


SCHEME_INTRO_HI = "आपके सवाल से ये योजनाएँ मिलती हैं (मध्य प्रदेश सरकार):"


def build_scheme_reply(schemes: list) -> str:
    """Matched schemes with their official CM Helpline page, then the disclaimer. Only rows of the scheme file, never generated."""
    lines = [SCHEME_INTRO_HI]
    for i, s in enumerate(schemes, 1):
        lines.append(f"{i}. {s.name} ({s.department})" + chr(10) + f"   {s.url}")
    lines.append(INFO_DISCLAIMER_HI)
    return chr(10).join(lines)
