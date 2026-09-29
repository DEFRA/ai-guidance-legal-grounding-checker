"""Classify empty LLM extraction outcomes for operator inspection."""

from __future__ import annotations

import json
from typing import Any

# Granular empty-response categories (replace legacy ``empty_model_response`` in traces).
TRANSPORT_EMPTY_RESPONSE = "transport_empty_response"
PARSED_EMPTY_PROPOSITION_LIST = "parsed_empty_proposition_list"
NON_JSON_RESPONSE = "non_json_response"
SCHEMA_VALID_BUT_EMPTY = "schema_valid_but_empty"
POST_FILTER_REMOVED_ALL = "post_filter_removed_all"
EXTRACTION_SCHEMA_VIOLATION = "extraction_schema_violation"

GRANULAR_EMPTY_FAILURE_TYPES: frozenset[str] = frozenset(
    {
        TRANSPORT_EMPTY_RESPONSE,
        PARSED_EMPTY_PROPOSITION_LIST,
        NON_JSON_RESPONSE,
        SCHEMA_VALID_BUT_EMPTY,
        POST_FILTER_REMOVED_ALL,
        EXTRACTION_SCHEMA_VIOLATION,
    }
)

# Empty outcomes eligible for a targeted one-shot retry (local/frontier only).
RETRYABLE_EMPTY_FAILURE_TYPES: frozenset[str] = frozenset(
    {
        SCHEMA_VALID_BUT_EMPTY,
        PARSED_EMPTY_PROPOSITION_LIST,
        EXTRACTION_SCHEMA_VIOLATION,
    }
)

DEFAULT_EMPTY_EXTRACTION_RETRY_COUNT = 1

_EMPTY_EXTRACTION_RETRY_INSTRUCTION = (
    "Your previous response was `{previous}`, which is invalid for this task. "
    "Return an object with a `propositions` array. "
    'If no propositions exist, return `{{"propositions":[],"empty_rationale":"..."}}`.'
)

LEGACY_EMPTY_MODEL_RESPONSE = "empty_model_response"

RAW_FAILURE_EXCERPT_CAP = 4000


def row_has_extractable_atoms(item: dict[str, Any]) -> bool:
    """True when a parsed proposition object carries at least one substantive field."""
    return bool(
        str(item.get("proposition_text") or "").strip()
        or str(item.get("subject") or "").strip()
        or str(item.get("rule") or "").strip()
    )


def parse_model_propositions_container(parsed: Any) -> tuple[list[dict[str, Any]], list[Any]]:
    """Return (dict rows, raw propositions list from JSON container)."""
    if isinstance(parsed, dict) and isinstance(parsed.get("propositions"), list):
        raw_list = parsed["propositions"]
        return [x for x in raw_list if isinstance(x, dict)], raw_list
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)], parsed
    return [], []


def is_empty_extraction_retry_eligible(
    failure_type: str | None,
    *,
    extraction_mode: str,
    retry_transport_empty: bool = False,
) -> bool:
    """True when a failed local/frontier extraction attempt should be retried once."""
    if extraction_mode not in {"local", "frontier"}:
        return False
    ft = str(failure_type or "").strip()
    if ft in RETRYABLE_EMPTY_FAILURE_TYPES:
        return True
    return retry_transport_empty and ft == TRANSPORT_EMPTY_RESPONSE


def empty_extraction_retry_not_eligible_reason(
    failure_type: str | None,
    *,
    extraction_mode: str,
    retry_transport_empty: bool = False,
) -> str | None:
    """Human-readable reason when empty-extraction retry is not eligible, else None."""
    if is_empty_extraction_retry_eligible(
        failure_type,
        extraction_mode=extraction_mode,
        retry_transport_empty=retry_transport_empty,
    ):
        return None
    if extraction_mode not in {"local", "frontier"}:
        return f"extraction_mode {extraction_mode!r} does not support empty-extraction retry"
    ft = str(failure_type or "").strip()
    if not ft:
        return "first attempt did not record a failure_type"
    if ft == TRANSPORT_EMPTY_RESPONSE:
        return (
            "failure_type transport_empty_response is not retried unless "
            "retry_empty_extraction_transport is enabled"
        )
    return f"failure_type {ft!r} is not in the empty-extraction retry set"


def build_empty_extraction_retry_prompt_suffix(
    previous_raw: str | None,
    *,
    excerpt_cap: int = 500,
) -> str:
    """Prompt suffix appended on the second empty-extraction retry attempt."""
    prev = (previous_raw or "").strip()
    if not prev:
        prev = "{}"
    elif len(prev) > excerpt_cap:
        prev = prev[:excerpt_cap] + "…"
    return _EMPTY_EXTRACTION_RETRY_INSTRUCTION.format(previous=prev)


