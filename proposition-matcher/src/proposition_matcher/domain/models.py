from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from .enums import ConfidenceLevel, DivergenceType, ReviewStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class Topic(BaseModel):
    id: str
    name: str
    description: str = ""
    subject_tags: list[str] = Field(default_factory=list)


class Cluster(BaseModel):
    id: str
    topic_id: str
    name: str
    description: str = ""
    source_record_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("source_record_ids", "source_document_ids"),
    )


class SourceRecord(BaseModel):
    id: str
    title: str
    jurisdiction: str
    citation: str
    kind: str
    authoritative_text: str = ""
    authoritative_locator: str = "document:full"
    status: str = "working"
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    provenance: str = "manual"
    as_of_date: date | None = None
    retrieved_at: datetime | None = None
    content_hash: str | None = None
    version_id: str | None = None
    current_snapshot_id: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceSnapshot(BaseModel):
    id: str
    source_record_id: str
    version_id: str
    authoritative_text: str
    authoritative_locator: str = "document:full"
    provenance: str
    as_of_date: date | None = None
    retrieved_at: datetime
    content_hash: str
    raw_artifact_uri: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    parsed_at: datetime | None = None
    authority: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceFragment(BaseModel):
    id: str
    fragment_id: str | None = None
    source_record_id: str
    source_snapshot_id: str
    fragment_type: str = "unknown"
    locator: str
    fragment_text: str
    fragment_hash: str
    text_hash: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    parent_fragment_id: str | None = None
    order_index: int | None = None
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_integrity_fields(self) -> "SourceFragment":
        if not self.fragment_id:
            self.fragment_id = self.id
        if not self.text_hash and self.fragment_hash:
            self.text_hash = self.fragment_hash
        if not self.fragment_hash and self.text_hash:
            self.fragment_hash = self.text_hash
        return self


class SourceParseTrace(BaseModel):
    id: str
    source_record_id: str
    source_snapshot_id: str
    parser_name: str
    parser_version: str
    started_at: datetime
    finished_at: datetime
    status: Literal["success", "partial_success", "failed", "skipped"]
    input_content_hash: str | None = None
    output_fragment_ids: list[str] = Field(default_factory=list)
    fragment_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ReviewDecision(BaseModel):
    id: str
    target_type: str
    target_id: str
    previous_status: ReviewStatus | None = None
    new_status: ReviewStatus = ReviewStatus.PROPOSED
    reviewer: str = "system"
    timestamp: datetime = Field(default_factory=utc_now)
    note: str = ""
    edited_fields: dict[str, Any] | None = None

    # Legacy compatibility fields kept in-sync in model validator.
    review_status: ReviewStatus | None = None
    rationale: str = ""
    decided_by: str | None = None
    decided_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_legacy_fields(self) -> "ReviewDecision":
        if self.review_status is None:
            self.review_status = self.new_status
        if self.decided_by is None:
            self.decided_by = self.reviewer
        if self.decided_at is None:
            self.decided_at = self.timestamp
        if not self.rationale and self.note:
            self.rationale = self.note
        if not self.note and self.rationale:
            self.note = self.rationale
        return self


