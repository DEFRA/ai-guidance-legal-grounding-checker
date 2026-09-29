"""
Eight deterministic property checks on extracted propositions.

Guidance Proposition Extractor does not run these on its own outputs — they're exposed for the
validator at draft-pipelines/guidance-proposition-extractor/validation/property-checks/ and for any
caller that wants to gate at extraction time.

Each check is ``(proposition_dict, page_paragraphs) -> bool``. True == pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

# ── individual checks ────────────────────────────────────────────────────────

_OPERATIVE_RE = re.compile(
    r"\b(must|must not|shall|shall not|may|may not|should|should not|"
    r"required|prohibited|need to|needs to|cannot|can not|have to|has to|"
    r"is|are|has|have)\b",
    re.IGNORECASE,
)

_DEICTIC_OPENERS = (
    "this regulation", "this article", "this paragraph", "this directive",
    "this decision", "this guidance", "these", "those", "such ",
    "it ", "they ", "he ", "she ",
)

_CITATION_STUB_RE = re.compile(
    r"^\s*(see|refer to|as set out in|under|pursuant to)\b.{0,100}$",
    re.IGNORECASE,
)

_BARE_LIST_RE = re.compile(r"^\s*[\(\[]?[a-z0-9ivx]+[\)\].]\s+", re.IGNORECASE)

_PRONOUN_SUBJECTS = {
    "you", "we", "they", "he", "she", "it", "i", "one", "anyone", "someone",
}


def has_operative_language(prop: dict, _paragraphs: list[str]) -> bool:
    return bool(_OPERATIVE_RE.search(prop.get("proposition_text", "")))


def no_deictic_opener(prop: dict, _paragraphs: list[str]) -> bool:
    text = prop.get("proposition_text", "").strip().lower()
    return not any(text.startswith(opener) for opener in _DEICTIC_OPENERS)


def no_dangling_citation(prop: dict, _paragraphs: list[str]) -> bool:
    text = prop.get("proposition_text", "").strip()
    if len(text) > 140:
        return True
    return not _CITATION_STUB_RE.match(text)


def no_bare_list_marker(prop: dict, _paragraphs: list[str]) -> bool:
    text = prop.get("proposition_text", "")
    if not _BARE_LIST_RE.match(text):
        return True
    return bool(_OPERATIVE_RE.search(text))


def length_in_range(
    prop: dict, _paragraphs: list[str], min_words: int = 6, max_words: int = 60
) -> bool:
    words = (prop.get("proposition_text") or "").split()
    return min_words <= len(words) <= max_words


def looks_atomic(prop: dict, _paragraphs: list[str]) -> bool:
    """Flag heavily-conjoined propositions that look like merged obligations."""
    text = prop.get("proposition_text", "")
    if len(_OPERATIVE_RE.findall(text)) > 2:
        return False
    bare = re.sub(r"\([^)]*\)", "", text)
    if len(re.findall(r"\b(and|or)\b", bare, re.IGNORECASE)) >= 4:
        return False
    return True


def source_paragraph_verbatim(prop: dict, paragraphs: list[str]) -> bool:
    """Every source_paragraph must appear (case-insensitive, whitespace-collapsed)
    in the page's paragraphs. Catches hallucination and paraphrasing.

    Propositions with no source_paragraphs fail this check.
    """
    sources = prop.get("source_paragraphs") or []
    if not sources:
        return False
    haystack = " ".join(_collapse(p) for p in paragraphs)
    return all(_collapse(s) in haystack for s in sources)


def concrete_subject(prop: dict, _paragraphs: list[str]) -> bool:
    """Bonus check on the 'actor' field (Guidance Proposition Extractor's metadata schema).

    Empty actor — i.e. the page didn't supply one — passes (the prompt
    explicitly forbids guessing). A bare pronoun fails.
    """
    actor = (prop.get("actor") or "").strip().lower()
    if not actor:
        return True
    return actor not in _PRONOUN_SUBJECTS


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


# ── registry ─────────────────────────────────────────────────────────────────


@dataclass
class Check:
    key: str
    label: str
    description: str
    fn: Callable[[dict, list[str]], bool]


CHECKS: list[Check] = [
    Check("operative", "Operative language",
          "Contains a modal verb (must/may/shall/required/etc.) or a definitional copula.",
          has_operative_language),
    Check("no_deictic", "No deictic opener",
          "Doesn't begin with 'this regulation', 'those animals', 'it', etc.",
          no_deictic_opener),
    Check("no_citation_stub", "No dangling citation",
          "Not a short 'See Article X' stub with no operative content.",
          no_dangling_citation),
    Check("no_bare_list", "No bare list marker",
          "Doesn't start with '(a)'/'(i)'/'1.' unless it also contains operative language.",
          no_bare_list_marker),
    Check("length_in_range", "Length in range",
          "Between 6 and 60 words.",
          length_in_range),
    Check("atomic", "Looks atomic",
          "<=2 modal verbs and not heavily conjoined; flags compound obligations.",
          looks_atomic),
    Check("verbatim_source", "Verbatim source paragraph",
          "Every source_paragraph is a literal substring of the page text.",
          source_paragraph_verbatim),
    Check("concrete_subject", "Concrete actor",
          "actor field, if filled, is not a bare pronoun.",
          concrete_subject),
]


def score_proposition(prop: dict, paragraphs: list[str]) -> dict[str, bool]:
    return {check.key: bool(check.fn(prop, paragraphs)) for check in CHECKS}


def aggregate(props_with_scores: list[dict[str, bool]]) -> dict[str, float]:
    if not props_with_scores:
        return {check.key: 0.0 for check in CHECKS}
    return {
        check.key: sum(1 for s in props_with_scores if s.get(check.key)) / len(props_with_scores)
        for check in CHECKS
    }


def pass_all(scores: dict[str, bool]) -> bool:
    return all(scores.get(check.key, False) for check in CHECKS)
