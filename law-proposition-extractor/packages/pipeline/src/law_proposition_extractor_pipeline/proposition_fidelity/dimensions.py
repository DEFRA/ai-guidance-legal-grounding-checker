"""Per-dimension fidelity checks (deterministic, no LLM)."""

from __future__ import annotations

import re
from typing import Any

from law_proposition_extractor_pipeline.extract import evidence_locates_verbatim_after_normalisation

from .action_fidelity import (
    evaluate_legacy_action_fidelity,
    evaluate_structured_action_fidelity,
)
from .fixtures import ExpectedProposition, PropositionFidelityCase
from .matching import RoleMatch, _debug_meta, _structured_path, prop_by_id
from .results import DimensionResult

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _blob(prop: dict[str, Any]) -> str:
    meta = _debug_meta(prop)
    return " ".join(
        [
            str(prop.get("proposition_text") or ""),
            str(prop.get("legal_subject") or ""),
            str(prop.get("action") or ""),
            " ".join(str(x) for x in (prop.get("conditions") or [])),
            " ".join(str(x) for x in (prop.get("affected_subjects") or [])),
            str(meta.get("evidence_quote") or ""),
            str(meta.get("display_label") or ""),
            str(prop.get("label") or ""),
        ]
    )


def _evidence(prop: dict[str, Any]) -> str:
    meta = _debug_meta(prop)
    return str(meta.get("evidence_quote") or meta.get("candidate_evidence_text") or "")


def _status_fail(
    dimension: str,
    *,
    detail: str,
    expected: str = "",
    actual: str = "",
    stage: str = "extraction",
) -> DimensionResult:
    return DimensionResult(
        dimension=dimension,
        status="fail",
        detail=detail,
        expected=expected,
        actual=actual,
        severity_policy="hard_failure",
        likely_pipeline_stage=stage,
    )


def _status_pass(dimension: str, detail: str = "") -> DimensionResult:
    return DimensionResult(dimension=dimension, status="pass", detail=detail)


def _status_warn(
    dimension: str, detail: str, *, stage: str = "review"
) -> DimensionResult:
    return DimensionResult(
        dimension=dimension,
        status="warning",
        detail=detail,
        severity_policy="warning",
        likely_pipeline_stage=stage,
    )


def _status_na(dimension: str, detail: str = "") -> DimensionResult:
    return DimensionResult(
        dimension=dimension,
        status="not_applicable",
        detail=detail,
        severity_policy="informational",
    )


