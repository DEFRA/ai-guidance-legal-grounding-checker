from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

EvidenceType = Literal[
    "title",
    "text_snippet",
    "metadata",
    "relationship",
    "external_reference",
]

SourceType = Literal[
    "act",
    "ukpga",
    "uksi",
    "assimilated_eu_law",
    "retained_eu_law",
    "case_law",
    "guidance",
    "explanatory_note",
    "explanatory_memorandum",
    "form",
    "register",
    "unknown",
]

SourceSystem = Literal[
    "legislation_gov_uk",
    "lex",
    "gov_uk",
    "find_case_law",
    "eur_lex",
    "manual",
    "unknown",
]

TemporalStatus = Literal[
    "current",
    "current_or_part_current",
    "revoked",
    "historical",
    "prospective",
    "unknown",
]

RelationshipToCategory = Literal[
    "directly_regulates",
    "defines_terms",
    "amends",
    "commences",
    "revokes",
    "explains",
    "evidences",
    "operationalises",
    "cites",
    "possibly_relevant",
    "unknown",
]

Confidence = Literal["high", "medium", "low", "unknown"]

TriageRelevance = Literal["high", "medium", "low", "not_relevant", "uncertain"]

ReviewPriority = Literal[
    "likely_accept",
    "needs_human_review",
    "park_contextual",
    "likely_reject",
]

RecommendedAction = Literal[
    "accept_candidate",
    "park",
    "reject_candidate",
    "needs_more_research",
]

ReviewStatus = Literal[
    "unreviewed",
    "accepted",
    "rejected",
    "parked",
    "needs_more_research",
]

QueryType = Literal["label", "synonym", "description", "combined", "manual"]

RelatedSourceRelationshipType = Literal[
    "principal",
    "amends",
    "amended_by",
    "revokes",
    "revoked_by",
    "commences",
    "commenced_by",
    "corrects",
    "corrected_by",
    "explains",
    "explained_by",
    "implements",
    "implemented_by",
    "transposes",
    "transposed_by",
    "cites",
    "cited_by",
    "replaces",
    "replaced_by",
    "guidance_for",
    "form_for",
    "unknown",
]

RelationshipBasis = Literal[
    "lex_relationship",
    "legislation_metadata",
    "title_match",
    "uri_match",
    "ai_triage",
    "manual_review",
    "query_match",
    "unknown",
]


class CategoryBrief(BaseModel):
    category_id: str
    label: str
    description: str
    synonyms: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    jurisdiction_hints: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceSnippet(BaseModel):
    evidence_type: EvidenceType
    text: str
    uri: str | None = None
    locator: str | None = None
    source_field: str | None = None


class CandidateTriageMetadata(BaseModel):
    relevance: TriageRelevance
    review_priority: ReviewPriority
    relationship_to_category: RelationshipToCategory
    confidence_after_ai: Confidence
    recommended_action: RecommendedAction
    rationale: str
    supporting_signals: list[str] = Field(default_factory=list)
    false_positive_risks: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)
    assessment_confidence: Confidence | None = None


class CandidateSource(BaseModel):
    source_id: str
    title: str
    citation: str | None = None
    source_type: SourceType = "unknown"
    canonical_uri: str | None = None
    source_system: SourceSystem = "unknown"
    jurisdiction_extent: list[str] = Field(default_factory=list)
    temporal_status: TemporalStatus = "unknown"
    relationship_to_category: RelationshipToCategory = "unknown"
    match_basis: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSnippet] = Field(default_factory=list)
    confidence: Confidence = "unknown"
    review_status: ReviewStatus = "unreviewed"
    notes: str | None = None
    ai_triage: CandidateTriageMetadata | None = None


class DiscoveryQuery(BaseModel):
    query: str
    query_type: QueryType
    source_system: str = "lex"
    rationale: str | None = None


