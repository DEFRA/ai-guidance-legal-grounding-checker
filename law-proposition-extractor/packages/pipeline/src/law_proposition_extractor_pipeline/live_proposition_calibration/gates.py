"""Exact and semantic repeatability analysis for live calibration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import LiveCalibrationCaseResult, LiveCalibrationRepetitionResult, StabilityClass


def _fingerprint_props(props: list[dict[str, Any]]) -> str:
    rows = []
    for p in props:
        meta = p.get("extraction_debug_meta") if isinstance(p.get("extraction_debug_meta"), dict) else {}
        rows.append(
            {
                "locator": p.get("fragment_locator"),
                "effect": p.get("legal_effect_type"),
                "text": " ".join(str(p.get("proposition_text") or "").lower().split()),
                "evidence": " ".join(str(meta.get("evidence_quote") or "").lower().split()),
                "path": meta.get("structured_list_path"),
            }
        )
    blob = json.dumps(rows, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _semantic_signature(rep: LiveCalibrationRepetitionResult) -> dict[str, Any]:
    br = rep.benchmark_result
    return {
        "proposition_count": rep.proposition_count,
        "matched_roles": sorted(br.get("matched_roles") or []),
        "missing_roles": sorted(br.get("missing_roles") or []),
        "unexpected_count": len(br.get("unexpected_propositions") or []),
        "case_status": br.get("case_status"),
        "effects": sorted(
            [
                str(r.get("legal_effect_type") or "")
                for r in (br.get("unexpected_propositions") or [])
            ]
        ),
    }


def analyse_case_repeatability(
    case_id: str,
    expected_roles: list[str],
    repetitions: list[LiveCalibrationRepetitionResult],
    *,
    raw_fingerprints: list[str],
    prop_fingerprints: list[str],
) -> LiveCalibrationCaseResult:
    role_sets = [set(r.benchmark_result.get("matched_roles") or []) for r in repetitions]
    counts = [r.proposition_count for r in repetitions]
    variance = max(counts) - min(counts) if counts else 0
    stable_coverage = all(set(expected_roles) <= s for s in role_sets) and len(set(map(frozenset, role_sets))) == 1

    semantic_sigs = [_semantic_signature(r) for r in repetitions]
    semantic_variance: list[str] = []
    if len({json.dumps(s, sort_keys=True) for s in semantic_sigs}) > 1:
        semantic_variance.append("semantic_signature_differs_across_repetitions")
    if variance:
        semantic_variance.append(f"proposition_count_variance={variance}")

    evidence_fps = prop_fingerprints
    evidence_variance: list[str] = []
    if len(set(evidence_fps)) > 1:
        evidence_variance.append("proposition_or_evidence_fingerprint_differs")

    successful = sum(
        1
        for r in repetitions
        if r.parse_status == "ok"
        and r.critical_gate == "pass"
        and r.case_fidelity_gate == "pass"
    )

    failing_all = all(
        r.critical_gate == "fail" or r.case_fidelity_gate == "fail" for r in repetitions
    )
    exact_raw = len(set(raw_fingerprints)) == 1
    exact_props = len(set(prop_fingerprints)) == 1
    semantic_ok = not semantic_variance and stable_coverage

    stability: StabilityClass
    if failing_all:
        stability = "consistently_failing"
    elif exact_raw and exact_props and semantic_ok:
        stability = "exact_stable"
    elif semantic_ok:
        stability = "semantically_stable"
    else:
        stability = "materially_variable"

    findings: list[str] = []
    if not stable_coverage:
        findings.append("expected semantic roles not stable across all repetitions")
    if variance:
        findings.append(f"proposition count varies by {variance}")
    findings.extend(semantic_variance)
    findings.extend(evidence_variance)

    case_fidelity = (
        "pass"
        if all(r.case_fidelity_gate == "pass" for r in repetitions) and stable_coverage
        else "fail"
    )
    repeatability = "pass" if semantic_ok else "fail"

    return LiveCalibrationCaseResult(
        case_id=case_id,
        repetitions=repetitions,
        expected_roles=list(expected_roles),
        successful_repetitions=successful,
        stable_role_coverage=stable_coverage,
        proposition_count_variance=variance,
        semantic_variance=semantic_variance,
        evidence_variance=evidence_variance,
        findings=findings,
        stability=stability,
        case_fidelity_gate=case_fidelity,  # type: ignore[arg-type]
        repeatability_gate=repeatability,  # type: ignore[arg-type]
    )


def raw_fingerprint(raw_responses: list[str]) -> str:
    blob = "\n---\n".join(raw_responses)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def props_fingerprint(props: list[dict[str, Any]]) -> str:
    return _fingerprint_props(props)
