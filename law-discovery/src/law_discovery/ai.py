from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from law_discovery.models import (
    CandidateSource,
    CategoryBrief,
    RelatedSourceRelationshipType,
    SourceRelationship,
)
from law_discovery.progress import DiscoveryProgressEvent, ProgressCallback, emit_progress

AIProvider = Literal["litellm"]

SearchTermType = Literal[
    "synonym",
    "related_concept",
    "actor",
    "object",
    "process",
    "document",
    "exclusion",
]

TermConfidence = Literal["high", "medium", "low"]

CandidateRelevance = Literal["high", "medium", "low", "not_relevant", "uncertain"]

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

RecommendedReviewStatus = Literal[
    "unreviewed",
    "accepted",
    "rejected",
    "parked",
    "needs_more_research",
]

ReviewPriority = Literal[
    "likely_accept",
    "needs_human_review",
    "park_contextual",
    "likely_reject",
]

ConfidenceAfterAI = Literal["high", "medium", "low", "unknown"]

AssessmentConfidence = Literal["high", "medium", "low", "unknown"]

RecommendedAction = Literal[
    "accept_candidate",
    "park",
    "reject_candidate",
    "needs_more_research",
]


class AdaAIConfigurationError(Exception):
    """Raised when Law Discovery AI settings are missing or invalid."""


class AdaAISettings(BaseModel):
    provider: AIProvider = "litellm"
    model: str
    litellm_base_url: str
    litellm_api_key: str | None = None


class AICheckResponse(BaseModel):
    ok: bool
    message: str


class SearchTermSuggestion(BaseModel):
    term: str
    reason: str
    term_type: SearchTermType
    confidence: TermConfidence


class CategoryExpansion(BaseModel):
    category_id: str
    suggested_terms: list[SearchTermSuggestion]
    suggested_exclusions: list[SearchTermSuggestion]
    notes: list[str] = Field(default_factory=list)


class CandidateRelevanceAssessment(BaseModel):
    source_id: str
    relevance: CandidateRelevance
    relationship_to_category: RelationshipToCategory
    rationale: str
    useful_evidence: list[str] = Field(default_factory=list)
    false_positive_risks: list[str] = Field(default_factory=list)
    recommended_review_status: RecommendedReviewStatus = "unreviewed"


class CandidateTriageAssessment(BaseModel):
    source_id: str
    relevance: CandidateRelevance
    review_priority: ReviewPriority
    relationship_to_category: RelationshipToCategory
    confidence_after_ai: ConfidenceAfterAI
    rationale: str
    supporting_signals: list[str] = Field(default_factory=list)
    false_positive_risks: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction
    evidence_limitations: list[str] = Field(default_factory=list)
    assessment_confidence: AssessmentConfidence | None = None


class CandidateTriageBatch(BaseModel):
    assessments: list[CandidateTriageAssessment]
    batch_notes: list[str] = Field(default_factory=list)


class RelatedSourceAssessment(BaseModel):
    from_source_id: str
    to_source_id: str
    relationship_type: RelatedSourceRelationshipType
    relevance: Literal["high", "medium", "low", "not_relevant", "uncertain"]
    confidence: Literal["high", "medium", "low", "unknown"]
    recommended_review_status: Literal[
        "accepted",
        "parked",
        "rejected",
        "needs_more_research",
        "unreviewed",
    ]
    rationale: str
    supporting_signals: list[str] = Field(default_factory=list)
    false_positive_risks: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)


class RelatedSourceAssessmentBatch(BaseModel):
    assessments: list[RelatedSourceAssessment]
    batch_notes: list[str] = Field(default_factory=list)


_FALLBACK_TRIAGE_RATIONALE = "AI triage unavailable; manual review required."
_FALLBACK_RELATED_RATIONALE = "AI relationship triage unavailable; manual review required."
_MAX_TRIAGE_FAILURE_REASONS = 10


