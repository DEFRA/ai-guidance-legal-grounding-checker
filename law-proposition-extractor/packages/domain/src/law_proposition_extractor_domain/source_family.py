"""Source family discovery: related instruments around a legislative target."""

from typing import Any, Literal

from pydantic import BaseModel, Field

SourceFamilySourceRole = Literal[
    "base_act",
    "consolidated_text",
    "corrigendum",
    "amendment",
    "delegated_act",
    "implementing_act",
    "annex",
    "definition_source",
    "guidance",
    "explanatory_material",
    "certificate_model",
    "retained_version",
    "replacement",
    "unknown",
]

SourceFamilyRelationship = Literal[
    "is_target",
    "corrects",
    "amends",
    "supplements",
    "implements",
    "defines_terms_for",
    "explains",
    "replaces",
    "contextual",
    "unknown",
]

SourceFamilyInclusionStatus = Literal[
    "required_core",
    "required_for_scope",
    "optional_context",
    "candidate_needs_review",
    "excluded",
]

SourceFamilyConfidence = Literal["high", "medium", "low"]


class SourceFamilyCandidate(BaseModel):
    """Structured candidate row for related legal instruments around a registry target."""

    id: str = Field(min_length=1)
    target_source_id: str | None = None
    target_citation: str | None = None
    candidate_source_id: str | None = None
    title: str
    citation: str | None = None
    celex: str | None = None
    eli: str | None = None
    url: str | None = None
    source_role: SourceFamilySourceRole = "unknown"
    relationship_to_target: SourceFamilyRelationship = "unknown"
    inclusion_status: SourceFamilyInclusionStatus = "candidate_needs_review"
    confidence: SourceFamilyConfidence = "medium"
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
