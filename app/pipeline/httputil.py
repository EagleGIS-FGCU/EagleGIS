"""HTTP helpers for pipeline network I/O.

estero-fl.gov (and some other municipal hosts) occasionally present a TLS
chain that browsers accept via AIA fetching but stock OpenSSL on GitHub
Actions rejects with CERTIFICATE_VERIFY_FAILED. We try a certifi-backed
context first, then fall back to an unverified context for that failure
only so weekly scrapes keep working.
"""
from __future__ import annotations

import logging
import ssl
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; EagleGIS/1.0; "
    "+https://github.com/EagleGIS-FGCU/EagleGIS)"
)


def _ssl_context(*, insecure: bool = False) -> ssl.SSLContext:
    if insecure:
        ctx = ssl._create_unverified_context()  # noqa: S323 — intentional fallback
        return ctx
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def urlopen(url: str, *, timeout: int = DEFAULT_TIMEOUT, headers: dict[str, str] | None = None):
    """Open *url* with a hardened SSL context and one insecure retry on verify failure."""
    hdrs = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}
    req = urllib.request.Request(url, headers=hdrs)
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if not isinstance(reason, ssl.SSLCertVerificationError):
            raise
        logger.warning(
            "TLS verify failed for %s (%s); retrying without certificate verification",
            url,
            reason,
        )
        return urllib.request.urlopen(
            req, timeout=timeout, context=_ssl_context(insecure=True)
        )


def fetch_text(url: str, *, timeout: int = DEFAULT_TIMEOUT, headers: dict[str, str] | None = None) -> str:
    with urlopen(url, timeout=timeout, headers=headers) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_bytes(url: str, *, timeout: int = DEFAULT_TIMEOUT, headers: dict[str, str] | None = None) -> bytes:
    with urlopen(url, timeout=timeout, headers=headers) as resp:
        return resp.read()