def classify_empty_extraction_outcome(
    *,
    raw: str | None,
    parsed: Any | None = None,
    raw_rows: list[dict[str, Any]] | None = None,
    json_parse_failed: bool = False,
) -> tuple[str, str]:
    """Return ``(failure_type, failure_reason)`` for an empty model outcome."""
    text = (raw or "").strip()
    rows = list(raw_rows or [])
    if not text:
        return TRANSPORT_EMPTY_RESPONSE, "provider returned no content"
    if json_parse_failed:
        return NON_JSON_RESPONSE, "model returned non-JSON or unparseable JSON"
    container_rows, raw_container = parse_model_propositions_container(parsed)
    if rows:
        if any(row_has_extractable_atoms(r) for r in rows):
            return POST_FILTER_REMOVED_ALL, (
                f"model produced {len(rows)} candidate row(s) but validation removed all"
            )
        return SCHEMA_VALID_BUT_EMPTY, (
            "parsed JSON contained proposition objects but none had extractable atoms"
        )
    if isinstance(parsed, dict):
        if "propositions" not in parsed:
            return SCHEMA_VALID_BUT_EMPTY, "parsed JSON object without propositions field"
        if isinstance(parsed.get("propositions"), list):
            if not parsed["propositions"]:
                return PARSED_EMPTY_PROPOSITION_LIST, "model returned valid JSON with propositions=[]"
            if raw_container and not container_rows:
                return SCHEMA_VALID_BUT_EMPTY, (
                    "parsed JSON propositions list had entries but no valid proposition objects"
                )
    if isinstance(parsed, list) and not parsed:
        return PARSED_EMPTY_PROPOSITION_LIST, "model returned valid JSON with empty proposition list"
    if parsed is not None:
        try:
            json.dumps(parsed)
            return PARSED_EMPTY_PROPOSITION_LIST, "model returned valid JSON with no proposition rows"
        except (TypeError, ValueError):
            pass
    return PARSED_EMPTY_PROPOSITION_LIST, "model returned no propositions"


def classify_extraction_failure_type(
    message: str,
    *,
    explicit_failure_type: str | None = None,
) -> str:
    """Coarse failure category for operator inspection (broader than repairable-only)."""
    if explicit_failure_type:
        ft = str(explicit_failure_type).strip()
        if ft in GRANULAR_EMPTY_FAILURE_TYPES:
            return ft
        if ft and ft != LEGACY_EMPTY_MODEL_RESPONSE:
            return ft

    from .extraction_repair import classify_repairable_failure_type

    blob = (message or "").lower()
    if not blob.strip():
        return "unknown"
    repairable = classify_repairable_failure_type(message)
    if repairable:
        return repairable
    if "provider returned no content" in blob:
        return TRANSPORT_EMPTY_RESPONSE
    if "propositions=[]" in blob or "with propositions=[]" in blob:
        return PARSED_EMPTY_PROPOSITION_LIST
    if "non-json" in blob or "unparseable json" in blob:
        return NON_JSON_RESPONSE
    if "no extractable atoms" in blob or "no valid proposition objects" in blob:
        return SCHEMA_VALID_BUT_EMPTY
    if "validation removed all" in blob or "post_filter" in blob:
        return POST_FILTER_REMOVED_ALL
    if "schema validation" in blob or "validation failed" in blob or "validation error" in blob:
        return "schema_validation_error"
    if "model returned no propositions" in blob or "returned no propositions" in blob:
        return LEGACY_EMPTY_MODEL_RESPONSE
    if "no valid rows" in blob or "produced no valid" in blob:
        return "no_valid_rows"
    if "failed chunk cache" in blob or "failed_chunk_cached" in blob:
        return "failed_chunk_cached"
    if "context window" in blob or "context_window" in blob:
        return "context_window"
    if "skipped" in blob and "cache" in blob:
        return "cache_skip"
    return "other_extraction_failure"


def build_llm_failure_trace_fields(
    *,
    raw: str | None,
    failure_type: str,
    failure_reason: str,
    model_alias: str,
    prompt_version: str,
    prompt_text: str,
    fragment_locator: str | None,
    estimated_input_tokens: int | None,
    finish_reason: str | None = None,
    parse_error_message: str | None = None,
    parse_error_line: int | None = None,
    parse_error_column: int | None = None,
    candidate_row_count: int | None = None,
    accepted_row_count: int | None = None,
) -> dict[str, Any]:
    """Safe diagnostic fields persisted on failed extraction LLM traces."""
    from .extract import _safe_model_output_excerpt
    from .intake import content_hash

    excerpt = ""
    truncated = False
    if isinstance(raw, str) and raw:
        excerpt, truncated = _safe_model_output_excerpt(raw, cap=RAW_FAILURE_EXCERPT_CAP)
    fields: dict[str, Any] = {
        "failure_type": failure_type,
        "failure_reason": failure_reason,
        "model_error": failure_reason,
        "raw_model_output_excerpt": excerpt,
        "raw_model_output_truncated": truncated,
        "finish_reason": finish_reason,
        "prompt_version": prompt_version,
        "prompt_template_id": f"extraction_v2:{prompt_version}",
        "prompt_hash": content_hash(prompt_text)[:16],
        "fragment_locator": fragment_locator,
    }
    if isinstance(estimated_input_tokens, int) and estimated_input_tokens > 0:
        fields["estimated_input_tokens"] = estimated_input_tokens
    if parse_error_message:
        fields["parse_error_message"] = parse_error_message
    if isinstance(parse_error_line, int):
        fields["parse_error_line"] = parse_error_line
    if isinstance(parse_error_column, int):
        fields["parse_error_column"] = parse_error_column
    if candidate_row_count is not None:
        fields["candidate_row_count"] = candidate_row_count
    if accepted_row_count is not None:
        fields["accepted_row_count"] = accepted_row_count
    return fields
