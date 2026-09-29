"""Detect repealed / structurally-empty legislative fragments (no extractable content).

legislation.gov.uk renders repealed or omitted provisions as the heading followed by a
run of dots (e.g. ``Article 5. . . . . .``) and leaves bare enumerators / lone headings
(``(2)``, ``5.``, ``ANNEX II``). The frontier model correctly returns nothing for these,
but the heuristic fallback would otherwise emit them as ``needs_review`` noise. This shared
predicate lets both the extraction path (skip emitting) and the explorer (suppress in the
default view) treat them consistently.
"""

from __future__ import annotations

import re

# A single leading structural marker: (2) · 2 · 2a · (a) · (iv) · Article 5 · Annex II · Part IV.
_MARKER = (
    r"(?:"
    r"\(?\d+[a-z]?\)?"  # 2, (2), 2a
    r"|\((?:[a-z]|[ivxlcdm]{1,5})\)"  # (a), (iv)
    r"|(?:article|section|regulation|paragraph|sub-?paragraph|annex|schedule|part|chapter)"
    r"\s*[ivxlcdm\d]+[a-z]?"  # Article 5, Annex II, Part IV
    r")"
)
# Filler legislation.gov.uk uses for repealed/omitted text, plus enumerator punctuation/space.
_FILLER = r"[.\u2026\u00b7\u2022)\s]"
_PLACEHOLDER_RE = re.compile(rf"^{_FILLER}*(?:{_MARKER}{_FILLER}*)*$", re.IGNORECASE)


def is_repealed_or_empty_fragment(text: str | None) -> bool:
    """True when a fragment / proposition carries no extractable normative content.

    Matches blank text, bare enumerators (``(2)``, ``5.``), lone headings (``ANNEX II``,
    ``Article 6``), and repealed/omitted dot runs (``Article 5. . . . .``). Conservative:
    any alphabetic word beyond a structural marker makes the whole match fail, so genuine
    short rules (``Imports are prohibited.``) are never suppressed.
    """
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return True
    return bool(_PLACEHOLDER_RE.fullmatch(collapsed))
