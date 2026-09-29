"""LLM extraction endpoint description, preflight, and CLI fallback defaults."""

from __future__ import annotations

from typing import Any, Literal

from law_proposition_extractor_llm.client import JuditLLMClient
from law_proposition_extractor_llm.settings import LLMSettings

ExtractionMode = Literal["heuristic", "local", "frontier"]

PROPOSITION_EXTRACTION_DERIVED_CACHE_STAGES: tuple[str, ...] = (
    "proposition_extraction",
    "proposition_extraction_chunk",
)


def resolve_extraction_fallback_for_run(
    *,
    use_llm: bool,
    extraction_fallback: str | None,
) -> str:
    """CLI / pipeline default: fail closed when LLM extraction is enabled."""
    if extraction_fallback is not None:
        return extraction_fallback
    return "fail_closed" if use_llm else "fallback"


def resolve_retry_failed_extraction_cache(
    *,
    extraction_mode: str,
    extraction_fallback: str,
    retry_failed_extraction_cache: bool | None = None,
    ignore_failed_extraction_cache: bool = False,
    retry_failed_llm: bool | None = None,
) -> bool:
    """
    Whether to bypass derived-cache entries for failed extraction chunks and re-call the model.

    Default: retry when model-backed extraction uses fail_closed; otherwise reuse cached failures.
    """
    if ignore_failed_extraction_cache and retry_failed_extraction_cache is True:
        raise ValueError(
            "Cannot set both --ignore-failed-extraction-cache and --retry-failed-extraction-cache."
        )
    if ignore_failed_extraction_cache:
        return False
    explicit = (
        retry_failed_extraction_cache
        if retry_failed_extraction_cache is not None
        else retry_failed_llm
    )
    if explicit is not None:
        return explicit
    if extraction_mode in {"local", "frontier"} and extraction_fallback == "fail_closed":
        return True
    return False


def format_clear_proposition_extraction_cache_command(derived_cache_dir: str) -> str:
    """Shell snippet to drop only proposition extraction derived cache for a run."""
    base = derived_cache_dir.rstrip("/")
    parts = [f"{base}/{stage}" for stage in PROPOSITION_EXTRACTION_DERIVED_CACHE_STAGES]
    return f"rm -rf {' '.join(parts)}"


def format_failed_chunk_cache_operator_hint(
    *,
    derived_cache_dir: str | None,
    skip_reasons_by_type: dict[str, int] | None = None,
) -> str:
    """Actionable hint when all LLM work was skipped due to cached chunk failures."""
    failed_count = int((skip_reasons_by_type or {}).get("failed_chunk_cached") or 0)
    if failed_count <= 0:
        return ""
    lines = [
        "Cached failed extraction chunks were not retried.",
        "Re-run with --retry-failed-extraction-cache (default for fail_closed), "
        "or pass --ignore-failed-extraction-cache to reuse cached failures without LLM calls.",
    ]
    if derived_cache_dir:
        lines.append(
            f"Clear only proposition extraction cache: "
            f"{format_clear_proposition_extraction_cache_command(derived_cache_dir)}"
        )
        lines.append(f"Or use a fresh derived cache: --derived-cache-dir <new-path>")
    return " ".join(lines)


def resolve_extraction_mode_requested(
    *,
    use_llm: bool,
    extraction_mode: str | None,
    case_data: dict[str, Any],
) -> str:
    """Mode the operator asked for (CLI flag, case file, or --use-llm default)."""
    em = extraction_mode
    if em is None:
        case_ex = case_data.get("extraction")
        if isinstance(case_ex, dict):
            raw = case_ex.get("mode")
            if isinstance(raw, str) and raw.strip():
                em = raw.strip()
    if em is None:
        em = "local" if use_llm else "heuristic"
    return em


def describe_llm_extraction_endpoint(
    extraction_mode: ExtractionMode,
    settings: LLMSettings,
) -> dict[str, str]:
    """Human-readable LiteLLM alias + gateway URL for local / frontier extraction."""
    if extraction_mode == "frontier":
        model_alias = str(getattr(settings, "frontier_extract_model", "frontier_extract"))
        profile = "frontier_extract"
        backend_hint = "Anthropic via LiteLLM (see config/litellm.yaml → frontier_extract)"
    elif extraction_mode == "local":
        model_alias = str(getattr(settings, "local_extract_model", "local_extract"))
        profile = "local_extract"
        backend_hint = "Ollama via LiteLLM (see config/litellm.yaml → local_extract)"
    else:
        return {}
    return {
        "extraction_mode": extraction_mode,
        "model_alias": model_alias,
        "profile": profile,
        "litellm_base_url": str(getattr(settings, "base_url", "http://127.0.0.1:4000/v1")),
        "backend_hint": backend_hint,
    }


def format_llm_extraction_endpoint_line(endpoint: dict[str, str]) -> str:
    if not endpoint:
        return ""
    return (
        f"extraction_mode={endpoint['extraction_mode']} "
        f"profile={endpoint['profile']} "
        f"model_alias={endpoint['model_alias']} "
        f"base_url={endpoint['litellm_base_url']} "
        f"({endpoint['backend_hint']})"
    )


def preflight_llm_extraction(
    llm_client: JuditLLMClient,
    extraction_mode: ExtractionMode,
) -> None:
    """
    Probe the configured LiteLLM alias before processing many fragments.

    Raises RuntimeError with operator guidance when the gateway or backend is misconfigured.
    """
    if extraction_mode not in {"local", "frontier"}:
        return
    settings = llm_client.settings
    endpoint = describe_llm_extraction_endpoint(extraction_mode, settings)
    model_alias = endpoint["model_alias"]
    try:
        llm_client.complete_text(
            prompt='{"ping":true}',
            model=model_alias,
            system_prompt="Reply with JSON only.",
            temperature=0.0,
            enforce_json_object=True,
        )
    except Exception as exc:
        msg = str(exc).strip()
        hint = _preflight_error_hint(msg, extraction_mode, settings)
        raise RuntimeError(
            f"LLM extraction preflight failed for {format_llm_extraction_endpoint_line(endpoint)}: {msg}{hint}"
        ) from exc


def _preflight_error_hint(message: str, extraction_mode: str, settings: LLMSettings) -> str:
    lower = message.lower()
    parts: list[str] = []
    if "no connected db" in lower or "connected db" in lower:
        parts.append(
            " LiteLLM proxy has DATABASE_URL set but no reachable database — run "
            "`just litellm` (which unsets DATABASE_URL) or unset DATABASE_URL in your shell."
        )
    base_url = str(getattr(settings, "base_url", "http://127.0.0.1:4000/v1"))
    if extraction_mode == "local" and ("connection" in lower or "connect" in lower or "11434" in lower):
        parts.append(
            " Local mode expects Ollama at http://127.0.0.1:11434 (config/litellm.yaml) and LiteLLM on "
            f"{base_url}."
        )
    if extraction_mode == "frontier" and ("api" in lower or "auth" in lower or "key" in lower):
        parts.append(" Frontier mode expects ANTHROPIC_API_KEY and LiteLLM proxy with frontier_extract alias.")
    if not parts:
        parts.append(
            " Ensure LiteLLM proxy is running (`just litellm`), LAW_PROPOSITION_EXTRACTOR_LLM_BASE_URL/LAW_PROPOSITION_EXTRACTOR_LLM_API_KEY are set, "
            "and the backend for this profile is available."
        )
    return "".join(parts)
