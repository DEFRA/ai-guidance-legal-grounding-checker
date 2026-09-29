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


class ReviewStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    ACCEPTED_WITH_EDITS = "accepted_with_edits"
    REJECTED = "rejected"
    NEEDS_MORE_SOURCES = "needs_more_sources"
    SUPERSEDED = "superseded"

    # Legacy statuses kept for backward compatibility.
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    NEEDS_REVIEW = "needs_review"
