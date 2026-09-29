"""Typed benchmark result model (test/audit only — not a production artifact)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DimensionStatus = Literal["pass", "warning", "fail", "not_applicable"]
RoleStatus = Literal["matched", "missing", "ambiguous", "unexpected"]

FIDELITY_DIMENSIONS: tuple[str, ...] = (
    "coverage",
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
)


@dataclass
class DimensionResult:
    dimension: str
    status: DimensionStatus
    detail: str = ""
    expected: str = ""
    actual: str = ""
    severity_policy: Literal["hard_failure", "warning", "informational"] = "hard_failure"
    likely_pipeline_stage: str = ""
    audit: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "dimension": self.dimension,
            "status": self.status,
            "detail": self.detail,
            "expected": self.expected,
            "actual": self.actual,
            "severity_policy": self.severity_policy,
            "likely_pipeline_stage": self.likely_pipeline_stage,
        }
        if self.audit is not None:
            out["audit"] = dict(self.audit)
        return out


@dataclass
class PropositionFidelityRoleResult:
    role: str
    proposition_id: str | None
    status: RoleStatus
    dimension_results: list[DimensionResult] = field(default_factory=list)
    evidence: str = ""
    notes: str = ""
    competing_candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "proposition_id": self.proposition_id,
            "status": self.status,
            "dimension_results": [d.to_dict() for d in self.dimension_results],
            "evidence": self.evidence,
            "notes": self.notes,
            "competing_candidates": list(self.competing_candidates),
        }


@dataclass
class PropositionFidelityCaseResult:
    case_id: str
    structural_pattern: str
    expected_roles: list[str]
    matched_roles: list[str]
    missing_roles: list[str]
    unexpected_propositions: list[dict[str, Any]]
    role_results: list[PropositionFidelityRoleResult]
    dimension_results: list[DimensionResult]
    diagnostics: list[str] = field(default_factory=list)
    produced_count: int = 0
    accepted_limitations: list[str] = field(default_factory=list)
    case_status: Literal["pass", "warning", "fail", "baseline_limitation"] = "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "structural_pattern": self.structural_pattern,
            "expected_roles": list(self.expected_roles),
            "matched_roles": list(self.matched_roles),
            "missing_roles": list(self.missing_roles),
            "unexpected_propositions": list(self.unexpected_propositions),
            "role_results": [r.to_dict() for r in self.role_results],
            "dimension_results": [d.to_dict() for d in self.dimension_results],
            "diagnostics": list(self.diagnostics),
            "produced_count": self.produced_count,
            "accepted_limitations": list(self.accepted_limitations),
            "case_status": self.case_status,
        }


@dataclass
class PropositionFidelityBenchmarkResult:
    benchmark_version: str
    cases: list[PropositionFidelityCaseResult]
    totals: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    dimension_totals: dict[str, dict[str, int]] = field(default_factory=dict)
    runtime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_version": self.benchmark_version,
            "cases": [c.to_dict() for c in self.cases],
            "totals": dict(self.totals),
            "warnings": list(self.warnings),
            "failures": list(self.failures),
            "dimension_totals": {
                dim: dict(counts) for dim, counts in sorted(self.dimension_totals.items())
            },
            "runtime_seconds": self.runtime_seconds,
        }


def empty_dimension_totals() -> dict[str, dict[str, int]]:
    return {
        dim: {"pass": 0, "warning": 0, "fail": 0, "not_applicable": 0}
        for dim in FIDELITY_DIMENSIONS
    }


def accumulate_dimension(
    totals: dict[str, dict[str, int]], result: DimensionResult
) -> None:
    bucket = totals.setdefault(
        result.dimension, {"pass": 0, "warning": 0, "fail": 0, "not_applicable": 0}
    )
    bucket[result.status] = bucket.get(result.status, 0) + 1
