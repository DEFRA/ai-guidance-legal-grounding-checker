import pytest

from law_proposition_extractor_llm.settings import LLMSettings
from law_proposition_extractor_pipeline.llm_extraction_config import (
    _preflight_error_hint,
    format_clear_proposition_extraction_cache_command,
    format_failed_chunk_cache_operator_hint,
    resolve_extraction_fallback_for_run,
    resolve_extraction_mode_requested,
    resolve_retry_failed_extraction_cache,
)


def test_resolve_extraction_fallback_fail_closed_with_use_llm() -> None:
    assert resolve_extraction_fallback_for_run(use_llm=True, extraction_fallback=None) == "fail_closed"
    assert (
        resolve_extraction_fallback_for_run(use_llm=True, extraction_fallback="mark_needs_review")
        == "mark_needs_review"
    )


def test_resolve_extraction_fallback_heuristic_default_without_use_llm() -> None:
    assert resolve_extraction_fallback_for_run(use_llm=False, extraction_fallback=None) == "fallback"


def test_resolve_extraction_mode_requested_use_llm_default_local() -> None:
    assert (
        resolve_extraction_mode_requested(use_llm=True, extraction_mode=None, case_data={}) == "local"
    )


def test_preflight_hint_no_connected_db() -> None:
    settings = LLMSettings()
    hint = _preflight_error_hint("Error code: 400 - No connected db.", "local", settings)
    assert "DATABASE_URL" in hint
    assert "just litellm" in hint


def test_resolve_retry_failed_extraction_cache_fail_closed_defaults_true() -> None:
    assert (
        resolve_retry_failed_extraction_cache(
            extraction_mode="local",
            extraction_fallback="fail_closed",
        )
        is True
    )


def test_resolve_retry_failed_extraction_cache_ignore_wins() -> None:
    assert (
        resolve_retry_failed_extraction_cache(
            extraction_mode="local",
            extraction_fallback="fail_closed",
            ignore_failed_extraction_cache=True,
        )
        is False
    )


def test_resolve_retry_failed_extraction_cache_explicit_false() -> None:
    assert (
        resolve_retry_failed_extraction_cache(
            extraction_mode="frontier",
            extraction_fallback="fail_closed",
            retry_failed_extraction_cache=False,
        )
        is False
    )


def test_resolve_retry_conflicting_flags_raises() -> None:
    with pytest.raises(ValueError, match="Cannot set both"):
        resolve_retry_failed_extraction_cache(
            extraction_mode="local",
            extraction_fallback="fail_closed",
            ignore_failed_extraction_cache=True,
            retry_failed_extraction_cache=True,
        )


def test_failed_chunk_cache_hint_mentions_flags_and_clear_command() -> None:
    hint = format_failed_chunk_cache_operator_hint(
        derived_cache_dir="/tmp/lpe-derived",
        skip_reasons_by_type={"failed_chunk_cached": 3},
    )
    assert "--retry-failed-extraction-cache" in hint
    assert "--ignore-failed-extraction-cache" in hint
    assert format_clear_proposition_extraction_cache_command("/tmp/lpe-derived") in hint