@dataclass
class AITriageStats:
    ai_triage_requested: bool = True
    ai_triage_batch_count: int = 0
    ai_triage_successful_batch_count: int = 0
    ai_triage_failed_batch_count: int = 0
    ai_triage_successful_candidate_count: int = 0
    ai_triage_fallback_candidate_count: int = 0
    ai_triage_failure_reasons: list[str] = field(default_factory=list)

    @property
    def ai_triage_failed(self) -> bool:
        return (
            self.ai_triage_batch_count > 0
            and self.ai_triage_failed_batch_count == self.ai_triage_batch_count
        )

    @property
    def ai_triage_partial(self) -> bool:
        return (
            self.ai_triage_failed_batch_count > 0
            and self.ai_triage_failed_batch_count < self.ai_triage_batch_count
        )

    def record_failure_reason(self, reason: str) -> None:
        if reason not in self.ai_triage_failure_reasons:
            self.ai_triage_failure_reasons.append(reason)
        if len(self.ai_triage_failure_reasons) > _MAX_TRIAGE_FAILURE_REASONS:
            self.ai_triage_failure_reasons = self.ai_triage_failure_reasons[
                :_MAX_TRIAGE_FAILURE_REASONS
            ]

    def merge(self, other: AITriageStats) -> None:
        self.ai_triage_batch_count += other.ai_triage_batch_count
        self.ai_triage_successful_batch_count += other.ai_triage_successful_batch_count
        self.ai_triage_failed_batch_count += other.ai_triage_failed_batch_count
        self.ai_triage_successful_candidate_count += other.ai_triage_successful_candidate_count
        self.ai_triage_fallback_candidate_count += other.ai_triage_fallback_candidate_count
        for reason in other.ai_triage_failure_reasons:
            self.record_failure_reason(reason)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "ai_triage_requested": self.ai_triage_requested,
            "ai_triage_batch_count": self.ai_triage_batch_count,
            "ai_triage_successful_batch_count": self.ai_triage_successful_batch_count,
            "ai_triage_failed_batch_count": self.ai_triage_failed_batch_count,
            "ai_triage_successful_candidate_count": self.ai_triage_successful_candidate_count,
            "ai_triage_fallback_candidate_count": self.ai_triage_fallback_candidate_count,
            "ai_triage_failed": self.ai_triage_failed,
            "ai_triage_partial": self.ai_triage_partial,
            "ai_triage_failure_reasons": self.ai_triage_failure_reasons,
        }


_CATEGORY_EXPANSION_SYSTEM_PROMPT = """\
You help expand UK legal source discovery categories for Law Discovery.

Rules:
- Suggest extra search terms and exclusions only.
- Do not draw legal conclusions or provide legal advice.
- Do not claim completeness.
- Prefer UK legal terminology and instruments discoverable via legislation.gov.uk-style sources.
- Preserve the original category boundary.
- State uncertainty in notes when appropriate.
- Return structured output only.
"""

_CANDIDATE_RELEVANCE_SYSTEM_PROMPT = """\
You assess candidate UK legal source relevance for Law Discovery discovery review.

Rules:
- Assess relevance only from the provided title, metadata, and evidence.
- Never assert that a source definitely applies unless evidence is strong.
- Never provide legal advice.
- Prefer "uncertain" when evidence is thin.
- Never recommend automatic acceptance; default to unreviewed or needs_more_research.
- Return structured output only.
"""

_AI_CHECK_SYSTEM_PROMPT = """\
Smoke-test response for Law Discovery LiteLLM connectivity check.
Return structured output only with ok=true and message="hello".
"""

_RELATED_SOURCE_ASSESSMENT_SYSTEM_PROMPT = """\
You assess whether candidate UK legal sources are genuinely related to seed sources for Law Discovery.

Rules:
- Use category.metadata.triage_guidance when provided.
  It is user-supplied domain guidance, not a legal conclusion.
- Assess using only provided titles, citations, URIs, evidence,
  and deterministic relationship guesses.
- Do not decide final legal effect.
- Do not say an amendment is legally in force or consolidated.
- You may say "appears to amend", "appears to revoke", "appears to explain", etc.
- Prefer needs_more_research when evidence is title-only or ambiguous.
- Reject obvious unrelated title matches (shared generic words only).
- Return one assessment per (from_source_id, to_source_id) pair in the batch.
- Return structured output only.
"""

