"""Resolve LiteLLM proxy aliases to provider model strings (config file or live proxy)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from law_proposition_extractor_llm.settings import LLMSettings, settings as default_llm_settings

_MODEL_NAME_RE = re.compile(r"^\s*-\s*model_name:\s*(.+?)\s*$")
_LITELLM_PARAMS_RE = re.compile(r"^\s*litellm_params:\s*$")
_MODEL_PARAM_RE = re.compile(r"^\s*model:\s*(.+?)\s*$")


@dataclass(frozen=True)
class LiteLLMAliasResolution:
    alias_to_provider: dict[str, str]
    sources: list[str]
    config_path: str | None = None
    proxy_reachable: bool = False


def find_litellm_config_path(*, start: Path | None = None) -> Path | None:
    """Locate `config/litellm.yaml` by walking up from *start* or this module."""
    roots: list[Path] = []
    if start is not None:
        roots.append(start.resolve())
    module = Path(__file__).resolve()
    roots.extend(module.parents)
    seen: set[Path] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        candidate = root / "config" / "litellm.yaml"
        if candidate.is_file():
            return candidate
    return None


def parse_litellm_yaml_alias_map(text: str) -> dict[str, str]:
    """Parse `model_list` entries from LiteLLM proxy config without a YAML dependency."""
    mapping: dict[str, str] = {}
    current_alias: str | None = None
    in_params = False
    for line in text.splitlines():
        name_match = _MODEL_NAME_RE.match(line)
        if name_match:
            current_alias = name_match.group(1).strip().strip("'\"")
            in_params = False
            continue
        if current_alias and _LITELLM_PARAMS_RE.match(line):
            in_params = True
            continue
        if current_alias and in_params:
            model_match = _MODEL_PARAM_RE.match(line)
            if model_match:
                mapping[current_alias] = model_match.group(1).strip().strip("'\"")
                in_params = False
            elif line.strip() and not line.startswith(" "):
                in_params = False
    return mapping


def load_alias_map_from_config(path: Path | str) -> dict[str, str]:
    config_path = Path(path)
    return parse_litellm_yaml_alias_map(config_path.read_text(encoding="utf-8"))


def _model_info_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}/model/info"


def load_alias_map_from_proxy(
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: float = 2.0,
) -> dict[str, str] | None:
    """Fetch alias → provider model from LiteLLM `GET /model/info`. Returns None if unreachable."""
    url = _model_info_url(base_url)
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
    return _alias_map_from_model_info_payload(payload)


def _alias_map_from_model_info_payload(payload: Any) -> dict[str, str]:
    rows: list[Any]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = [data]
        else:
            rows = []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    mapping: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        alias = str(row.get("model_name") or "").strip()
        params = row.get("litellm_params")
        if not alias or not isinstance(params, dict):
            continue
        provider = str(params.get("model") or "").strip()
        if provider:
            mapping[alias] = provider
    return mapping


def resolve_litellm_aliases(
    *,
    llm_settings: LLMSettings | None = None,
    config_path: Path | str | None = None,
    try_proxy: bool = True,
) -> LiteLLMAliasResolution:
    """Merge config-file and optional live proxy mappings (proxy wins on conflict)."""
    llm_settings = llm_settings or default_llm_settings
    merged: dict[str, str] = {}
    sources: list[str] = []
    resolved_config: Path | None = None

    if config_path is not None:
        resolved_config = Path(config_path)
    else:
        resolved_config = find_litellm_config_path()

    if resolved_config is not None and resolved_config.is_file():
        file_map = load_alias_map_from_config(resolved_config)
        merged.update(file_map)
        if file_map:
            sources.append(f"config:{resolved_config}")

    proxy_map: dict[str, str] | None = None
    if try_proxy:
        proxy_map = load_alias_map_from_proxy(
            base_url=llm_settings.base_url,
            api_key=llm_settings.api_key,
        )
    if proxy_map:
        merged.update(proxy_map)
        sources.append("litellm:/model/info")

    return LiteLLMAliasResolution(
        alias_to_provider=merged,
        sources=sources,
        config_path=str(resolved_config) if resolved_config else None,
        proxy_reachable=bool(proxy_map),
    )


def provider_model_for_alias(
    alias: str,
    resolution: LiteLLMAliasResolution,
    *,
    observed_response_models: set[str] | frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """
    Return (provider_model_display, resolution_note).

    Prefers config/proxy map; appends observed API `response.model` when it differs from alias.
    """
    alias = alias.strip()
    if not alias:
        return "—", ""
    configured = resolution.alias_to_provider.get(alias)
    if configured:
        note = "litellm config"
        if observed_response_models:
            extras = sorted(m for m in observed_response_models if m and m != alias and m != configured)
            if extras:
                note = f"{note}; API also reported: {', '.join(extras)}"
        return configured, note
    if observed_response_models:
        observed = sorted(observed_response_models)
        if len(observed) == 1:
            return observed[0], "completion response only (alias not in config)"
        return " / ".join(observed), "completion response only (alias not in config)"
    return "—", "alias not in litellm config"
