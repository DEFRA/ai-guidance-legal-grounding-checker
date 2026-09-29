"""Load Law Proposition Extractor law exports into a uniform LawUnit for Proposition Matcher matching.

Supports:
- ``propositions.json`` (list or ``{"propositions": [...]}``)
- ``proposition_matcher_law_candidates.json`` (``{"candidates": [...]}``)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from proposition_matcher.domain import Proposition

def _open_law_path(path: Path) -> Path:
    """Resolve law export path, accepting legacy beatrice_law_candidates.json. COMPAT_LEGACY_NAME"""
    if path.is_file():
        return path
    if path.is_dir():
        for name in (
            "proposition_matcher_law_candidates.json",
            "beatrice_law_candidates.json",  # COMPAT_LEGACY_NAME
            "propositions.json",
        ):
            candidate = path / name
            if candidate.is_file():
                return candidate
    # If caller pointed at the canonical name but only legacy exists beside it:
    if path.name == "proposition_matcher_law_candidates.json":
        legacy = path.with_name("beatrice_law_candidates.json")  # COMPAT_LEGACY_NAME
        if legacy.is_file():
            return legacy
    return path


LawSource = Literal["auto", "propositions", "candidates"]
ResolvedLawSource = Literal["propositions", "candidates"]


@dataclass(frozen=True)
class LawUnit:
    """Normalized law row for embed / retrieve / group-rerank."""

    id: str
    embed_text: str
    display_text: str
    citation: str
    payload: dict[str, Any]

    @property
    def proposition_text(self) -> str:
        """Alias so existing prompt code can read ``law.proposition_text``."""
        return self.display_text


def detect_law_source(raw: Any) -> ResolvedLawSource:
    """Sniff Law Proposition Extractor export shape. Raises ValueError when ambiguous or unknown."""
    if isinstance(raw, list):
        return "propositions"
    if not isinstance(raw, dict):
        raise ValueError(
            f"law file must be a JSON list or object, got {type(raw).__name__}"
        )

    has_candidates = isinstance(raw.get("candidates"), list)
    has_propositions = isinstance(raw.get("propositions"), list)

    if has_candidates and has_propositions:
        raise ValueError(
            "law file has both 'candidates' and 'propositions' — pass "
            "--law-source propositions|candidates explicitly"
        )
    if has_candidates:
        return "candidates"
    if has_propositions:
        return "propositions"
    raise ValueError(
        "unrecognised law file shape: expected a propositions list/object "
        "or a proposition_matcher_law_candidates object with 'candidates'"
    )


def _citation_from_proposition(prop: Proposition) -> str:
    return prop.article_reference or prop.fragment_locator or "—"


def _citation_from_candidate(cand: dict[str, Any]) -> str:
    presentation = cand.get("presentation")
    if isinstance(presentation, dict):
        label = str(presentation.get("locator_label") or "").strip()
        if label:
            return label
    evidence = cand.get("evidence")
    if isinstance(evidence, dict):
        locs = evidence.get("fragment_locators") or []
        if isinstance(locs, list):
            for loc in locs:
                text = str(loc or "").strip()
                if text:
                    return text
    return (
        str(cand.get("article_reference") or "").strip()
        or str(cand.get("fragment_locator") or "").strip()
        or "—"
    )


def _units_from_propositions(raw: Any) -> list[LawUnit]:
    records = raw if isinstance(raw, list) else raw.get("propositions", [])
    if not isinstance(records, list):
        raise ValueError("propositions payload must be a list")
    units: list[LawUnit] = []
    for rec in records:
        prop = Proposition.model_validate(rec)
        text = prop.proposition_text
        units.append(
            LawUnit(
                id=prop.id,
                embed_text=text,
                display_text=text,
                citation=_citation_from_proposition(prop),
                payload=prop.model_dump(),
            )
        )
    return units


def _units_from_candidates(raw: Any) -> list[LawUnit]:
    if not isinstance(raw, dict):
        raise ValueError("candidates payload must be a JSON object with 'candidates'")
    records = raw.get("candidates")
    if not isinstance(records, list):
        raise ValueError("candidates payload missing 'candidates' list")
    units: list[LawUnit] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        cand_id = str(rec.get("id") or "").strip()
        statement = str(rec.get("statement_text") or "").strip()
        matching = str(rec.get("matching_text") or "").strip()
        display = statement or matching
        if not cand_id or not display:
            continue
        units.append(
            LawUnit(
                id=cand_id,
                embed_text=matching or statement,
                display_text=display,
                citation=_citation_from_candidate(rec),
                payload=dict(rec),
            )
        )
    return units


def load_law_units(
    path: Path,
    *,
    source: LawSource = "auto",
) -> tuple[list[LawUnit], ResolvedLawSource]:
    """Load ``--law`` into LawUnits and the resolved source name."""
    path = _open_law_path(path)
    raw = json.loads(path.read_text())
    sniffed = detect_law_source(raw)

    if source == "auto":
        resolved: ResolvedLawSource = sniffed
    elif source != sniffed:
        raise SystemExit(
            f"--law-source {source} but {path} looks like {sniffed} "
            f"(expected matching JSON shape)"
        )
    else:
        resolved = source

    if resolved == "propositions":
        return _units_from_propositions(raw), resolved
    return _units_from_candidates(raw), resolved


def law_display_text(payload: dict[str, Any]) -> str:
    """Law text from a dumped match payload (prop or candidate)."""
    return str(
        payload.get("proposition_text")
        or payload.get("statement_text")
        or ""
    )