_CANDIDATE_TRIAGE_SYSTEM_PROMPT = """\
You triage candidate UK legal sources for Law Discovery discovery human review.

Rules:
- Use category.metadata.triage_guidance when provided. It is user-supplied domain guidance for
  triage priority, not a legal conclusion.
- Assess relevance using only the provided category brief and candidate metadata/evidence.
- Do not make legal conclusions or provide legal advice.
- Do not claim discovery is complete.
- Prefer "uncertain" or "needs_human_review" when evidence is thin.
- Identify obvious false positives (e.g. unrelated transport, local/private acts, merchant shipping,
  construction, vehicle safety, non-UK EU derogations when the category is UK-focused).
- Distinguish:
  a) core legal instruments that directly regulate the category,
  b) amendment/revocation/commencement instruments,
  c) contextual interpretive material,
  d) adjacent-but-not-core material,
  e) false positives.
- Be conservative about "likely_accept" and never use review_priority "likely_accept" unless
  title and evidence strongly align with the category.
- recommended_action "accept_candidate" only when title/evidence strongly align; otherwise prefer
  park, reject_candidate, or needs_more_research.
- confidence_after_ai is AI-adjusted RELEVANCE confidence (how likely the source belongs in the
  category), NOT confidence in your triage decision.
- assessment_confidence (optional) is how confident you are in review_priority and
  recommended_action.
- confidence_after_ai mapping:
  - relevance "high" with likely_accept: usually "high"
  - relevance "medium": usually "medium"
  - relevance "low": usually "low" or "medium"
  - relevance "not_relevant": MUST be "low"
  - relevance "uncertain": MUST be "unknown" or "medium"
- Never set confidence_after_ai to "high" for reject_candidate or likely_reject outcomes.
- For a confident false positive (clearly unrelated to the category):
  relevance="not_relevant", review_priority="likely_reject", recommended_action="reject_candidate",
  confidence_after_ai="low", assessment_confidence="high".
- Return one assessment per candidate source_id in the batch.
- Return structured output only.
"""