def evaluate_role_dimensions(
    *,
    case: PropositionFidelityCase,
    expected: ExpectedProposition,
    match: RoleMatch,
    prop: dict[str, Any] | None,
    operative_text: str,
    heading_text: str | None,
    all_matched_props: list[dict[str, Any]],
) -> list[DimensionResult]:
    results: list[DimensionResult] = []

    # coverage (per-role)
    if match.status == "missing":
        results.append(
            _status_fail(
                "coverage",
                detail=f"expected operative role missing: {expected.role}",
                expected=expected.short_legal_description,
                stage="extraction",
            )
        )
        for dim in (
            "atomicity",
            "no_false_merge",
            "no_false_split",
            "actor_fidelity",
            "action_fidelity",
            "object_fidelity",
            "condition_fidelity",
            "exception_fidelity",
            "threshold_fidelity",
            "cross_reference_fidelity",
            "evidence_fidelity",
            "structural_context_boundary",
            "legal_effect_fidelity",
            "completeness_fidelity",
        ):
            results.append(_status_na(dim, "role missing"))
        return results

    if match.status == "ambiguous":
        results.append(
            _status_warn(
                "coverage",
                f"ambiguous match for {expected.role}; candidates="
                f"{list(match.competing_candidate_ids)}",
                stage="benchmark_matching",
            )
        )
        for dim in (
            "atomicity",
            "no_false_merge",
            "no_false_split",
            "actor_fidelity",
            "action_fidelity",
            "object_fidelity",
            "condition_fidelity",
            "exception_fidelity",
            "threshold_fidelity",
            "cross_reference_fidelity",
            "evidence_fidelity",
            "structural_context_boundary",
            "legal_effect_fidelity",
            "completeness_fidelity",
        ):
            results.append(_status_na(dim, "ambiguous match — human review"))
        return results

    assert prop is not None
    results.append(_status_pass("coverage", f"matched {expected.role}"))

    # atomicity — one independently reviewable claim (heuristic: single legal_effect)
    effect = str(prop.get("legal_effect_type") or "")
    text = str(prop.get("proposition_text") or "")
    # Do not treat the "must" inside "must not" as a separate obligation cue.
    has_prohibition_cue = bool(re.search(r"\bmust\s+not\b", text, flags=re.IGNORECASE))
    has_obligation_cue = bool(
        re.search(r"\bmust\b(?!\s+not\b)", text, flags=re.IGNORECASE)
    )
    merge_cues = has_prohibition_cue and has_obligation_cue
    if merge_cues and expected.legal_effect_type in {"obligation", "prohibition"}:
        results.append(
            _status_fail(
                "atomicity",
                detail="proposition appears to merge obligation and prohibition",
                actual=text[:240],
                stage="extraction_decomposition",
            )
        )
        results.append(
            _status_fail(
                "no_false_merge",
                detail="obligation and prohibition appear merged",
                actual=text[:240],
                stage="extraction_decomposition",
            )
        )
    else:
        results.append(_status_pass("atomicity"))
        results.append(_status_pass("no_false_merge"))

    # no_false_split — if gold marks may_share and we matched exactly one role to this prop
    share_with = set(expected.may_share_source_fragment_with)
    same_id_roles = [
        p
        for p in all_matched_props
        if str(p.get("id")) == str(prop.get("id"))
    ]
    if share_with and len(same_id_roles) > 1:
        results.append(
            _status_fail(
                "no_false_split",
                detail="indivisible claim appears split across roles unexpectedly",
                stage="extraction_decomposition",
            )
        )
    else:
        results.append(_status_pass("no_false_split"))

    # actor
    if expected.required_actor:
        subject = str(prop.get("legal_subject") or "")
        if _norm(expected.required_actor) in _norm(subject) or _norm(
            expected.required_actor
        ) in _norm(text):
            results.append(_status_pass("actor_fidelity"))
        else:
            results.append(
                _status_fail(
                    "actor_fidelity",
                    detail="wrong or missing actor",
                    expected=expected.required_actor,
                    actual=subject or text[:160],
                    stage="extraction",
                )
            )
    else:
        results.append(_status_na("actor_fidelity"))

    # action — structured invariants when present; else legacy required_action matcher
    if expected.action_expectation is not None:
        meta = _debug_meta(prop)
        label_text = str(meta.get("display_label") or prop.get("label") or "")
        results.append(
            evaluate_structured_action_fidelity(
                expectation=expected.action_expectation,
                prop=prop,
                operative_text=operative_text,
                heading_text=heading_text,
                evidence=_evidence(prop),
                label_text=label_text,
            )
        )
    elif expected.required_action:
        results.append(
            evaluate_legacy_action_fidelity(
                required_action=expected.required_action,
                prop=prop,
            )
        )
    else:
        results.append(_status_na("action_fidelity"))

    # object
    if expected.object:
        if _norm(expected.object) in _norm(_blob(prop)):
            results.append(_status_pass("object_fidelity"))
        else:
            results.append(
                _status_fail(
                    "object_fidelity",
                    detail="legal object / subject-matter not preserved",
                    expected=expected.object,
                    actual=_blob(prop)[:200],
                    stage="extraction",
                )
            )
    else:
        results.append(_status_na("object_fidelity"))

    # conditions
    if expected.conditions:
        blob = _blob(prop)
        missing = [c for c in expected.conditions if _norm(c) not in _norm(blob)]
        if missing:
            results.append(
                _status_fail(
                    "condition_fidelity",
                    detail=f"material condition omitted: {missing[0]}",
                    expected="; ".join(expected.conditions),
                    actual=" | ".join(str(x) for x in (prop.get("conditions") or [])),
                    stage="extraction",
                )
            )
        else:
            results.append(_status_pass("condition_fidelity"))
    else:
        results.append(_status_na("condition_fidelity"))

    # exceptions
    if expected.exceptions:
        blob = _blob(prop)
        missing = [e for e in expected.exceptions if _norm(e) not in _norm(blob)]
        # derogation rows are themselves exceptions — path/effect can satisfy
        if missing and effect == "derogation" and expected.legal_effect_type == "derogation":
            results.append(_status_pass("exception_fidelity", "derogation row itself"))
        elif missing:
            results.append(
                _status_fail(
                    "exception_fidelity",
                    detail=f"exception / derogation lost or mistargeted: {missing[0]}",
                    expected="; ".join(expected.exceptions),
                    stage="legal_rule_relationships",
                )
            )
        else:
            results.append(_status_pass("exception_fidelity"))
    else:
        results.append(_status_na("exception_fidelity"))

    # thresholds
    if expected.thresholds:
        blob = _blob(prop)
        missing = []
        for thr in expected.thresholds:
            if _norm(thr) in _norm(blob):
                continue
            # numeric token presence (e.g. "10" from "10 metres")
            nums = _NUM_RE.findall(thr)
            if nums and all(n in blob for n in nums):
                continue
            missing.append(thr)
        if missing:
            results.append(
                _status_fail(
                    "threshold_fidelity",
                    detail=f"numerical threshold changed or omitted: {missing[0]}",
                    expected="; ".join(expected.thresholds),
                    actual=blob[:200],
                    stage="extraction",
                )
            )
        else:
            results.append(_status_pass("threshold_fidelity"))
    else:
        results.append(_status_na("threshold_fidelity"))

    # cross-references
    if expected.cross_references:
        blob = _blob(prop)
        xrefs = " ".join(
            str(x)
            for x in (
                list(prop.get("explicit_cross_reference_targets") or [])
                + list(prop.get("cross_reference_targets") or [])
            )
        )
        hay = f"{blob} {xrefs} {prop.get('fragment_locator') or ''}"
        missing = [c for c in expected.cross_references if _norm(c) not in _norm(hay)]
        if missing:
            results.append(
                _status_fail(
                    "cross_reference_fidelity",
                    detail=f"cross-reference not retained: {missing[0]}",
                    expected="; ".join(expected.cross_references),
                    stage="extraction",
                )
            )
        else:
            results.append(_status_pass("cross_reference_fidelity"))
    else:
        results.append(_status_na("cross_reference_fidelity"))

    # evidence fidelity
    evidence = _evidence(prop)
    for marker in expected.evidence_markers:
        if evidence and _norm(marker) not in _norm(evidence) and _norm(marker) not in _norm(
            text
        ):
            results.append(
                _status_fail(
                    "evidence_fidelity",
                    detail=f"evidence missing marker: {marker}",
                    expected=marker,
                    actual=evidence[:200],
                    stage="evidence_validation",
                )
            )
            break
    else:
        if evidence and operative_text:
            ok, _, _ = evidence_locates_verbatim_after_normalisation(evidence, operative_text)
            if not ok:
                # commentary / heading-only contamination
                if heading_text and _norm(evidence) in _norm(heading_text):
                    results.append(
                        _status_fail(
                            "evidence_fidelity",
                            detail="evidence quote uses heading-only text",
                            actual=evidence[:200],
                            stage="evidence_validation",
                        )
                    )
                else:
                    results.append(
                        _status_fail(
                            "evidence_fidelity",
                            detail="evidence not found in operative source text",
                            actual=evidence[:200],
                            stage="evidence_validation",
                        )
                    )
            else:
                results.append(_status_pass("evidence_fidelity"))
        elif expected.evidence_markers:
            results.append(
                _status_warn(
                    "evidence_fidelity",
                    "no evidence_quote on proposition; markers checked in text only",
                    stage="extraction",
                )
            )
        else:
            results.append(_status_na("evidence_fidelity"))

    # structural context boundary
    if heading_text:
        if _norm(text) == _norm(heading_text) or (
            evidence and _norm(evidence) == _norm(heading_text)
        ):
            results.append(
                _status_fail(
                    "structural_context_boundary",
                    detail="heading-only proposition or evidence accepted",
                    actual=text[:200],
                    stage="extraction",
                )
            )
        else:
            # heading concepts may appear in label
            results.append(_status_pass("structural_context_boundary"))
    else:
        results.append(
            _status_pass(
                "structural_context_boundary",
                "unheaded provision — normal extraction",
            )
        )

    for forbidden in case.sibling_heading_forbidden:
        if _norm(forbidden) in _norm(evidence) or (
            _norm(forbidden) in _norm(text) and _norm(forbidden) not in _norm(operative_text)
        ):
            results.append(
                _status_fail(
                    "structural_context_boundary",
                    detail=f"sibling heading leaked: {forbidden}",
                    stage="structural_headings",
                )
            )
            break

    # legal effect
    if expected.legal_effect_type:
        if effect == expected.legal_effect_type:
            results.append(_status_pass("legal_effect_fidelity"))
        else:
            results.append(
                _status_fail(
                    "legal_effect_fidelity",
                    detail="legal-effect classification mismatch",
                    expected=expected.legal_effect_type,
                    actual=effect,
                    stage="proposition_classification",
                )
            )
    else:
        results.append(_status_na("legal_effect_fidelity"))

    # structured list path (folded into exception/coverage diagnostics via notes)
    if expected.structured_list_path:
        path = _structured_path(prop)
        if path != expected.structured_list_path:
            results.append(
                _status_fail(
                    "coverage",
                    detail=(
                        f"structured-list path changed: expected "
                        f"{expected.structured_list_path}, got {path}"
                    ),
                    expected=expected.structured_list_path,
                    actual=str(path),
                    stage="structured_list_decomposition",
                )
            )

    # completeness
    if expected.expected_completeness:
        actual_c = str(_debug_meta(prop).get("completeness_status") or "")
        if not actual_c:
            results.append(
                _status_warn(
                    "completeness_fidelity",
                    "completeness_status absent on proposition meta",
                    stage="proposition_completeness",
                )
            )
        elif actual_c == expected.expected_completeness:
            results.append(_status_pass("completeness_fidelity"))
        else:
            sev = expected.completeness_severity
            if sev == "fail":
                results.append(
                    _status_fail(
                        "completeness_fidelity",
                        detail="completeness classification mismatch",
                        expected=expected.expected_completeness,
                        actual=actual_c,
                        stage="proposition_completeness",
                    )
                )
            else:
                results.append(
                    _status_warn(
                        "completeness_fidelity",
                        f"completeness {actual_c} vs expected "
                        f"{expected.expected_completeness}",
                        stage="proposition_completeness",
                    )
                )
    else:
        results.append(_status_na("completeness_fidelity"))

    return results


