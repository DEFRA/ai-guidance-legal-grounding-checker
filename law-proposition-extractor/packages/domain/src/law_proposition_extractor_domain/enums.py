from enum import StrEnum


class DivergenceType(StrEnum):
    NONE = "none"
    TEXTUAL = "textual"
    STRUCTURAL = "structural"
    DYNAMIC_REFERENCE = "dynamic_reference"
    TERRITORIAL = "territorial"
    INSTITUTIONAL = "institutional"
    PROCEDURAL = "procedural"
    ANNEX_MODEL_CERTIFICATE = "annex_model_certificate"
    DEFINITIONAL = "definitional"
    REVOCATION_REPLACEMENT = "revocation_replacement"
    UNKNOWN = "unknown"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PropositionTier(StrEnum):
    INSTRUMENT_METADATA = "instrument_metadata"
    SCOPE_RULE = "scope_rule"
    SUBSTANTIVE_RULE = "substantive_rule"
    PROCEDURAL_RULE = "procedural_rule"
    DEFINITIONAL_RULE = "definitional_rule"
    RELATIONSHIP_REFERENCE = "relationship_reference"
    UNKNOWN = "unknown"


class LegalEffectType(StrEnum):
    CITATION = "citation"
    COMMENCEMENT = "commencement"
    EXTENT = "extent"
    APPLICATION_SCOPE = "application_scope"
    DEFINITION = "definition"
    OBLIGATION = "obligation"
    PROHIBITION = "prohibition"
    PERMISSION = "permission"
    POWER = "power"
    RECORDKEEPING = "recordkeeping"
    NOTIFICATION = "notification"
    CERTIFICATION = "certification"
    INSPECTION = "inspection"
    ENFORCEMENT = "enforcement"
    APPEAL = "appeal"
    DEROGATION = "derogation"
    CROSS_REFERENCE = "cross_reference"
    UNKNOWN = "unknown"


class ReviewStatus(StrEnum):
    PROPOSED = "proposed"
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    ACCEPTED_WITH_EDITS = "accepted_with_edits"
    REJECTED = "rejected"
    NEEDS_MORE_SOURCES = "needs_more_sources"
    SUPERSEDED = "superseded"

    # Legacy statuses kept for backward compatibility.
    DRAFT = "draft"
    IN_REVIEW = "in_review"


class SourceManifestationType(StrEnum):
    """Authority-identified legislation.gov.uk manifestation of consumed text.

    Records how the source labelled the snapshot. Does not assert that Law Proposition Extractor
    independently applied or verified amendments.
    """

    ORIGINAL = "original"
    REVISED = "revised"
    POINT_IN_TIME = "point_in_time"
    PROSPECTIVE = "prospective"
    UNKNOWN = "unknown"


class SourceManifestationBasis(StrEnum):
    """Where manifestation classification evidence came from."""

    REQUEST_URL = "request_url"
    RESOLVED_URL = "resolved_url"
    SOURCE_METADATA = "source_metadata"
    REQUEST_AND_SOURCE_METADATA = "request_and_source_metadata"
    UNAVAILABLE = "unavailable"


class SourceEffectStatus(StrEnum):
    """What the authority/source reported about an effect — not Law Proposition Extractor application."""

    SOURCE_MARKS_APPLIED = "source_marks_applied"
    SOURCE_MARKS_OUTSTANDING = "source_marks_outstanding"
    SOURCE_MARKS_PARTIALLY_APPLIED = "source_marks_partially_applied"
    SOURCE_STATUS_UNKNOWN = "source_status_unknown"


class SourceEffectRepresentationStatus(StrEnum):
    """How the effect/annotation appeared in the consumed source representation."""

    ANNOTATION_PRESENT = "annotation_present"
    EFFECT_METADATA_PRESENT = "effect_metadata_present"
    REVISED_TEXT_REFERENCE_PRESENT = "revised_text_reference_present"
    UNKNOWN = "unknown"