class DiscoveryRun(BaseModel):
    run_id: str
    created_at: datetime
    category: CategoryBrief
    query_plan: list[DiscoveryQuery]
    candidate_sources: list[CandidateSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceRegister(BaseModel):
    register_id: str
    category_id: str
    created_at: datetime
    accepted_sources: list[CandidateSource] = Field(default_factory=list)
    rejected_sources: list[CandidateSource] = Field(default_factory=list)
    parked_sources: list[CandidateSource] = Field(default_factory=list)
    export_target: str = "law-proposition-extractor"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceRelationship(BaseModel):
    relationship_id: str
    from_source_id: str
    to_source_id: str
    relationship_type: RelatedSourceRelationshipType
    confidence: Confidence = "unknown"
    basis: list[RelationshipBasis] = Field(default_factory=list)
    evidence: list[EvidenceSnippet] = Field(default_factory=list)
    review_status: ReviewStatus = "unreviewed"
    notes: str | None = None


class RelatedSourceExpansionRun(BaseModel):
    run_id: str
    created_at: datetime
    category_id: str
    seed_sources: list[CandidateSource] = Field(default_factory=list)
    related_sources: list[CandidateSource] = Field(default_factory=list)
    relationships: list[SourceRelationship] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceBundle(BaseModel):
    bundle_id: str
    category_id: str
    created_at: datetime
    principal_sources: list[CandidateSource] = Field(default_factory=list)
    amending_sources: list[CandidateSource] = Field(default_factory=list)
    commencement_sources: list[CandidateSource] = Field(default_factory=list)
    correction_sources: list[CandidateSource] = Field(default_factory=list)
    revocation_sources: list[CandidateSource] = Field(default_factory=list)
    interpretive_sources: list[CandidateSource] = Field(default_factory=list)
    guidance_sources: list[CandidateSource] = Field(default_factory=list)
    form_sources: list[CandidateSource] = Field(default_factory=list)
    contextual_sources: list[CandidateSource] = Field(default_factory=list)
    rejected_sources: list[CandidateSource] = Field(default_factory=list)
    relationships: list[SourceRelationship] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_category_brief(path: Path) -> CategoryBrief:
    return CategoryBrief.model_validate_json(path.read_text(encoding="utf-8"))


def save_discovery_run(run: DiscoveryRun, path: Path, *, input_path: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    from law_discovery.run_model_md import persist_model_md_for_discovery

    persist_model_md_for_discovery(run, path, input_path=input_path)


def load_discovery_run(path: Path) -> DiscoveryRun:
    return DiscoveryRun.model_validate_json(path.read_text(encoding="utf-8"))


def save_source_register(
    register: SourceRegister,
    path: Path,
    *,
    input_path: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(register.model_dump_json(indent=2), encoding="utf-8")
    from law_discovery.run_model_md import persist_model_md_for_source_register

    persist_model_md_for_source_register(register, path, input_path=input_path)


def load_source_register(path: Path) -> SourceRegister:
    return SourceRegister.model_validate_json(path.read_text(encoding="utf-8"))


def save_related_source_expansion_run(
    run: RelatedSourceExpansionRun,
    path: Path,
    *,
    input_path: Path | None = None,
    category_label: str | None = None,
    category_description: str | None = None,
    jurisdiction_hints: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    from law_discovery.run_model_md import persist_model_md_for_related_expansion

    persist_model_md_for_related_expansion(
        run,
        path,
        input_path=input_path,
        category_label=category_label,
        category_description=category_description,
        jurisdiction_hints=jurisdiction_hints,
    )


def load_related_source_expansion_run(path: Path) -> RelatedSourceExpansionRun:
    return RelatedSourceExpansionRun.model_validate_json(path.read_text(encoding="utf-8"))


def save_source_bundle(
    bundle: SourceBundle,
    path: Path,
    *,
    input_path: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    from law_discovery.run_model_md import persist_model_md_for_source_bundle

    persist_model_md_for_source_bundle(bundle, path, input_path=input_path)


def load_source_bundle(path: Path) -> SourceBundle:
    return SourceBundle.model_validate_json(path.read_text(encoding="utf-8"))
