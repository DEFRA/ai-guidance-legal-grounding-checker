import os
import warnings

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Legacy JUDIT_* env names accepted until rename+1. COMPAT_LEGACY_NAME
_ENV_PAIRS = (
    ("LAW_PROPOSITION_EXTRACTOR_LLM_BASE_URL", "JUDIT_LLM_BASE_URL"),
    ("LAW_PROPOSITION_EXTRACTOR_LLM_API_KEY", "JUDIT_LLM_API_KEY"),
    ("LAW_PROPOSITION_EXTRACTOR_MODEL_LOCAL_EXTRACT", "JUDIT_MODEL_LOCAL_EXTRACT"),
    ("LAW_PROPOSITION_EXTRACTOR_MODEL_LOCAL_CLASSIFY", "JUDIT_MODEL_LOCAL_CLASSIFY"),
    ("LAW_PROPOSITION_EXTRACTOR_MODEL_FRONTIER_REASON", "JUDIT_MODEL_FRONTIER_REASON"),
    ("LAW_PROPOSITION_EXTRACTOR_MODEL_FRONTIER_EXTRACT", "JUDIT_MODEL_FRONTIER_EXTRACT"),
    ("LAW_PROPOSITION_EXTRACTOR_LLM_MAX_EXTRACT_INPUT_TOKENS", "JUDIT_LLM_MAX_EXTRACT_INPUT_TOKENS"),
    ("LAW_PROPOSITION_EXTRACTOR_LLM_EXTRACT_MODEL_CONTEXT_LIMIT", "JUDIT_LLM_EXTRACT_MODEL_CONTEXT_LIMIT"),
    ("LAW_PROPOSITION_EXTRACTOR_MODEL_FRONTIER_WRITEUP", "JUDIT_MODEL_FRONTIER_WRITEUP"),
)


def _check_env_conflicts() -> None:
    for canon, legacy in _ENV_PAIRS:
        c, l = os.environ.get(canon), os.environ.get(legacy)
        if c is not None and l is not None and c != l:
            raise RuntimeError(
                f"Conflicting environment values for {canon}={c!r} and {legacy}={l!r}."
            )
        if l is not None and c is None:
            warnings.warn(
                f"Legacy env {legacy!r} is deprecated; use {canon!r}. Removed in rename+1.",
                DeprecationWarning,
                stacklevel=3,
            )


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = Field(
        default="http://127.0.0.1:4000/v1",
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_LLM_BASE_URL", "JUDIT_LLM_BASE_URL"  # COMPAT_LEGACY_NAME
        ),
    )
    api_key: str = Field(
        default="lpe-dev-key",
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_LLM_API_KEY", "JUDIT_LLM_API_KEY"  # COMPAT_LEGACY_NAME
        ),
    )

    local_extract_model: str = Field(
        default="local_extract",
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_MODEL_LOCAL_EXTRACT",
            "JUDIT_MODEL_LOCAL_EXTRACT",  # COMPAT_LEGACY_NAME
        ),
    )
    local_classify_model: str = Field(
        default="local_classify",
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_MODEL_LOCAL_CLASSIFY",
            "JUDIT_MODEL_LOCAL_CLASSIFY",  # COMPAT_LEGACY_NAME
        ),
    )
    frontier_reason_model: str = Field(
        default="frontier_reason",
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_MODEL_FRONTIER_REASON",
            "JUDIT_MODEL_FRONTIER_REASON",  # COMPAT_LEGACY_NAME
        ),
    )
    frontier_extract_model: str = Field(
        default="frontier_extract",
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_MODEL_FRONTIER_EXTRACT",
            "JUDIT_MODEL_FRONTIER_EXTRACT",  # COMPAT_LEGACY_NAME
        ),
    )
    # Conservative max estimated input tokens (prompt + system) before chunking / skipping LLM.
    max_extract_input_tokens: int = Field(
        default=150_000,
        ge=1024,
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_LLM_MAX_EXTRACT_INPUT_TOKENS",
            "JUDIT_LLM_MAX_EXTRACT_INPUT_TOKENS",  # COMPAT_LEGACY_NAME
        ),
    )
    # Documented provider context window for traces / diagnostics (not enforced directly).
    extract_model_context_limit: int = Field(
        default=200_000,
        ge=4096,
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_LLM_EXTRACT_MODEL_CONTEXT_LIMIT",
            "JUDIT_LLM_EXTRACT_MODEL_CONTEXT_LIMIT",  # COMPAT_LEGACY_NAME
        ),
    )
    frontier_writeup_model: str = Field(
        default="frontier_writeup",
        validation_alias=AliasChoices(
            "LAW_PROPOSITION_EXTRACTOR_MODEL_FRONTIER_WRITEUP",
            "JUDIT_MODEL_FRONTIER_WRITEUP",  # COMPAT_LEGACY_NAME
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_env_contract(cls, data):
        _check_env_conflicts()
        return data


_check_env_conflicts()
settings = LLMSettings()