class RunArtifact(BaseModel):
    id: str
    run_id: str
    artifact_type: str
    provenance: str
    created_at: datetime = Field(default_factory=utc_now)
    content_hash: str
    storage_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceFetchMetadata(BaseModel):
    id: str
    source_record_id: str
    authority: str
    authority_source_id: str | None = None
    source_identifier: str | None = None
    citation: str | None = None
    source_url: str | None = None
    retrieved_at: datetime | None = None
    content_hash: str
    fetch_status: str
    response_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_artifact_uri: str | None = None
    parsed_artifact_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceFetchAttempt(BaseModel):
    id: str
    source_record_id: str
    attempt_number: int
    started_at: datetime
    finished_at: datetime
    status: str
    url: str | None = None
    authority: str
    http_status: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    response_content_type: str | None = None
    response_content_length: int | None = None
    content_hash: str | None = None
    cache_key: str | None = None
    raw_artifact_uri: str | None = None
    method: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceInventoryRow(BaseModel):
    id: str
    source_record_id: str
    jurisdiction: str
    instrument_id: str
    title: str
    instrument_type: str
    status: str
    version_id: str | None = None
    consolidation_date: date | None = None
    source_url: str | None = None
    citation: str | None = None
    content_hash: str
    source_role: str = "base_act"
    relationship_to_analysis: str = "analysis_target"
    fetch_metadata_id: str | None = None
    target_link_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceInventoryArtifact(BaseModel):
    id: str
    run_id: str
    created_at: datetime = Field(default_factory=utc_now)
    inventory_version: str = "0.1"
    rows: list[SourceInventoryRow] = Field(default_factory=list)
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceCategorisationRationale(BaseModel):
    source_record_id: str
    source_inventory_row_id: str | None = None
    source_target_link_id: str | None = None
    source_role: str
    relationship_to_analysis: str
    confidence: str
    method: str
    reason: str
    evidence: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class SourceTargetLink(BaseModel):
    id: str
    source_record_id: str
    target_source_record_id: str | None = None
    target_citation: str | None = None
    target_instrument_id: str | None = None
    link_type: str
    confidence: str
    method: str
    reason: str
    evidence: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class RunStageTrace(BaseModel):
    stage_name: str
    run_id: str
    timestamp: str
    started_at: str
    finished_at: str
    status: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    strategy_used: str = "unknown"
    model_alias_used: str | None = None
    duration_ms: int = 0
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_artifact_ids: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PropositionExtractionTrace(BaseModel):
    id: str
    proposition_id: str
    proposition_key: str | None = None
    source_record_id: str
    source_snapshot_id: str | None = None
    source_fragment_id: str | None = None
    extraction_method: Literal["heuristic", "llm", "manual", "imported", "fallback"]
    extractor_name: str
    extractor_version: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: Literal["success", "partial_success", "failed", "skipped"]
    prompt_id: str | None = None
    prompt_version: str | None = None
    rule_id: str | None = None
    rule_version: str | None = None
    evidence_text: str | None = None
    evidence_locator: str | None = None
    confidence: Literal["high", "medium", "low"]
    reason: str
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class Proposition(BaseModel):
    id: str
    proposition_key: str | None = None
    proposition_version_id: str | None = None
    observed_in_run_id: str | None = None
    topic_id: str
    cluster_id: str | None = None
    source_record_id: str = Field(
        validation_alias=AliasChoices("source_record_id", "source_document_id"),
    )
    source_snapshot_id: str | None = None
    source_fragment_id: str | None = None
    fragment_locator: str | None = None
    jurisdiction: str
    article_reference: str | None = None
    proposition_text: str
    label: str = ""
    short_name: str = ""
    slug: str = ""
    legal_subject: str
    action: str
    conditions: list[str] = Field(default_factory=list)
    authority: str | None = None
    required_documents: list[str] = Field(default_factory=list)
    affected_subjects: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    cross_reference_key: str | None = None
    cross_reference_targets: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    notes: str = ""


PropositionCompletenessStatus = Literal["complete", "context_dependent", "fragmentary"]

PropositionCompletenessConfidence = Literal["high", "medium", "low"]

PropositionCompletenessMethod = Literal["deterministic", "llm", "manual", "fallback"]


class PropositionCompletenessAssessment(BaseModel):
    """Usability/readability of an extracted proposition in isolation (not legal truth)."""

    id: str
    proposition_id: str
    proposition_key: str | None = None
    status: PropositionCompletenessStatus
    confidence: PropositionCompletenessConfidence
    reason: str
    missing_context: list[str] = Field(default_factory=list)
    suggested_display_statement: str | None = None
    context_injections: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    method: PropositionCompletenessMethod = "deterministic"
    signals: dict[str, Any] = Field(default_factory=dict)

    @field_validator("missing_context", mode="after")
    @classmethod
    def _allowed_missing_context(cls, values: list[str]) -> list[str]:
        allowed = {
            "instrument_identity",
            "article_locator",
            "actor",
            "object",
            "condition",
            "exception",
            "defined_term",
            "cross_reference",
        }
        for item in values:
            if item not in allowed:
                raise ValueError(f"missing_context value not allowed: {item!r}")
        return values


