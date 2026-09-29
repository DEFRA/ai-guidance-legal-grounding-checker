"""Typed live proposition calibration result models (evaluation-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from law_proposition_extractor_pipeline.proposition_fidelity.results import PropositionFidelityCaseResult

FailureOrigin = Literal[
    "model_omission",
    "model_invention",
    "model_false_merge",
    "model_false_split",
    "model_evidence_error",
    "model_structure_error",
    "response_format_error",
    "deterministic_validation_error",
    "deterministic_reconciliation_error",
    "gold_or_evaluator_ambiguity",
    "infrastructure_error",
    "human_review_required",
]

StabilityClass = Literal[
    "exact_stable",
    "semantically_stable",
    "materially_variable",
    "consistently_failing",
]

GateStatus = Literal["pass", "fail"]


@dataclass
class FailureOriginFinding:
    case_id: str
    repetition: int
    dimension: str
    role: str | None
    expected_invariant: str
    raw_model_row_or_omission: str
    validator_result: str
    final_proposition_result: str
    likely_origin: FailureOrigin
    severity: Literal["critical", "warning", "informational"]
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "repetition": self.repetition,
            "dimension": self.dimension,
            "role": self.role,
            "expected_invariant": self.expected_invariant,
            "raw_model_row_or_omission": self.raw_model_row_or_omission,
            "validator_result": self.validator_result,
            "final_proposition_result": self.final_proposition_result,
            "likely_origin": self.likely_origin,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass
class LiveCalibrationRepetitionResult:
    repetition: int
    raw_response_status: str
    parse_status: str
    validation_status: str
    proposition_count: int
    benchmark_result: dict[str, Any]
    latency_seconds: float | None = None
    token_usage: dict[str, Any] | None = None
    diagnostics: list[str] = field(default_factory=list)
    provider_call_count: int = 0
    provider_retry_count: int = 0
    json_repair_applied: bool = False
    heading_boundary: dict[str, Any] = field(default_factory=dict)
    article_49a_detail: dict[str, Any] | None = None
    failure_origins: list[FailureOriginFinding] = field(default_factory=list)
    critical_gate: GateStatus = "pass"
    case_fidelity_gate: GateStatus = "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "repetition": self.repetition,
            "raw_response_status": self.raw_response_status,
            "parse_status": self.parse_status,
            "validation_status": self.validation_status,
            "proposition_count": self.proposition_count,
            "benchmark_result": dict(self.benchmark_result),
            "latency_seconds": self.latency_seconds,
            "token_usage": dict(self.token_usage) if self.token_usage else None,
            "diagnostics": list(self.diagnostics),
            "provider_call_count": self.provider_call_count,
            "provider_retry_count": self.provider_retry_count,
            "json_repair_applied": self.json_repair_applied,
            "heading_boundary": dict(self.heading_boundary),
            "article_49a_detail": dict(self.article_49a_detail)
            if self.article_49a_detail
            else None,
            "failure_origins": [f.to_dict() for f in self.failure_origins],
            "critical_gate": self.critical_gate,
            "case_fidelity_gate": self.case_fidelity_gate,
        }


@dataclass
class LiveCalibrationCaseResult:
    case_id: str
    repetitions: list[LiveCalibrationRepetitionResult]
    expected_roles: list[str]
    successful_repetitions: int
    stable_role_coverage: bool
    proposition_count_variance: int
    semantic_variance: list[str] = field(default_factory=list)
    evidence_variance: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    stability: StabilityClass = "semantically_stable"
    case_fidelity_gate: GateStatus = "pass"
    repeatability_gate: GateStatus = "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "repetitions": [r.to_dict() for r in self.repetitions],
            "expected_roles": list(self.expected_roles),
            "successful_repetitions": self.successful_repetitions,
            "stable_role_coverage": self.stable_role_coverage,
            "proposition_count_variance": self.proposition_count_variance,
            "semantic_variance": list(self.semantic_variance),
            "evidence_variance": list(self.evidence_variance),
            "findings": list(self.findings),
            "stability": self.stability,
            "case_fidelity_gate": self.case_fidelity_gate,
            "repeatability_gate": self.repeatability_gate,
        }


@dataclass
class LivePropositionCalibrationResult:
    calibration_run_id: str
    model: dict[str, Any]
    prompt_version: str
    cases: list[LiveCalibrationCaseResult]
    totals: dict[str, Any]
    repeatability: dict[str, Any]
    critical_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dimension_totals: dict[str, dict[str, int]] = field(default_factory=dict)
    promotion_candidates: list[dict[str, Any]] = field(default_factory=list)
    runtime_seconds: float = 0.0
    provider_call_count: int = 0
    provider_retry_count: int = 0
    estimated_cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "calibration_run_id": self.calibration_run_id,
            "model": dict(self.model),
            "prompt_version": self.prompt_version,
            "cases": [c.to_dict() for c in self.cases],
            "totals": dict(self.totals),
            "repeatability": dict(self.repeatability),
            "critical_failures": list(self.critical_failures),
            "warnings": list(self.warnings),
            "dimension_totals": {
                dim: dict(counts)
                for dim, counts in sorted(self.dimension_totals.items())
            },
            "promotion_candidates": list(self.promotion_candidates),
            "runtime_seconds": self.runtime_seconds,
            "provider_call_count": self.provider_call_count,
            "provider_retry_count": self.provider_retry_count,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


def case_result_from_pf(
    pf: PropositionFidelityCaseResult,
) -> dict[str, Any]:
    """Serialize a PF case result for embedding in a live repetition."""
    return pf.to_dict()