def evaluate_case_level_dimensions(
    *,
    case: PropositionFidelityCase,
    matches: list[RoleMatch],
    unexpected: list[dict[str, Any]],
    propositions: list[dict[str, Any]],
    operative_text: str,
    heading_text: str | None,
) -> list[DimensionResult]:
    out: list[DimensionResult] = []
    missing = [m for m in matches if m.status == "missing"]
    if missing:
        out.append(
            _status_fail(
                "coverage",
                detail=f"{len(missing)} expected role(s) missing",
                expected=str(case.expected_proposition_count),
                actual=str(len(propositions)),
            )
        )
    else:
        out.append(_status_pass("coverage", "all expected roles present or ambiguous"))

    if unexpected:
        # Article 49a seventh prop is a hard failure; others may be warnings if accepted
        if case.case_id == "article_49a" or len(unexpected) > 0:
            detail_bits = [
                str(p.get("proposition_text") or p.get("id") or "")[:120]
                for p in unexpected
            ]
            out.append(
                _status_fail(
                    "coverage",
                    detail=f"unexpected proposition(s): {detail_bits}",
                    stage="extraction",
                )
            )

    if heading_text:
        for prop in propositions:
            text = str(prop.get("proposition_text") or "")
            evidence = _evidence(prop)
            if _norm(text) == _norm(heading_text):
                out.append(
                    _status_fail(
                        "structural_context_boundary",
                        detail="standalone heading proposition present",
                        actual=text[:200],
                    )
                )
            if evidence and _norm(evidence) == _norm(heading_text):
                out.append(
                    _status_fail(
                        "evidence_fidelity",
                        detail="heading used as evidence",
                        actual=evidence[:200],
                    )
                )

    # control case: exactly one prop
    if "control" in case.structural_pattern or "exactly_one" in case.structural_pattern:
        if len(propositions) != 1:
            out.append(
                _status_fail(
                    "no_false_split",
                    detail=(
                        f"control provision expected exactly 1 proposition; "
                        f"got {len(propositions)}"
                    ),
                    stage="extraction_decomposition",
                )
            )
        else:
            out.append(_status_pass("no_false_split", "control remains single proposition"))

    return out


def heading_only_candidate_rejected(heading: str, operative_text: str) -> bool:
    """Prove a heading-only fake candidate is rejected by production evidence checks."""
    from law_proposition_extractor_pipeline.extract import _validate_v2_items

    accepted, errors, issues = _validate_v2_items(
        [
            {
                "proposition_text": heading,
                "evidence_text": heading,
                "reason": "heading-only fake candidate",
            }
        ],
        operative_text,
        limit=4,
    )
    return accepted == [] and bool(errors or issues)
