from typing import Any, Literal

from pydantic import BaseModel, Field

PipelineReviewDecisionType = Literal[
    "approved",
    "rejected",
    "needs_review",
    "overridden",
    "deferred",
]


class PipelineReviewDecision(BaseModel):
    id: str
    run_id: str
    artifact_type: str
    artifact_id: str
    decision: PipelineReviewDecisionType
    reviewer: str | None = None
    reviewed_at: str
    reason: str = ""
    replacement_value: Any | None = None
    evidence: list[str] = Field(default_factory=list)
    applies_to_field: str | None = None
    supersedes_decision_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
