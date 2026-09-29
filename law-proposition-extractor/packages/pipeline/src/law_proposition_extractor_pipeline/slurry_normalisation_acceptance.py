"""Deterministic acceptance checks for slurry principal-5 frontier export normalisation."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import Proposition, apply_relationship_keys
from law_proposition_extractor_domain.enums import LegalEffectType, PropositionTier
from law_proposition_extractor_domain.proposition_relationship_keys import should_auto_link_propositions

from .proposition_classification_pass import apply_post_extraction_classification_pass
from .proposition_jurisdiction_pass import apply_post_extraction_jurisdiction_pass
from .proposition_labelling_pass import apply_post_extraction_labelling_pass

# Repo-relative default: frontier export used in NORMALISATION_COMPARISON.md.
DEFAULT_SLURRY_EXPORT_DIR = Path("runs/slurry-gb-principal-5-frontier-export")

DIFFUSE_SOURCE_2018 = "lex-2459c955ee13be52"
AGRICULTURAL_LAND_ENGLAND_TEXT = "These Regulations apply to agricultural land in England."
EXPECTED_REG1D_LABEL_FRAGMENT = "Application to agricultural land in England"

_REG1_LOCATOR = re.compile(r"^regulation\s+1(\([a-d]\))?$", re.IGNORECASE)


@dataclass(frozen=True)
class SlurryNormalisationAcceptanceResult:
    before_count: int
    after_count: int
    generic_key_count: int
    cross_instrument_link_count: int
    citation_commencement_count: int
    citation_commencement_visible_count: int


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "packages" / "pipeline").is_dir():
            return candidate
    return here.parents[4]


def default_slurry_export_path(repo_root: Path | None = None) -> Path:
    root = repo_root if repo_root is not None else _repo_root()
    return root / DEFAULT_SLURRY_EXPORT_DIR


def slurry_export_available(export_dir: str | Path | None = None) -> bool:
    root = Path(export_dir) if export_dir is not None else default_slurry_export_path()
    return (root / "propositions.json").is_file()


def load_slurry_export_propositions(export_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(export_dir) / "propositions.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise TypeError(f"{path} must contain a JSON list")
    return raw


def load_normalised_slurry_export_propositions(export_dir: str | Path) -> list[dict[str, Any]]:
    """Load export propositions and apply post-extraction normalisation v1 (same as acceptance)."""
    before = load_slurry_export_propositions(export_dir)
    after = normalise_slurry_propositions(before)
    return [p.model_dump(mode="json") for p in after]


def normalise_slurry_propositions(before: list[dict[str, Any]]) -> list[Proposition]:
    """Re-apply post-extraction normalisation v1 (no LLM)."""
    props: list[Proposition] = []
    for row in before:
        props.append(Proposition.model_validate(deepcopy(row)))
    apply_post_extraction_classification_pass(props)
    apply_post_extraction_jurisdiction_pass(props)
    apply_post_extraction_labelling_pass(props)
    for prop in props:
        apply_relationship_keys(prop)
    _rebuild_cross_reference_targets(props)
    return props


def _rebuild_cross_reference_targets(props: list[Proposition]) -> None:
    for prop in props:
        prop.cross_reference_targets = []
    index: dict[str, list[str]] = {}
    for prop in props:
        if prop.source_scoped_key:
            index.setdefault(prop.source_scoped_key, []).append(prop.id)
    by_id = {p.id: p for p in props}
    for ids in index.values():
        if len(ids) <= 1:
            continue
        for pid in ids:
            left = by_id[pid]
            linked = [
                other
                for other in ids
                if other != pid and should_auto_link_propositions(left, by_id[other])
            ]
            if linked:
                left.cross_reference_targets = linked


def is_generic_these_regulations_key(key: str | None) -> bool:
    k = str(key or "").strip().lower()
    return k.startswith("uk:these-regulations")


def cross_instrument_cross_reference_targets(props: list[Proposition]) -> list[dict[str, str]]:
    by_id = {p.id: p for p in props}
    bad: list[dict[str, str]] = []
    for prop in props:
        sid = str(prop.source_record_id or "")
        for tid in prop.cross_reference_targets or []:
            target = by_id.get(tid)
            if target is None:
                continue
            tsid = str(target.source_record_id or "")
            if sid and tsid and sid != tsid:
                bad.append(
                    {
                        "from_id": prop.id,
                        "to_id": tid,
                        "from_source": sid,
                        "to_source": tsid,
                        "cross_reference_key": str(prop.cross_reference_key or ""),
                    }
                )
    return bad


def explorer_visible_default(prop: Proposition) -> bool:
    """Mirror scripts/compare_slurry_normalisation.py default explorer visibility."""
    if prop.proposition_tier == PropositionTier.INSTRUMENT_METADATA:
        return False
    if prop.legal_effect_type in {LegalEffectType.CITATION, LegalEffectType.COMMENCEMENT}:
        return False
    if (
        prop.proposition_tier == PropositionTier.UNKNOWN
        and prop.legal_effect_type == LegalEffectType.UNKNOWN
    ):
        return True
    return prop.proposition_tier in {
        PropositionTier.SUBSTANTIVE_RULE,
        PropositionTier.PROCEDURAL_RULE,
        PropositionTier.DEFINITIONAL_RULE,
        PropositionTier.SCOPE_RULE,
        PropositionTier.RELATIONSHIP_REFERENCE,
    }


def compliance_relevant_only_visible(prop: Proposition) -> bool:
    """Compliance-only explorer filter — uses is_compliance_relevant, never legacy categories."""
    return explorer_visible_default(prop) and prop.is_compliance_relevant is True


def find_proposition(
    props: list[Proposition],
    *,
    source_record_id: str,
    fragment_locator: str,
    proposition_text: str | None = None,
) -> Proposition:
    locator_norm = fragment_locator.strip().lower()
    matches = [
        p
        for p in props
        if str(p.source_record_id or "") == source_record_id
        and str(p.fragment_locator or "").strip().lower() == locator_norm
        and (proposition_text is None or p.proposition_text == proposition_text)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one proposition for source={source_record_id!r} "
            f"locator={fragment_locator!r} text={proposition_text!r}, found {len(matches)}"
        )
    return matches[0]


def evaluate_slurry_normalisation_acceptance(
    export_dir: str | Path,
) -> tuple[list[Proposition], SlurryNormalisationAcceptanceResult]:
    before = load_slurry_export_propositions(export_dir)
    after = normalise_slurry_propositions(before)
    generic_keys = sum(
        1 for p in after if is_generic_these_regulations_key(p.cross_reference_key)
    )
    cross_bad = cross_instrument_cross_reference_targets(after)
    citation_commencement = [
        p
        for p in after
        if p.legal_effect_type in {LegalEffectType.CITATION, LegalEffectType.COMMENCEMENT}
    ]
    visible_cc = sum(1 for p in citation_commencement if explorer_visible_default(p))
    summary = SlurryNormalisationAcceptanceResult(
        before_count=len(before),
        after_count=len(after),
        generic_key_count=generic_keys,
        cross_instrument_link_count=len(cross_bad),
        citation_commencement_count=len(citation_commencement),
        citation_commencement_visible_count=visible_cc,
    )
    return after, summary


def assert_slurry_normalisation_acceptance(export_dir: str | Path) -> SlurryNormalisationAcceptanceResult:
    after, summary = evaluate_slurry_normalisation_acceptance(export_dir)

    assert summary.before_count == summary.after_count, (
        "proposition count must be unchanged by normalisation "
        f"(before={summary.before_count}, after={summary.after_count})"
    )
    assert summary.generic_key_count == 0, (
        f"expected zero uk:these-regulations:* keys, found {summary.generic_key_count}"
    )
    assert summary.cross_instrument_link_count == 0, (
        "expected zero cross-instrument cross_reference_targets, "
        f"found {summary.cross_instrument_link_count}"
    )
    assert summary.citation_commencement_count > 0, "expected citation/commencement rows in export"
    assert summary.citation_commencement_visible_count == 0, (
        "citation and commencement propositions must be hidden from default explorer "
        f"({summary.citation_commencement_visible_count} still visible)"
    )

    reg1d = find_proposition(
        after,
        source_record_id=DIFFUSE_SOURCE_2018,
        fragment_locator="regulation 1(d)",
        proposition_text=AGRICULTURAL_LAND_ENGLAND_TEXT,
    )
    assert reg1d.proposition_tier == PropositionTier.SCOPE_RULE
    assert reg1d.legal_effect_type == LegalEffectType.APPLICATION_SCOPE
    assert reg1d.territorial_application == ["England"]
    assert reg1d.is_compliance_relevant is False
    assert reg1d.is_comparison_anchor is True
    assert EXPECTED_REG1D_LABEL_FRAGMENT in (reg1d.label or "")

    reg1a = find_proposition(
        after,
        source_record_id=DIFFUSE_SOURCE_2018,
        fragment_locator="regulation 1(a)",
    )
    assert reg1a.proposition_tier == PropositionTier.INSTRUMENT_METADATA
    assert reg1a.legal_effect_type == LegalEffectType.CITATION
    assert explorer_visible_default(reg1a) is False

    return summary
