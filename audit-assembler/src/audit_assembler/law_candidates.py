"""Join Law Proposition Extractor candidate locators onto stripped Matcher law.json rows."""

from __future__ import annotations

import re
from typing import Any

_CITATION_PROVISION_RE = re.compile(
    r"\b((?:regulation|article|section|schedule|annex)\s+\S.+)$",
    re.I,
)


def load_candidates(data: Any) -> list[dict]:
    """Accept bare candidate list or ``{candidates: [...]}`` export wrap."""
    if isinstance(data, dict) and isinstance(data.get("candidates"), list):
        return data["candidates"]
    if isinstance(data, list):
        return data
    raise ValueError(
        "law-candidates must be a JSON list or an object with a 'candidates' array"
    )


def locator_from_candidate(candidate: dict) -> str | None:
    presentation = candidate.get("presentation")
    if isinstance(presentation, dict):
        label = str(presentation.get("locator_label") or "").strip()
        if label and label != "Multiple provisions":
            return label
    evidence = candidate.get("evidence")
    if isinstance(evidence, dict):
        for item in evidence.get("fragment_locators") or []:
            text = str(item or "").strip()
            if text:
                return text
    for key in ("fragment_locator", "article_reference"):
        text = str(candidate.get(key) or "").strip()
        if text:
            return text
    return None


def locator_from_law_row(row: dict) -> str | None:
    """Best available locator on a Matcher law.json / joined row."""
    for key in ("fragment_locator", "article_reference"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    presentation = row.get("presentation")
    if isinstance(presentation, dict):
        label = str(presentation.get("locator_label") or "").strip()
        if label and label != "Multiple provisions":
            return label
    evidence = row.get("evidence")
    if isinstance(evidence, dict):
        for item in evidence.get("fragment_locators") or []:
            text = str(item or "").strip()
            if text:
                return text
    citation = str(row.get("citation") or "").strip()
    if citation:
        match = _CITATION_PROVISION_RE.search(citation)
        if match:
            return match.group(1).strip()
    return None


def merge_law_candidate_locators(
    law_input: list[dict],
    candidates: list[dict],
    warnings: list[str],
) -> list[dict]:
    """Copy ``fragment_locator`` from candidates onto law rows that lack one.

    Does not overwrite an existing locator on ``law_input``. Returns new row dicts.
    """
    by_id = {str(c["id"]): c for c in candidates if c.get("id")}
    merged: list[dict] = []
    joined = 0
    unmatched = 0
    for lp in law_input:
        row = dict(lp)
        if locator_from_law_row(row):
            merged.append(row)
            continue
        cand = by_id.get(str(lp.get("id") or ""))
        if cand is None:
            unmatched += 1
            merged.append(row)
            continue
        locator = locator_from_candidate(cand)
        if locator:
            row["fragment_locator"] = locator
            joined += 1
        else:
            unmatched += 1
        merged.append(row)

    if joined:
        warnings.append(
            f"joined fragment_locator from law-candidates for {joined} law proposition(s)"
        )
    if unmatched:
        warnings.append(
            f"{unmatched} law proposition(s) had no locator in law.json or law-candidates"
        )
    return merged
