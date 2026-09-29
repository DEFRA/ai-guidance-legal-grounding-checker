"""URL identity for Excel round-trip — gov.uk path, same rules as GRF explain."""

from __future__ import annotations

from urllib.parse import urlparse

from guidance_relevance_filter.annotate import govuk_path

GOVUK_HOSTS = {"www.gov.uk", "gov.uk"}
GOVUK_PREFIX = "https://www.gov.uk"


def normalize_govuk_url(url: str) -> str | None:
    """Canonical ``https://www.gov.uk/<path>``, or None if not a gov.uk URL."""
    raw = (url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    if host not in GOVUK_HOSTS:
        return None
    path = govuk_path(raw)
    if not path:
        return None
    return f"{GOVUK_PREFIX}{path}"


def require_govuk_url(url: str) -> str:
    canonical = normalize_govuk_url(url)
    if canonical is None:
        raise ValueError(f"not a www.gov.uk URL: {url!r}")
    return canonical
