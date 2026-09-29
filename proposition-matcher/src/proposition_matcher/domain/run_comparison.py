from typing import Any, Literal

from pydantic import BaseModel, Field


class RunComparisonChangeGroup(BaseModel):
    added_count: int = 0
    removed_count: int = 0
    changed_count: int = 0
    added_ids: list[str] = Field(default_factory=list)
    removed_ids: list[str] = Field(default_factory=list)
    changed_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RunComparisonSummary(BaseModel):
    id: str
    baseline_run_id: str
    candidate_run_id: str
    generated_at: str
    status: Literal["unchanged", "changed", "regression", "inconclusive"]
    source_changes: RunComparisonChangeGroup
    snapshot_changes: RunComparisonChangeGroup
    fragment_changes: RunComparisonChangeGroup
    proposition_changes: RunComparisonChangeGroup
    divergence_changes: RunComparisonChangeGroup
    quality_changes: RunComparisonChangeGroup
    artifact_hash_changes: RunComparisonChangeGroup
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
