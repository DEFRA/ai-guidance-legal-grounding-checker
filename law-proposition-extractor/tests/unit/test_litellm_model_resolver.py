"""LiteLLM alias → provider model resolution."""

from __future__ import annotations

from pathlib import Path

from law_proposition_extractor_pipeline.litellm_model_resolver import (
    load_alias_map_from_config,
    parse_litellm_yaml_alias_map,
    provider_model_for_alias,
    resolve_litellm_aliases,
)
from law_proposition_extractor_pipeline.litellm_model_resolver import LiteLLMAliasResolution

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LITELLM_CONFIG = _REPO_ROOT / "config" / "litellm.yaml"


def test_parse_litellm_yaml_alias_map() -> None:
    text = """
model_list:
  - model_name: frontier_extract
    litellm_params:
      model: anthropic/claude-sonnet-4-5-20250929
  - model_name: local_extract
    litellm_params:
      model: ollama/qwen3:14b
      api_base: http://127.0.0.1:11434
"""
    assert parse_litellm_yaml_alias_map(text) == {
        "frontier_extract": "anthropic/claude-sonnet-4-5-20250929",
        "local_extract": "ollama/qwen3:14b",
    }


def test_load_alias_map_from_repo_config() -> None:
    if not _LITELLM_CONFIG.is_file():
        return
    mapping = load_alias_map_from_config(_LITELLM_CONFIG)
    assert mapping["frontier_extract"] == "anthropic/claude-sonnet-4-5-20250929"
    assert mapping["local_extract"].startswith("ollama/")


def test_provider_model_for_alias_prefers_config() -> None:
    resolution = LiteLLMAliasResolution(
        alias_to_provider={"frontier_extract": "anthropic/claude-sonnet-4-5-20250929"},
        sources=["config:test"],
    )
    provider, _note = provider_model_for_alias("frontier_extract", resolution)
    assert provider == "anthropic/claude-sonnet-4-5-20250929"


def test_resolve_litellm_aliases_uses_config_without_proxy() -> None:
    if not _LITELLM_CONFIG.is_file():
        return
    resolution = resolve_litellm_aliases(config_path=_LITELLM_CONFIG, try_proxy=False)
    assert "frontier_extract" in resolution.alias_to_provider
    assert any(s.startswith("config:") for s in resolution.sources)