def load_ai_settings(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> AdaAISettings:
    provider = os.environ.get("LAW_DISCOVERY_AI_PROVIDER", "litellm").strip() or "litellm"
    if provider != "litellm":
        msg = f"Unsupported AI provider: {provider!r}. Only 'litellm' is supported."
        raise AdaAIConfigurationError(msg)

    model = (model_name or os.environ.get("LAW_DISCOVERY_AI_MODEL", "")).strip()
    if not model:
        msg = "LAW_DISCOVERY_AI_MODEL is required but not set."
        raise AdaAIConfigurationError(msg)

    resolved_base_url = (base_url or os.environ.get("LAW_DISCOVERY_LITELLM_BASE_URL", "")).strip()
    if not resolved_base_url:
        msg = "LAW_DISCOVERY_LITELLM_BASE_URL is required but not set."
        raise AdaAIConfigurationError(msg)

    resolved_api_key = api_key if api_key is not None else os.environ.get("LAW_DISCOVERY_LITELLM_API_KEY")

    return AdaAISettings(
        provider="litellm",
        model=model,
        litellm_base_url=resolved_base_url.rstrip("/"),
        litellm_api_key=resolved_api_key,
    )


def is_ai_configured() -> bool:
    """Return True when required AI settings are available."""
    try:
        load_ai_settings()
    except AdaAIConfigurationError:
        return False
    return True


def build_litellm_model(settings: AdaAISettings) -> OpenAIChatModel:
    """Build a Pydantic AI model routed through the LiteLLM OpenAI-compatible proxy."""
    api_key = settings.litellm_api_key or "not-required-for-local-dev"
    provider = OpenAIProvider(base_url=settings.litellm_base_url, api_key=api_key)
    return OpenAIChatModel(settings.model, provider=provider)


def build_ai_check_agent(settings: AdaAISettings) -> Agent[None, AICheckResponse]:
    model = build_litellm_model(settings)
    return Agent(
        model,
        output_type=AICheckResponse,
        system_prompt=_AI_CHECK_SYSTEM_PROMPT,
    )


def run_ai_connection_check(settings: AdaAISettings) -> AICheckResponse:
    """Run a tiny structured Pydantic AI call through LiteLLM using resolved settings."""
    agent = build_ai_check_agent(settings)
    result = agent.run_sync("Respond with ok=true and message='hello'.")
    return result.output


def check_ai_connection(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> AICheckResponse:
    """Run a tiny structured Pydantic AI call through LiteLLM."""
    settings = load_ai_settings(model_name=model_name, base_url=base_url, api_key=api_key)
    return run_ai_connection_check(settings)


def build_category_expansion_agent(settings: AdaAISettings) -> Agent[None, CategoryExpansion]:
    model = build_litellm_model(settings)
    return Agent(
        model,
        output_type=CategoryExpansion,
        system_prompt=_CATEGORY_EXPANSION_SYSTEM_PROMPT,
    )


def build_candidate_relevance_agent(
    settings: AdaAISettings,
) -> Agent[None, CandidateRelevanceAssessment]:
    model = build_litellm_model(settings)
    return Agent(
        model,
        output_type=CandidateRelevanceAssessment,
        system_prompt=_CANDIDATE_RELEVANCE_SYSTEM_PROMPT,
    )


def build_candidate_triage_agent(settings: AdaAISettings) -> Agent[None, CandidateTriageBatch]:
    model = build_litellm_model(settings)
    return Agent(
        model,
        output_type=CandidateTriageBatch,
        system_prompt=_CANDIDATE_TRIAGE_SYSTEM_PROMPT,
    )


def build_related_source_assessment_agent(
    settings: AdaAISettings,
) -> Agent[None, RelatedSourceAssessmentBatch]:
    model = build_litellm_model(settings)
    return Agent(
        model,
        output_type=RelatedSourceAssessmentBatch,
        system_prompt=_RELATED_SOURCE_ASSESSMENT_SYSTEM_PROMPT,
    )


def _category_expansion_prompt(category: CategoryBrief) -> str:
    return (
        "Expand this UK legal source discovery category with additional "
        "search terms and exclusions.\n\n"
        f"category_id: {category.category_id}\n"
        f"label: {category.label}\n"
        f"description: {category.description}\n"
        f"synonyms: {', '.join(category.synonyms) or '(none)'}\n"
        f"exclusions: {', '.join(category.exclusions) or '(none)'}\n"
        f"jurisdiction_hints: {', '.join(category.jurisdiction_hints) or '(none)'}\n"
    )


def _candidate_relevance_prompt(category: CategoryBrief, candidate: CandidateSource) -> str:
    evidence_lines = [
        f"- [{snippet.evidence_type}] {snippet.text}"
        for snippet in candidate.evidence
    ] or ["- (no evidence snippets provided)"]
    return (
        "Assess this candidate source for the category below.\n\n"
        f"category_id: {category.category_id}\n"
        f"label: {category.label}\n"
        f"description: {category.description}\n"
        f"synonyms: {', '.join(category.synonyms) or '(none)'}\n"
        f"exclusions: {', '.join(category.exclusions) or '(none)'}\n\n"
        f"source_id: {candidate.source_id}\n"
        f"title: {candidate.title}\n"
        f"citation: {candidate.citation or '(none)'}\n"
        f"source_type: {candidate.source_type}\n"
        f"canonical_uri: {candidate.canonical_uri or '(none)'}\n"
        f"source_system: {candidate.source_system}\n"
        f"matched_terms: {', '.join(candidate.matched_terms) or '(none)'}\n"
        f"match_basis: {', '.join(candidate.match_basis) or '(none)'}\n"
        f"notes: {candidate.notes or '(none)'}\n\n"
        "Evidence:\n"
        f"{chr(10).join(evidence_lines)}"
    )


def expand_category_with_ai(
    category: CategoryBrief,
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> CategoryExpansion:
    settings = load_ai_settings(model_name=model_name, base_url=base_url, api_key=api_key)
    agent = build_category_expansion_agent(settings)
    result = agent.run_sync(_category_expansion_prompt(category))
    expansion = result.output
    if expansion.category_id != category.category_id:
        expansion = expansion.model_copy(update={"category_id": category.category_id})
    return expansion


def _compact_candidate_summary(candidate: CandidateSource) -> str:
    evidence_lines = [
        f"    - [{snippet.evidence_type}] {snippet.text}"
        for snippet in candidate.evidence
    ] or ["    - (no evidence snippets)"]
    return (
        f"  source_id: {candidate.source_id}\n"
        f"  title: {candidate.title}\n"
        f"  citation: {candidate.citation or '(none)'}\n"
        f"  source_type: {candidate.source_type}\n"
        f"  canonical_uri: {candidate.canonical_uri or '(none)'}\n"
        f"  matched_terms: {', '.join(candidate.matched_terms) or '(none)'}\n"
        f"  deterministic_confidence: {candidate.confidence}\n"
        f"  relationship_to_category: {candidate.relationship_to_category}\n"
        f"  evidence:\n"
        f"{chr(10).join(evidence_lines)}"
    )


def _category_triage_context(category: CategoryBrief) -> str:
    metadata_json = (
        json.dumps(category.metadata, indent=2, ensure_ascii=False)
        if category.metadata
        else "(none)"
    )
    return (
        f"category_id: {category.category_id}\n"
        f"label: {category.label}\n"
        f"description: {category.description}\n"
        f"synonyms: {', '.join(category.synonyms) or '(none)'}\n"
        f"exclusions: {', '.join(category.exclusions) or '(none)'}\n"
        f"jurisdiction_hints: {', '.join(category.jurisdiction_hints) or '(none)'}\n"
        f"metadata:\n{metadata_json}"
    )


def _candidate_triage_batch_prompt(
    category: CategoryBrief,
    candidates: list[CandidateSource],
) -> str:
    summaries = "\n\n".join(_compact_candidate_summary(candidate) for candidate in candidates)
    return (
        "Triage these candidate sources for the category below.\n\n"
        f"{_category_triage_context(category)}\n\n"
        f"Candidates ({len(candidates)}):\n\n"
        f"{summaries}"
    )


def is_fallback_triage_assessment(assessment: CandidateTriageAssessment) -> bool:
    return assessment.rationale == _FALLBACK_TRIAGE_RATIONALE


def _uncertain_triage_assessment(
    candidate: CandidateSource,
    *,
    limitation: str,
) -> CandidateTriageAssessment:
    return CandidateTriageAssessment(
        source_id=candidate.source_id,
        relevance="uncertain",
        review_priority="needs_human_review",
        relationship_to_category=candidate.relationship_to_category,
        confidence_after_ai="unknown",
        rationale=_FALLBACK_TRIAGE_RATIONALE,
        evidence_limitations=[limitation],
        recommended_action="needs_more_research",
    )


def _record_triage_assessments(
    stats: AITriageStats,
    assessments: list[CandidateTriageAssessment],
) -> None:
    for assessment in assessments:
        if is_fallback_triage_assessment(assessment):
            stats.ai_triage_fallback_candidate_count += 1
        else:
            stats.ai_triage_successful_candidate_count += 1


def _normalise_triage_batch(
    candidates: list[CandidateSource],
    batch: CandidateTriageBatch,
) -> list[CandidateTriageAssessment]:
    by_id = {assessment.source_id: assessment for assessment in batch.assessments}
    normalised: list[CandidateTriageAssessment] = []
    for candidate in candidates:
        assessment = by_id.get(candidate.source_id)
        if assessment is None:
            normalised.append(
                _uncertain_triage_assessment(
                    candidate,
                    limitation="AI batch omitted an assessment for this source_id.",
                )
            )
        elif assessment.source_id != candidate.source_id:
            normalised.append(
                assessment.model_copy(update={"source_id": candidate.source_id})
            )
        else:
            normalised.append(assessment)
    return normalised


def triage_candidates_with_ai(
    category: CategoryBrief,
    candidates: list[CandidateSource],
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    batch_size: int = 15,
) -> tuple[list[CandidateTriageAssessment], AITriageStats]:
    """Batch-triage candidates via Pydantic AI; uncertain fallbacks on batch failure."""
    stats = AITriageStats(ai_triage_requested=True)
    if not candidates:
        return [], stats

    settings = load_ai_settings(model_name=model_name, base_url=base_url, api_key=api_key)
    agent = build_candidate_triage_agent(settings)
    effective_batch_size = max(1, batch_size)
    all_assessments: list[CandidateTriageAssessment] = []

    for offset in range(0, len(candidates), effective_batch_size):
        batch_candidates = candidates[offset : offset + effective_batch_size]
        stats.ai_triage_batch_count += 1
        try:
            result = agent.run_sync(_candidate_triage_batch_prompt(category, batch_candidates))
            assessments = _normalise_triage_batch(batch_candidates, result.output)
            stats.ai_triage_successful_batch_count += 1
            _record_triage_assessments(stats, assessments)
            all_assessments.extend(assessments)
        except Exception as exc:  # noqa: BLE001 - degrade batch to uncertain assessments
            stats.ai_triage_failed_batch_count += 1
            limitation = f"AI triage batch failed: {exc}"
            stats.record_failure_reason(limitation)
            fallback_assessments = [
                _uncertain_triage_assessment(candidate, limitation=limitation)
                for candidate in batch_candidates
            ]
            stats.ai_triage_fallback_candidate_count += len(fallback_assessments)
            all_assessments.extend(fallback_assessments)

    return all_assessments, stats


def assess_candidate_with_ai(
    category: CategoryBrief,
    candidate: CandidateSource,
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> CandidateRelevanceAssessment:
    settings = load_ai_settings(model_name=model_name, base_url=base_url, api_key=api_key)
    agent = build_candidate_relevance_agent(settings)
    result = agent.run_sync(_candidate_relevance_prompt(category, candidate))
    assessment = result.output
    if assessment.source_id != candidate.source_id:
        assessment = assessment.model_copy(update={"source_id": candidate.source_id})
    return assessment


def expand_category_without_ai(category: CategoryBrief) -> CategoryExpansion:
    """Deterministic fallback when AI is not configured."""
    return CategoryExpansion(
        category_id=category.category_id,
        suggested_terms=[],
        suggested_exclusions=[],
        notes=["AI not configured; using category brief only."],
    )


def _compact_seed_summary(seed: CandidateSource) -> str:
    return (
        f"  source_id: {seed.source_id}\n"
        f"  title: {seed.title}\n"
        f"  citation: {seed.citation or '(none)'}\n"
        f"  canonical_uri: {seed.canonical_uri or '(none)'}"
    )


def _related_source_assessment_batch_prompt(
    category: CategoryBrief,
    seed_sources: list[CandidateSource],
    related_sources: list[CandidateSource],
    relationships: list[SourceRelationship],
) -> str:
    seed_by_id = {item.source_id: item for item in seed_sources}
    related_by_id = {item.source_id: item for item in related_sources}
    relationship_lines: list[str] = []
    pairs: list[tuple[CandidateSource, CandidateSource, SourceRelationship | None]] = []

    for relationship in relationships:
        seed = seed_by_id.get(relationship.from_source_id)
        related = related_by_id.get(relationship.to_source_id)
        if seed is None or related is None:
            continue
        pairs.append((seed, related, relationship))
        relationship_lines.append(
            f"- {relationship.from_source_id} -> {relationship.to_source_id}: "
            f"{relationship.relationship_type} "
            f"(confidence={relationship.confidence}, basis={relationship.basis})"
        )

    pair_blocks: list[str] = []
    for seed, related, guess in pairs:
        guess_line = (
            f"Deterministic guess: {guess.relationship_type} ({guess.confidence})"
            if guess is not None
            else "Deterministic guess: none"
        )
        pair_blocks.append(
            f"Pair:\n"
            f"Seed:\n{_compact_seed_summary(seed)}\n"
            f"Candidate:\n{_compact_candidate_summary(related)}\n"
            f"{guess_line}"
        )

    return (
        "Assess related-source relationships for the category below.\n\n"
        f"{_category_triage_context(category)}\n\n"
        f"Deterministic relationship guesses ({len(relationship_lines)}):\n"
        f"{chr(10).join(relationship_lines) or '(none)'}\n\n"
        f"Pairs to assess ({len(pair_blocks)}):\n\n"
        f"{chr(10).join(pair_blocks)}"
    )


def _uncertain_related_assessment(
    relationship: SourceRelationship,
    *,
    limitation: str,
) -> RelatedSourceAssessment:
    return RelatedSourceAssessment(
        from_source_id=relationship.from_source_id,
        to_source_id=relationship.to_source_id,
        relationship_type=relationship.relationship_type,
        relevance="uncertain",
        confidence="unknown",
        recommended_review_status="needs_more_research",
        rationale=_FALLBACK_RELATED_RATIONALE,
        evidence_limitations=[limitation],
    )


def _normalise_related_batch(
    relationships: list[SourceRelationship],
    batch: RelatedSourceAssessmentBatch,
) -> list[RelatedSourceAssessment]:
    by_pair = {
        (item.from_source_id, item.to_source_id): item for item in batch.assessments
    }
    normalised: list[RelatedSourceAssessment] = []
    for relationship in relationships:
        assessment = by_pair.get((relationship.from_source_id, relationship.to_source_id))
        if assessment is None:
            normalised.append(
                _uncertain_related_assessment(
                    relationship,
                    limitation="AI batch omitted an assessment for this relationship pair.",
                )
            )
        else:
            normalised.append(assessment)
    return normalised


def assess_related_sources_with_ai(
    category: CategoryBrief,
    seed_sources: list[CandidateSource],
    related_sources: list[CandidateSource],
    relationships: list[SourceRelationship],
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    batch_size: int = 15,
    progress_callback: ProgressCallback | None = None,
) -> list[RelatedSourceAssessment]:
    """Batch-assess related-source relationships via Pydantic AI; uncertain fallbacks on failure."""
    if not relationships:
        return []

    settings = load_ai_settings(model_name=model_name, base_url=base_url, api_key=api_key)
    agent = build_related_source_assessment_agent(settings)
    effective_batch_size = max(1, batch_size)
    all_assessments: list[RelatedSourceAssessment] = []
    relationship_count = len(relationships)
    batch_count = (relationship_count + effective_batch_size - 1) // effective_batch_size

    emit_progress(
        progress_callback,
        DiscoveryProgressEvent(
            stage="ai_triage_start",
            message="Starting AI relationship triage",
            total=relationship_count,
            extra={
                "relationship_count": relationship_count,
                "batch_count": batch_count,
                "batch_size": effective_batch_size,
                "unit": "relationships",
            },
        ),
    )

    for batch_index, offset in enumerate(
        range(0, relationship_count, effective_batch_size),
        start=1,
    ):
        batch_relationships = relationships[offset : offset + effective_batch_size]
        relationships_done = offset + len(batch_relationships)
        try:
            result = agent.run_sync(
                _related_source_assessment_batch_prompt(
                    category,
                    seed_sources,
                    related_sources,
                    batch_relationships,
                )
            )
            all_assessments.extend(_normalise_related_batch(batch_relationships, result.output))
        except Exception as exc:  # noqa: BLE001 - degrade batch to uncertain assessments
            limitation = f"AI relationship triage batch failed: {exc}"
            all_assessments.extend(
                _uncertain_related_assessment(relationship, limitation=limitation)
                for relationship in batch_relationships
            )
        emit_progress(
            progress_callback,
            DiscoveryProgressEvent(
                stage="ai_triage_batch",
                message=f"Relationship triage batch {batch_index}/{batch_count}",
                current=relationships_done,
                total=relationship_count,
                extra={
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "batch_size": len(batch_relationships),
                    "relationship_count": relationship_count,
                    "unit": "relationships",
                },
            ),
        )

    emit_progress(
        progress_callback,
        DiscoveryProgressEvent(
            stage="ai_triage_complete",
            message="AI relationship triage complete",
            extra={"relationship_count": relationship_count},
        ),
    )

    return all_assessments


# Backwards-compatible alias for CLI/tests.
expand_keywords_deterministic = expand_category_without_ai
