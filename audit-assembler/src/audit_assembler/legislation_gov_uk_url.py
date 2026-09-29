"""Build legislation.gov.uk HTML deep-links from instrument URL + fragment locators.

Port of Law Proposition Extractor's ``legislation-gov-uk-url.ts``, with extra
stripping of seed tails (``/contents/made``, ``/made``) used by Audit Assembler
legislation seeds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urlparse

PROVISION_TYPES = frozenset(
    {"article", "section", "regulation", "schedule", "annex", "part", "chapter"}
)

_XML_TAIL_RE = re.compile(
    r"/(?:data\.(?:xml|xht|htm|html)|contents/data\.(?:xml|xht))$", re.I
)
_CONTENTS_TAIL_RE = re.compile(r"/contents(?:/made)?$", re.I)
_MADE_TAIL_RE = re.compile(r"/made$", re.I)
_LEGISLATION_HOST_RE = re.compile(r"(^|\.)legislation\.gov\.uk$", re.I)

_FREE_TEXT_PROVISION_RE = re.compile(
    r"^(article|section|regulation|reg\.?|schedule|annex|part|chapter)\s+"
    r"([0-9]+[a-z]?|[ivxlcdm]+)\b",
    re.I,
)
_FREE_TEXT_PARA_RE = re.compile(r"^\s*\(\s*([0-9]+[a-z]?)\s*\)", re.I)
_FREE_TEXT_PARA_WORD_RE = re.compile(
    r"^\s*,?\s*paragraph\s+([0-9]+[a-z]?)\b", re.I
)


@dataclass(frozen=True)
class ProvisionRef:
    type: str
    id: str
    paragraph: str | None = None


def _normalize_annex_id(value: str) -> str:
    trimmed = value.strip()
    if re.fullmatch(r"[ivxlcdm]+", trimmed, re.I):
        return trimmed.upper()
    return trimmed


def _normalize_provision_id(kind: str, value: str) -> str:
    if kind == "annex":
        return _normalize_annex_id(value)
    return value.strip()


def legislation_document_base_url(source_url: str | None) -> str | None:
    raw = str(source_url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    if not _LEGISLATION_HOST_RE.search(parsed.hostname or ""):
        return None
    path = parsed.path or ""
    path = _XML_TAIL_RE.sub("", path)
    path = _CONTENTS_TAIL_RE.sub("", path)
    path = _MADE_TAIL_RE.sub("", path)
    path = path.rstrip("/")
    if not path or path == "/":
        return None
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _provision_from_canonical_locator(locator: str) -> ProvisionRef | None:
    parts = [part.strip() for part in locator.strip().lower().split(":") if part.strip()]
    if len(parts) < 2:
        return None

    kind: str | None = None
    ident: str | None = None
    paragraph: str | None = None

    i = 0
    while i < len(parts) - 1:
        key = parts[i]
        value = parts[i + 1]
        if key in {"list", "fragment", "subparagraph"}:
            break
        if key in PROVISION_TYPES and kind is None:
            kind = key
            ident = value
            i += 2
            continue
        if key == "paragraph" and kind is not None:
            paragraph = value
            break
        i += 1

    if not kind or not ident:
        return None
    return ProvisionRef(
        type=kind,
        id=_normalize_provision_id(kind, ident),
        paragraph=paragraph,
    )


def _provision_from_free_text_locator(locator: str) -> ProvisionRef | None:
    text = locator.strip()
    if not text:
        return None
    match = _FREE_TEXT_PROVISION_RE.match(text)
    if not match:
        return None
    kind = match.group(1).lower().rstrip(".")
    if kind == "reg":
        kind = "regulation"
    ident = _normalize_provision_id(kind, match.group(2))
    after = text[match.end() :]
    para_match = _FREE_TEXT_PARA_RE.match(after) or _FREE_TEXT_PARA_WORD_RE.match(after)
    return ProvisionRef(
        type=kind,
        id=ident,
        paragraph=para_match.group(1) if para_match else None,
    )


def provision_ref_from_locator(locator: str | None) -> ProvisionRef | None:
    raw = str(locator or "").strip()
    if not raw or raw.lower() == "document:full":
        return None
    if ":" in raw:
        return _provision_from_canonical_locator(raw) or _provision_from_free_text_locator(
            raw
        )
    return _provision_from_free_text_locator(raw)


def provision_path_from_locator(locator: str | None) -> str | None:
    ref = provision_ref_from_locator(locator)
    if ref is None:
        return None
    base = f"/{ref.type}/{quote(ref.id, safe='')}"
    if not ref.paragraph:
        return base
    # Schedules use an explicit /paragraph/ segment; articles/regs/sections use /N/M.
    if ref.type == "schedule":
        return f"{base}/paragraph/{quote(ref.paragraph, safe='')}"
    return f"{base}/{quote(ref.paragraph, safe='')}"


def legislation_provision_url(
    source_url: str | None, locator: str | None
) -> str | None:
    """Deep-link to the provision; fall back to instrument root when unmapped."""
    base = legislation_document_base_url(source_url)
    if base is None:
        return None
    path = provision_path_from_locator(locator)
    return f"{base}{path}" if path else base
