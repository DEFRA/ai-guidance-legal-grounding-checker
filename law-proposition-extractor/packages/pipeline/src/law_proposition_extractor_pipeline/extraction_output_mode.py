"""Extraction LLM structured output modes (json_object, json_schema, text_then_parse)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from law_proposition_extractor_llm.settings import LLMSettings

ExtractionOutputMode = Literal["json_object", "json_schema", "text_then_parse"]

V2_PROPOSITION_ITEM_REQUIRED_FIELDS: tuple[str, ...] = (
    "proposition_text",
    "display_label",
    "subject",
    "rule",
    "object",
    "conditions",
    "exceptions",
    "temporal_condition",
    "provision_type",
    "source_locator",
    "evidence_text",
    "completeness_status",
    "confidence",
    "reason",
)

class ExtractionOutputModeUnsupportedError(RuntimeError):
    """Raised when the requested output mode cannot be used with the configured provider."""


class ExtractionOutputModeRejectedError(RuntimeError):
    """Raised when the provider rejects structured output for the requested mode."""


def build_v2_extraction_json_schema_dict() -> dict[str, Any]:
    """JSON Schema document (inner ``schema``) for v2 extraction responses."""
    item_properties = {name: {"type": "string"} for name in V2_PROPOSITION_ITEM_REQUIRED_FIELDS}
    item_properties["conditions"] = {"type": "array", "items": {"type": "string"}}
    item_properties["exceptions"] = {"type": "array", "items": {"type": "string"}}
    for name in (
        "proposition_text",
        "display_label",
        "subject",
        "rule",
        "object",
        "temporal_condition",
        "provision_type",
        "source_locator",
        "evidence_text",
        "completeness_status",
        "confidence",
        "reason",
    ):
        item_properties[name] = {"type": "string"}

    return {
        "type": "object",
        "properties": {
            "propositions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": item_properties,
                    "required": list(V2_PROPOSITION_ITEM_REQUIRED_FIELDS),
                    "additionalProperties": False,
                },
            },
            "empty_rationale": {"type": "string"},
        },
        "required": ["propositions"],
        "additionalProperties": False,
    }


def build_litellm_json_schema_wrapper() -> dict[str, Any]:
    """LiteLLM / OpenAI ``response_format.json_schema`` wrapper."""
    return {
        "name": "judit_extraction_v2",
        "strict": True,
        "schema": build_v2_extraction_json_schema_dict(),
    }


# Backward-compatible alias used by extract.py imports.
V2_EXTRACTION_JSON_SCHEMA: dict[str, Any] = build_litellm_json_schema_wrapper()


def schema_hash(schema: dict[str, Any] | None = None) -> str:
    """Stable short hash of the extraction JSON schema sent to the provider."""
    payload = schema if schema is not None else build_litellm_json_schema_wrapper()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def response_format_type_for_mode(mode: ExtractionOutputMode) -> str:
    if mode == "json_schema":
        return "json_schema"
    if mode == "json_object":
        return "json_object"
    return "none"


def build_response_format_for_mode(mode: ExtractionOutputMode) -> dict[str, Any] | None:
    if mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": build_litellm_json_schema_wrapper(),
        }
    if mode == "json_object":
        return {"type": "json_object"}
    return None


def provider_supports_json_schema(
    *,
    extraction_mode: str,
    model_alias: str,
    settings: LLMSettings | None = None,
) -> bool:
    """Whether the configured provider/model is expected to accept json_schema response_format."""
    alias = str(model_alias or "").strip().lower()
    if alias.endswith("_schema") or alias.endswith("_json_schema"):
        return True
    if extraction_mode == "local":
        return True
    if extraction_mode == "frontier":
        frontier = str(getattr(settings, "frontier_extract_model", "frontier_extract") or "").lower()
        if frontier.endswith("_schema") or frontier.endswith("_json_schema"):
            return True
        if "claude" in frontier or "anthropic" in frontier:
            return True
    return False


def resolve_extraction_output_mode(
    *,
    extraction_mode: str,
    model_alias: str,
    requested: ExtractionOutputMode | str | None = None,
    settings: LLMSettings | None = None,
) -> ExtractionOutputMode:
    """
    Resolve effective extraction output mode.

    Defaults:
    - explicit ``requested`` wins when set
    - local: json_schema when provider supports it, else json_object
    - frontier: json_object unless provider is schema-capable and caller did not override
    """
    if requested is not None:
        mode = str(requested).strip()
        if mode not in {"json_object", "json_schema", "text_then_parse"}:
            raise ValueError(
                f"extraction_output_mode must be json_object, json_schema, or text_then_parse; got {requested!r}"
            )
        return mode  # type: ignore[return-value]

    if extraction_mode == "local":
        if provider_supports_json_schema(
            extraction_mode=extraction_mode, model_alias=model_alias, settings=settings
        ):
            return "json_schema"
        return "json_object"
    if extraction_mode == "frontier":
        if provider_supports_json_schema(
            extraction_mode=extraction_mode, model_alias=model_alias, settings=settings
        ):
            return "json_schema"
        return "json_object"
    return "json_object"


def ensure_output_mode_supported(
    *,
    extraction_output_mode: ExtractionOutputMode,
    extraction_mode: str,
    model_alias: str,
    settings: LLMSettings | None = None,
    allow_fallback: bool = False,
) -> ExtractionOutputMode:
    """
    Return the mode to use, or raise when json_schema is unsupported and fallback is disallowed.
    """
    if extraction_output_mode != "json_schema":
        return extraction_output_mode
    if provider_supports_json_schema(
        extraction_mode=extraction_mode,
        model_alias=model_alias,
        settings=settings,
    ):
        return extraction_output_mode
    if allow_fallback:
        return "json_object"
    raise ExtractionOutputModeUnsupportedError(
        f"extraction_output_mode=json_schema is not supported for extraction_mode={extraction_mode!r} "
        f"model_alias={model_alias!r}. Use --allow-output-mode-fallback to fall back to json_object, "
        f"or pass --extraction-output-mode json_object."
    )


def fallback_output_mode(mode: ExtractionOutputMode) -> ExtractionOutputMode | None:
    if mode == "json_schema":
        return "json_object"
    return None


_SCHEMA_REJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"json_schema", re.I),
    re.compile(r"response_format", re.I),
    re.compile(r"structured.?output", re.I),
    re.compile(r"does not support", re.I),
    re.compile(r"not supported", re.I),
    re.compile(r"invalid.*format", re.I),
)


def is_output_mode_rejection_error(message: str) -> bool:
    blob = str(message or "")
    if not blob.strip():
        return False
    return any(pattern.search(blob) for pattern in _SCHEMA_REJECTION_PATTERNS)


def validate_parsed_extraction_schema(
    parsed: Any,
    *,
    extraction_output_mode: ExtractionOutputMode,
) -> tuple[bool, str | None]:
    """
    Post-parse structural validation for json_schema mode.

    Rejects ``{}`` and objects missing required ``propositions``.
    ``empty_rationale`` is only allowed when ``propositions`` is an empty list.
    """
    if extraction_output_mode != "json_schema":
        return True, None
    if not isinstance(parsed, dict):
        return False, "parsed JSON must be an object with required field propositions"
    if "propositions" not in parsed:
        return False, "missing required field propositions"
    propositions = parsed.get("propositions")
    if not isinstance(propositions, list):
        return False, "propositions must be an array"
    empty_rationale = parsed.get("empty_rationale")
    if empty_rationale is not None and propositions:
        return False, "empty_rationale is only allowed when propositions is empty"
    if not propositions:
        if not str(empty_rationale or "").strip():
            return False, "propositions is empty but empty_rationale is missing"
        return True, None
    for idx, item in enumerate(propositions):
        if not isinstance(item, dict):
            return False, f"propositions[{idx}] must be an object"
        missing = [f for f in V2_PROPOSITION_ITEM_REQUIRED_FIELDS if f not in item]
        if missing:
            return False, f"propositions[{idx}] missing required fields: {', '.join(missing)}"
    return True, None


def output_mode_trace_fields(
    *,
    extraction_output_mode: ExtractionOutputMode,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rf = response_format if response_format is not None else build_response_format_for_mode(
        extraction_output_mode
    )
    fields: dict[str, Any] = {
        "extraction_output_mode": extraction_output_mode,
        "response_format_type": response_format_type_for_mode(extraction_output_mode),
    }
    if extraction_output_mode == "json_schema":
        fields["schema_hash"] = schema_hash()
    if rf is not None:
        fields["response_format"] = rf
    return fields
