from typing import Any, Literal

from pydantic import BaseModel, Field


class RunQualityGateResult(BaseModel):
    gate_id: str
    name: str
    status: Literal["pass", "warning", "fail", "skipped"]
    message: str = ""
    error_count: int = 0
    warning_count: int = 0
    affected_artifact_ids: list[str] = Field(default_factory=list)


class RunQualitySummary(BaseModel):
    run_id: str
    generated_at: str
    status: Literal["pass", "pass_with_warnings", "fail"]
    source_count: int
    snapshot_count: int
    fragment_count: int
    proposition_count: int
    divergence_assessment_count: int | None = None
    fetch_attempt_count: int
    parse_trace_count: int
    proposition_extraction_trace_count: int
    source_inventory_row_count: int
    source_target_link_count: int
    source_categorisation_rationale_count: int
    error_count: int
    warning_count: int
    gate_results: list[RunQualityGateResult] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
