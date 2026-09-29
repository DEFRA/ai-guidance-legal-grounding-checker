from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from .enums import (
    AffectingInstrumentConsumptionStatus,
    ConfidenceLevel,
    ConsumptionMatchBasis,
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    DivergenceType,
    HeuristicMethod,
    LegalEffectType,
    OutstandingEffectsStatus,
    PropositionTier,
    ReviewStatus,
    SourceEffectCategory,
    SourceEffectRepresentationStatus,
    SourceEffectStatus,
    SourceManifestationBasis,
    SourceManifestationType,
    StructuralHeadingKind,
)
from .proposition_classification import enrich_proposition_classification
from .proposition_jurisdiction import enrich_proposition_jurisdiction
from .proposition_notes import apply_notes_separation


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
    # Authority-supplied manifestation semantics (legislation.gov.uk / CLML).
    # Distinct from intake version_id and from Law Proposition Extractor amendment application.
    manifestation_type: SourceManifestationType | None = None
    manifestation_basis: SourceManifestationBasis | None = None
    requested_as_of_date: date | None = None
    resolved_as_of_date: date | None = None
    source_revision_date: date | None = None
    requested_manifestation: SourceManifestationType | None = None
    resolved_manifestation: SourceManifestationType | None = None
    manifestation_evidence: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuralHeading(BaseModel):
    """Source-provided legislative heading for a structural fragment.

    Authoritative stored copy lives only on the owning fragment. Descendants
    resolve headings through structural parent links — do not duplicate text
    onto every child. Distinct from operative ``fragment_text``, locator labels,
    and LLM-generated proposition labels.
    """

    kind: StructuralHeadingKind = StructuralHeadingKind.UNKNOWN
    text: str
    number_label: str | None = None
    owner_fragment_id: str | None = None
    owner_locator: str | None = None
    source_element: str | None = None
    change_ids: tuple[str, ...] = ()
    commentary_refs: tuple[str, ...] = ()

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_unknown_kind(cls, value: Any) -> Any:
        if value is None or value == "":
            return StructuralHeadingKind.UNKNOWN
        if isinstance(value, StructuralHeadingKind):
            return value
        text = str(value).strip().lower()
        try:
            return StructuralHeadingKind(text)
        except ValueError:
            return StructuralHeadingKind.UNKNOWN

    @field_validator("text", mode="before")
    @classmethod
    def _normalize_heading_text(cls, value: Any) -> str:
        text = " ".join(str(value or "").replace("\xa0", " ").split()).strip()
        if not text:
            raise ValueError("structural heading text must be non-empty")
        return text

    @field_validator("number_label", mode="before")
    @classmethod
    def _normalize_number_label(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).replace("\xa0", " ").split()).strip()
        return text or None

    @field_validator("change_ids", "commentary_refs", mode="before")
    @classmethod
    def _normalize_id_tuples(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            items = [value]
        else:
            items = list(value)
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            token = str(item or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            out.append(token)
        return tuple(out)


class StructuralHeadingContext(BaseModel):
    """Resolved heading context for extraction jobs and UI (inherited path entry)."""

    kind: StructuralHeadingKind = StructuralHeadingKind.UNKNOWN
    number_label: str | None = None
    heading_text: str
    owner_locator: str | None = None
    owner_fragment_id: str | None = None
    change_ids: tuple[str, ...] = ()
    commentary_refs: tuple[str, ...] = ()

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_unknown_kind(cls, value: Any) -> Any:
        return StructuralHeading._coerce_unknown_kind(value)

    @field_validator("heading_text", mode="before")
    @classmethod
    def _normalize_heading_text(cls, value: Any) -> str:
        return StructuralHeading._normalize_heading_text(value)

    @field_validator("number_label", mode="before")
    @classmethod
    def _normalize_number_label(cls, value: Any) -> str | None:
        return StructuralHeading._normalize_number_label(value)

    @field_validator("change_ids", "commentary_refs", mode="before")
    @classmethod
    def _normalize_id_tuples(cls, value: Any) -> tuple[str, ...]:
        return StructuralHeading._normalize_id_tuples(value)


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
    # Optional back-refs to source-reported legal effects (not Law Proposition Extractor-applied amendments).
    source_legal_effect_ids: list[str] = Field(default_factory=list)
    # Source-provided structural labels (not operative proposition text).
    number_label: str | None = None
    structural_heading: StructuralHeading | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("number_label", mode="before")
    @classmethod
    def _normalize_fragment_number_label(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).replace("\xa0", " ").split()).strip()
        return text or None

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
    extraction_mode: str | None = None
    model_alias: str | None = None
    fallback_policy: str | None = None
    fallback_used: bool | None = None
    validation_errors: list[str] = Field(default_factory=list)
    schema_version: str | None = None
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
    source_jurisdiction: str = ""
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
    categories: list[str] = Field(
        default_factory=list,
        description=(
            "Non-authoritative legacy LLM/tag output from extraction. "
            "Do not use to decide obligation type, compliance relevance, or comparison anchors — "
            "use legal_effect_type, is_compliance_relevant, and is_comparison_anchor."
        ),
    )
    tags: list[str] = Field(default_factory=list)
    cross_reference_key: str | None = None  # Deprecated: use source_scoped_key (same value when set).
    source_scoped_key: str | None = None
    semantic_comparison_key: str | None = None
    explicit_cross_reference_targets: list[str] = Field(default_factory=list)
    cross_reference_targets: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    notes: str = ""
    proposition_tier: PropositionTier = PropositionTier.UNKNOWN
    legal_effect_type: LegalEffectType = LegalEffectType.UNKNOWN
    territorial_application: list[str] = Field(default_factory=list)
    extent: list[str] = Field(default_factory=list)
    is_compliance_relevant: bool | None = None
    is_comparison_anchor: bool | None = None
    review_notes: str | None = None
    extraction_trace_id: str | None = None
    extraction_debug_meta: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _separate_extraction_notes(self) -> "Proposition":
        return apply_notes_separation(self)

    @model_validator(mode="after")
    def _apply_classification_defaults(self) -> "Proposition":
        return enrich_proposition_classification(self)

    @model_validator(mode="after")
    def _apply_jurisdiction_fields(self) -> "Proposition":
        return enrich_proposition_jurisdiction(self)


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


JurisdictionScope = Literal["EU", "UK", "mixed", "unknown"]

RegistryAnalysisScope = Literal["eu", "uk", "eu_uk", "selected_sources"]


class PropositionDatasetMetadata(BaseModel):
    """Saved output of an analysis (extraction) run: one proposition dataset per analysis run."""

    dataset_id: str
    run_id: str
    jurisdiction_scope: JurisdictionScope
    source_ids: list[str] = Field(default_factory=list)
    corpus_id: str | None = None
    extraction_settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    quality_status: str = "unknown"


class PropositionDatasetComparisonRun(BaseModel):
    """Comparison of two existing proposition datasets — never re-extracts source text."""

    comparison_run_id: str
    left_dataset_id: str
    right_dataset_id: str
    left_source_run_id: str
    right_source_run_id: str
    pairing_settings: dict[str, Any] = Field(default_factory=dict)
    divergence_reasoning_settings: dict[str, Any] = Field(default_factory=dict)
    output_finding_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


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


class SourceLegalEffect(BaseModel):
    """Authority-reported amendment/effect annotation from consumed CLML.

    Records what legislation.gov.uk supplied in the consumed source. Does not
    assert that Law Proposition Extractor applied the effect or independently consumed the affecting
    instrument.
    """

    id: str
    source_record_id: str
    source_snapshot_id: str
    annotation_id: str | None = None
    annotation_label: str | None = None
    effect_category: SourceEffectCategory = SourceEffectCategory.UNKNOWN
    raw_effect_category: str | None = None
    effect_description: str | None = None
    affected_locator: str | None = None
    affected_source_fragment_id: str | None = None
    affecting_instrument_uri: str | None = None
    affecting_instrument_citation: str | None = None
    affecting_instrument_title: str | None = None
    affecting_instrument_provision: str | None = None
    effect_date: date | None = None
    effect_status: SourceEffectStatus = SourceEffectStatus.SOURCE_STATUS_UNKNOWN
    source_representation_status: SourceEffectRepresentationStatus = (
        SourceEffectRepresentationStatus.UNKNOWN
    )
    independent_consumption_status: AffectingInstrumentConsumptionStatus = (
        AffectingInstrumentConsumptionStatus.NOT_ASSESSED
    )
    matched_source_record_id: str | None = None
    matched_source_snapshot_ids: list[str] = Field(default_factory=list)
    consumption_match_basis: ConsumptionMatchBasis | None = None
    matched_instrument_identity: str | None = None
    consumption_match_evidence: list[dict[str, Any]] = Field(default_factory=list)
    source_evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceLegalEffectLink(BaseModel):
    """Link from a source-reported effect to an affected structural fragment."""

    id: str
    effect_id: str
    source_record_id: str
    source_snapshot_id: str
    source_fragment_id: str | None = None
    affected_locator: str | None = None
    linkage_status: Literal[
        "linked",
        "locator_only",
        "unresolved",
    ] = "unresolved"
    source_evidence: dict[str, Any] = Field(default_factory=dict)


class SourceLegalEffectsArtifact(BaseModel):
    """Run-scoped inventory of source-reported legal effects/annotations."""

    schema_version: Literal["1"] = "1"
    run_id: str
    effects: list[SourceLegalEffect] = Field(default_factory=list)
    effect_links: list[SourceLegalEffectLink] = Field(default_factory=list)
    outstanding_effects_status: OutstandingEffectsStatus = (
        OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN
    )
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


LegalRuleGroupBasis = Literal["shared_source_fragment"]


class LegalRuleGroup(BaseModel):
    """Persisted set of retained propositions sharing one structural source fragment.

    Represents legal/source structure (e.g. a multi-proposition paragraph), not
    UI explorer groups, composition groups, or soft-duplicate clusters.
    """

    id: str
    source_record_id: str
    source_snapshot_id: str
    source_fragment_id: str
    canonical_locator: str
    member_proposition_ids: list[str]
    group_basis: LegalRuleGroupBasis = "shared_source_fragment"
    member_count: int | None = None
    fragment_kind: str | None = None
    parent_fragment_id: str | None = None

    @model_validator(mode="after")
    def _sync_member_count(self) -> "LegalRuleGroup":
        if self.member_count is None:
            self.member_count = len(self.member_proposition_ids)
        return self


LegalRuleRelationshipType = Literal["exception_to", "triggered_by"]
LegalRuleRelationshipSourceKind = Literal["proposition"]
LegalRuleRelationshipTargetKind = Literal["proposition", "legal_rule_group"]
LegalRuleRelationshipInferenceBasis = Literal["explicit_exception_cue", "explicit_trigger_cue"]
LegalRuleRelationshipResolutionBasis = Literal[
    "explicit",
    "structural_relative",
    "instrument_wide",
]


class LegalRuleRelationship(BaseModel):
    """Typed legal-semantic relationship between a proposition and a rule endpoint.

    Distinct from mechanical locator-wiring edges in proposition-relationships.json
    (``text_references_locator`` / ``locator_resolves_to``).
    """

    id: str
    relationship_type: LegalRuleRelationshipType
    source_kind: LegalRuleRelationshipSourceKind = "proposition"
    source_id: str
    target_kind: LegalRuleRelationshipTargetKind
    target_id: str
    source_record_id: str
    source_snapshot_id: str
    source_fragment_id: str | None = None
    target_source_fragment_id: str | None = None
    referenced_locator: str | None = None
    reference_text: str | None = None
    resolution_basis: LegalRuleRelationshipResolutionBasis | None = None
    inference_basis: LegalRuleRelationshipInferenceBasis
    evidence_text: str | None = None
    cue_text: str | None = None
    confidence: str | None = None
    target_canonical_locator: str | None = None


class DecisionInput(BaseModel):
    """Typed input referenced by a DecisionExplanation."""

    kind: str
    label: str | None = None
    value: str | None = None
    id: str | None = None


class DecisionEvidence(BaseModel):
    """Typed evidence fact supporting a DecisionExplanation."""

    kind: str
    label: str | None = None
    value: str | None = None
    id: str | None = None


class DecisionAlternative(BaseModel):
    """Alternative subject considered alongside the decision subject."""

    kind: str
    id: str | None = None
    label: str | None = None
    value: str | None = None
    role: str | None = None


class SuppressedDecisionItem(BaseModel):
    """Item suppressed as a consequence of the decision (when not the subject)."""

    kind: str
    id: str
    reason: str | None = None
    label: str | None = None


class DecisionTraceReference(BaseModel):
    """Pointer to an existing run/job/trace record."""

    kind: str
    id: str | None = None
    label: str | None = None


class DecisionExplanation(BaseModel):
    """Stable, audience-neutral record of a material pipeline decision.

    Execution evidence emitted at the decision site — not LLM chain-of-thought.
    Optional fields stay absent rather than filled with placeholders.
    """

    id: str
    stage: DecisionStage
    decision_type: DecisionType
    subject_kind: DecisionSubjectKind
    subject_id: str
    outcome: str
    method: HeuristicMethod
    rule_id: str
    rule_version: str
    summary: str
    inputs: list[DecisionInput] = Field(default_factory=list)
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    alternatives: list[DecisionAlternative] = Field(default_factory=list)
    suppressed_items: list[SuppressedDecisionItem] = Field(default_factory=list)
    confidence: str | None = None
    diagnostics: list[str] = Field(default_factory=list)
    code_references: list[str] = Field(default_factory=list)
    trace_references: list[DecisionTraceReference] = Field(default_factory=list)
    model_alias: str | None = None
    prompt_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionExplanationsArtifact(BaseModel):
    """Run-scoped inventory of DecisionExplanation records."""

    schema_version: Literal["1"] = "1"
    run_id: str
    decisions: list[DecisionExplanation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# Deprecated compatibility alias for migration boundary: canonical term is SourceRecord.
SourceDocument = SourceRecord