class DivergenceFinding(BaseModel):
    id: str
    proposition_id: str
    comparator_proposition_id: str
    jurisdiction_a: str
    jurisdiction_b: str
    common_ancestor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DivergenceObservation(BaseModel):
    id: str
    finding_id: str | None = None
    proposition_id: str
    comparator_proposition_id: str
    jurisdiction_a: str
    jurisdiction_b: str
    common_ancestor: str | None = None
    source_snapshot_ids: list[str] = Field(default_factory=list)
    primary_source_fragment_id: str | None = None
    comparator_source_fragment_id: str | None = None
    supporting_source_fragment_ids: list[str] = Field(default_factory=list)
    common_ancestor_fragment_id: str | None = None
    context_note: str | None = None
    why_these_fragments: str | None = None
    as_of_date: date | None = None
    divergence_exists: bool | None = None
    divergence_type: DivergenceType = DivergenceType.UNKNOWN
    affected_subjects: list[str] = Field(default_factory=list)
    operational_impact: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    rationale: str = ""
    sources_checked: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensure_finding_id(self) -> "DivergenceObservation":
        if not self.finding_id:
            self.finding_id = (
                "finding-" + self.proposition_id + "-" + self.comparator_proposition_id
            )
        return self


class DivergenceAssessment(DivergenceObservation):
    # Backward-compatible alias model; canonical point-in-time record is DivergenceObservation.
    pass


class ComparisonRun(BaseModel):
    id: str
    topic_id: str
    cluster_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    model_profile: str = "demo"
    workflow_mode: str = "divergence"
    source_record_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("source_record_ids", "source_document_ids"),
    )
    source_snapshot_ids: list[str] = Field(default_factory=list)
    source_fragment_ids: list[str] = Field(default_factory=list)
    proposition_ids: list[str] = Field(default_factory=list)
    assessment_ids: list[str] = Field(default_factory=list)
    review_decision_ids: list[str] = Field(default_factory=list)
    run_artifact_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class NarrativeExport(BaseModel):
    title: str
    summary: str
    sections: list[str] = Field(default_factory=list)


ScopeType = Literal[
    "species",
    "subject",
    "process",
    "institution",
    "document",
    "disease",
    "geography",
    "other",
]

LegalScopeStatus = Literal["draft", "active", "deprecated"]

ScopeRelevance = Literal["direct", "indirect", "contextual"]

ScopeInheritance = Literal["explicit", "inherited", "inferred", "none"]

ScopeLinkConfidence = Literal["high", "medium", "low"]

ScopeLinkMethod = Literal["deterministic", "llm", "manual", "fallback"]


class LegalScope(BaseModel):
    id: str
    slug: str
    label: str
    description: str = ""
    parent_scope_id: str | None = None
    scope_type: ScopeType
    synonyms: list[str] = Field(default_factory=list)
    status: LegalScopeStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PropositionScopeLink(BaseModel):
    id: str
    proposition_id: str
    proposition_key: str | None = None
    scope_id: str
    relevance: ScopeRelevance
    inheritance: ScopeInheritance
    confidence: ScopeLinkConfidence
    method: ScopeLinkMethod
    reason: str
    evidence: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class LegalScopeReviewCandidate(BaseModel):
    """Unknown or non-canonical scope suggestion recorded for governance review."""

    id: str
    run_id: str
    suggested_slug: str
    raw_label: str = ""
    source: Literal[
        "external_suggestion",
        "deterministic_unknown_token",
        "llm_suggestion",
        "import",
        "other",
    ] = "other"
    reason: str
    evidence: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


# Deprecated compatibility alias for migration boundary: canonical term is SourceRecord.
SourceDocument = SourceRecord
