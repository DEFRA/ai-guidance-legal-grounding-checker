"""Evaluate live extraction outputs with the offline proposition-fidelity evaluator."""

from __future__ import annotations

from typing import Any

from law_proposition_extractor_pipeline.proposition_fidelity.dimensions import (
    evaluate_case_level_dimensions,
    evaluate_role_dimensions,
)
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import PropositionFidelityCase
from law_proposition_extractor_pipeline.proposition_fidelity.matching import match_roles_for_case, prop_by_id
from law_proposition_extractor_pipeline.proposition_fidelity.results import (
    PropositionFidelityCaseResult,
    PropositionFidelityRoleResult,
)


def _debug_evidence(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""
    meta = prop.get("extraction_debug_meta")
    if isinstance(meta, dict):
        return str(meta.get("evidence_quote") or "")
    return ""


def evaluate_live_propositions(
    case: PropositionFidelityCase,
    props: list[dict[str, Any]],
    *,
    operative_text: str,
    heading_text: str | None,
    diagnostics: list[str],
    article_49a_bundle: dict[str, Any] | None = None,
) -> PropositionFidelityCaseResult:
    """Reuse PF matching + dimensions against live-produced propositions."""
    matches, unexpected = match_roles_for_case(
        case, props, article_49a_bundle=article_49a_bundle
    )
    matched_props = [
        p
        for m in matches
        if m.status == "matched"
        for p in [prop_by_id(props, m.proposition_id)]
        if p is not None
    ]

    role_results: list[PropositionFidelityRoleResult] = []
    for expected in case.gold:
        match = next(m for m in matches if m.role == expected.role)
        prop = prop_by_id(props, match.proposition_id)
        dim_results = evaluate_role_dimensions(
            case=case,
            expected=expected,
            match=match,
            prop=prop,
            operative_text=operative_text,
            heading_text=heading_text,
            all_matched_props=matched_props,
        )
        role_results.append(
            PropositionFidelityRoleResult(
                role=expected.role,
                proposition_id=match.proposition_id,
                status=match.status,  # type: ignore[arg-type]
                dimension_results=dim_results,
                evidence=_debug_evidence(prop),
                notes=match.notes,
                competing_candidates=list(match.competing_candidate_ids),
            )
        )

    case_dims = evaluate_case_level_dimensions(
        case=case,
        matches=matches,
        unexpected=unexpected,
        propositions=props,
        operative_text=operative_text,
        heading_text=heading_text,
    )

    missing_roles = [m.role for m in matches if m.status == "missing"]
    matched_roles = [m.role for m in matches if m.status == "matched"]
    unexpected_payload = [
        {
            "proposition_id": str(p.get("id")),
            "fragment_locator": str(p.get("fragment_locator") or ""),
            "legal_effect_type": str(p.get("legal_effect_type") or ""),
            "proposition_text": str(p.get("proposition_text") or "")[:240],
        }
        for p in unexpected
    ]

    fail_count = sum(
        1 for r in role_results for d in r.dimension_results if d.status == "fail"
    ) + sum(1 for d in case_dims if d.status == "fail")
    warn_count = sum(
        1 for r in role_results for d in r.dimension_results if d.status == "warning"
    ) + sum(1 for d in case_dims if d.status == "warning")

    if fail_count and case.accepted_limitations:
        case_status: Any = "baseline_limitation"
    elif fail_count:
        case_status = "fail"
    elif warn_count:
        case_status = "warning"
    else:
        case_status = "pass"

    return PropositionFidelityCaseResult(
        case_id=case.case_id,
        structural_pattern=case.structural_pattern,
        expected_roles=[g.role for g in case.gold],
        matched_roles=matched_roles,
        missing_roles=missing_roles,
        unexpected_propositions=unexpected_payload,
        role_results=role_results,
        dimension_results=case_dims,
        diagnostics=list(diagnostics),
        produced_count=len(props),
        accepted_limitations=list(case.accepted_limitations),
        case_status=case_status,
    )