class SourceEffectCategory(StrEnum):
    """Conservative normalized category derived from explicit source markers."""

    INSERTION = "insertion"
    SUBSTITUTION = "substitution"
    OMISSION = "omission"
    REPEAL = "repeal"
    REVOCATION = "revocation"
    COMMENCEMENT = "commencement"
    EXTENT = "extent"
    EDITORIAL_NOTE = "editorial_note"
    OTHER = "other"
    UNKNOWN = "unknown"


class OutstandingEffectsStatus(StrEnum):
    """Aggregate outstanding-effect status grounded only in explicit source metadata."""

    SOURCE_REPORTS_NONE = "source_reports_none"
    SOURCE_REPORTS_PRESENT = "source_reports_present"
    SOURCE_STATUS_UNKNOWN = "source_status_unknown"


class AffectingInstrumentConsumptionStatus(StrEnum):
    """Whether Law Proposition Extractor independently consumed the affecting instrument."""

    CONSUMED_IN_CURRENT_RUN = "consumed_in_current_run"
    PRESENT_IN_SOURCE_REGISTER_BUT_NOT_CONSUMED = "present_in_source_register_but_not_consumed"
    NOT_MATCHED = "not_matched"
    NOT_ASSESSED = "not_assessed"


class ConsumptionMatchBasis(StrEnum):
    """How an affecting instrument was matched to a run-scoped source identity."""

    CANONICAL_AUTHORITY_URI = "canonical_authority_uri"
    AUTHORITY_IDENTIFIER = "authority_identifier"
    CELEX_IDENTIFIER = "celex_identifier"
    NORMALIZED_CITATION = "normalized_citation"
    SOURCE_REGISTER_URI = "source_register_uri"
    NO_MATCH = "no_match"
    INSUFFICIENT_IDENTITY = "insufficient_identity"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"


class DecisionStage(StrEnum):
    """Pipeline stage that produced a DecisionExplanation.

    Extend with new members as explainability coverage grows; do not rename
    existing values.

    Ordering for artifact consumers (not emission order):
    provenance → selection → extraction → classification → grouping →
    relationship → effective_law → source_effect → review.
    """

    PROVENANCE = "provenance"
    SELECTION = "selection"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    GROUPING = "grouping"
    RELATIONSHIP = "relationship"
    EFFECTIVE_LAW = "effective_law"
    SOURCE_EFFECT = "source_effect"
    REVIEW = "review"


class DecisionType(StrEnum):
    """Kind of decision recorded in a DecisionExplanation."""

    SELECT = "select"
    SUPPRESS = "suppress"
    EXCLUDE = "exclude"
    RETAIN = "retain"
    DIAGNOSE = "diagnose"
    CLASSIFY = "classify"
    INFER = "infer"
    TARGET = "target"
    GROUP = "group"
    ATTACH = "attach"
    LINK = "link"
    INHERIT = "inherit"
    ASSESS = "assess"


class DecisionSubjectKind(StrEnum):
    """What the DecisionExplanation subject identifies."""

    SOURCE_FRAGMENT = "source_fragment"
    SOURCE_SNAPSHOT = "source_snapshot"
    SOURCE_LEGAL_EFFECT = "source_legal_effect"
    PROPOSITION = "proposition"
    EXTRACTION_CANDIDATE = "extraction_candidate"
    LEGAL_RULE_RELATIONSHIP = "legal_rule_relationship"
    LEGAL_RULE_GROUP = "legal_rule_group"
    EFFECTIVE_LAW_STATEMENT = "effective_law_statement"


class HeuristicMethod(StrEnum):
    """How a registered heuristic reaches its outcome."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    HYBRID = "hybrid"
    HUMAN = "human"
    CONFIGURATION = "configuration"


class StructuralHeadingKind(StrEnum):
    """Kind of source-provided legislative heading on a structural fragment.

    Distinguishes provision/container headings from proposition labels and
    locator display text. Unknown future values coerce to UNKNOWN on load.
    """

    PART = "part"
    TITLE = "title"
    CHAPTER = "chapter"
    DIVISION = "division"
    SECTION = "section"
    ARTICLE = "article"
    REGULATION = "regulation"
    RULE = "rule"
    SCHEDULE = "schedule"
    ANNEX = "annex"
    PROVISION = "provision"
    CROSS_HEADING = "cross_heading"
    UNKNOWN = "unknown"
