"""Build human-readable MODEL.md metadata for Law Proposition Extractor run and export directories."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from law_proposition_extractor_llm.settings import settings as llm_settings

from .cli_run_summary import build_cli_completion_summary
from .extraction_llm_metrics import (
    _cached_llm_result_successful,
    extraction_llm_call_traces_from_bundle,
    merge_extraction_observability_metrics,
)
from .extraction_progress import extraction_timing_metrics_from_bundle, format_duration
from .litellm_model_resolver import (
    LiteLLMAliasResolution,
    provider_model_for_alias,
    resolve_litellm_aliases,
)
from .run_persistence import PersistedRunConfig, load_persisted_run_config, resolve_run_directory
from .extraction_provider_failure import (
    assess_extraction_benchmark_completeness,
    extraction_abort_metadata_from_bundle,
)
from .run_quality import build_run_quality_summary
from .proposition_normalisation import PROPOSITION_NORMALISATION_VERSION
from .proposition_quality_gates import (
    load_normalisation_quality_payload,
    proposition_normalisation_quality_model_lines,
)

MODEL_MD_FILENAME = "MODEL.md"

# Indicative USD per 1M input tokens (operator ballpark; not billing truth).
_INDICATIVE_USD_PER_M_INPUT: dict[str, float] = {
    "frontier": 3.0,
    "local": 0.0,
    "heuristic": 0.0,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _is_safe_relative_display(rel: Path) -> bool:
    if rel == Path("."):
        return True
    parts = rel.parts
    if not parts or parts[0] == "..":
        return False
    risky_roots = {"private", "var", "Users", "tmp", "pytest-of"}
    if parts[0] in risky_roots or any(p in risky_roots for p in parts):
        return False
    return True


def _format_output_directory(
    output_dir: str | Path | None,
    *,
    anchor: Path | None = None,
) -> str:
    """Repo- or run-relative path for MODEL.md; omit absolute paths we cannot relativize."""
    if not output_dir:
        return ""
    raw = Path(output_dir).expanduser()
    if not raw.is_absolute():
        return raw.as_posix()
    path = raw.resolve()
    anchors: list[Path] = []
    if anchor is not None:
        anchors.append(Path(anchor).resolve())
    anchors.append(Path.cwd().resolve())
    for base in anchors:
        try:
            rel = path.relative_to(base)
            if not _is_safe_relative_display(rel):
                continue
            if rel == Path("."):
                return "."
            return rel.as_posix()
        except ValueError:
            continue
    return ""


def _trace_is_cached_for_tokens(trace: dict[str, Any]) -> bool:
    if trace.get("llm_cache_hit") is True or (
        trace.get("llm_call_attempted") is False and trace.get("llm_call_succeeded") is True
    ):
        return True
    return _cached_llm_result_successful(trace)


def _propositions_settings_label() -> str:
    return "Sources / bundled propositions"


def _proposition_normalisation_line(bundle: dict[str, Any]) -> str:
    pci = _as_dict(bundle.get("pipeline_case_inputs"))
    norm = pci.get("proposition_normalisation")
    if not isinstance(norm, dict):
        return (
            "**Proposition normalisation:** not recorded "
            f"(runs before v{PROPOSITION_NORMALISATION_VERSION} metadata may lack classification passes)"
        )
    enabled = norm.get("enabled") is not False
    version = str(norm.get("version") or PROPOSITION_NORMALISATION_VERSION)
    passes = norm.get("passes")
    pass_list = ", ".join(str(p) for p in passes) if isinstance(passes, list) and passes else "—"
    state = "enabled" if enabled else "disabled"
    return f"**Proposition normalisation:** v{version} ({state}; passes: {pass_list})"


def _proposition_normalisation_quality_lines(
    bundle: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> list[str]:
    payload = load_normalisation_quality_payload(bundle=bundle, export_dir=output_dir)
    return proposition_normalisation_quality_model_lines(payload)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _model_metadata_block(case_data: dict[str, Any]) -> dict[str, Any]:
    raw = case_data.get("model_metadata")
    return _as_dict(raw)


def _topic_block(case_data: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    topic = _as_dict(case_data.get("topic"))
    if not topic:
        topic = _as_dict(bundle.get("topic"))
    return topic


def _cluster_block(case_data: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    cluster = _as_dict(case_data.get("cluster"))
    if not cluster:
        clusters = bundle.get("clusters")
        if isinstance(clusters, list) and clusters and isinstance(clusters[0], dict):
            cluster = clusters[0]
    return cluster


def _resolve_description(case_data: dict[str, Any], bundle: dict[str, Any]) -> str:
    overrides = _model_metadata_block(case_data)
    if str(overrides.get("description") or "").strip():
        return str(overrides["description"]).strip()
    topic = _topic_block(case_data, bundle)
    if str(topic.get("name") or "").strip():
        return str(topic["name"]).strip()
    cluster = _cluster_block(case_data, bundle)
    if str(cluster.get("name") or "").strip():
        return str(cluster["name"]).strip()
    return "—"


def _resolve_input_pipeline(case_data: dict[str, Any]) -> str:
    overrides = _model_metadata_block(case_data)
    if str(overrides.get("input_pipeline") or "").strip():
        return str(overrides["input_pipeline"]).strip()
    law_discovery_ref = _as_dict(case_data.get("ada_intake_ref"))
    if law_discovery_ref:
        return "Law Discovery Law Proposition Extractor intake"
    if case_data.get("sources"):
        return "Law Proposition Extractor case file"
    return "—"


def _resolve_input_asset(case_data: dict[str, Any], bundle: dict[str, Any]) -> str:
    overrides = _model_metadata_block(case_data)
    if str(overrides.get("input_asset") or "").strip():
        return str(overrides["input_asset"]).strip()
    law_discovery_ref = _as_dict(case_data.get("ada_intake_ref"))
    category = str(law_discovery_ref.get("category_id") or "").strip()
    bundle_id = str(law_discovery_ref.get("bundle_id") or "").strip()
    if category and bundle_id:
        short_id = bundle_id[:8] + "…" if len(bundle_id) > 8 else bundle_id
        return f"{category} (`{short_id}`)"
    if category:
        return category
    cluster = _cluster_block(case_data, bundle)
    if str(cluster.get("name") or "").strip():
        return str(cluster["name"]).strip()
    return "—"


def _response_models_from_trace(trace: dict[str, Any]) -> set[str]:
    observed: set[str] = set()
    for key in ("response_model", "provider_model"):
        raw = trace.get(key)
        if isinstance(raw, str) and raw.strip():
            observed.add(raw.strip())
    return observed


def _collect_models_used(
    bundle: dict[str, Any],
    *,
    litellm_resolution: LiteLLMAliasResolution,
) -> list[dict[str, Any]]:
    """Distinct model aliases with stage role and live/cached call counts."""
    live_by_alias: dict[str, int] = {}
    cached_by_alias: dict[str, int] = {}
    roles: dict[str, set[str]] = {}
    response_models_by_alias: dict[str, set[str]] = {}

    for trace in extraction_llm_call_traces_from_bundle(bundle):
        alias = str(trace.get("model_alias") or "").strip()
        if not alias:
            continue
        response_models_by_alias.setdefault(alias, set()).update(_response_models_from_trace(trace))
        roles.setdefault(alias, set()).add("proposition extraction")
        if trace.get("llm_cache_hit") is True or (
            trace.get("llm_call_attempted") is False and trace.get("llm_call_succeeded") is True
        ):
            cached_by_alias[alias] = cached_by_alias.get(alias, 0) + 1
        elif trace.get("llm_call_attempted") is True or trace.get("llm_invoked") is True:
            live_by_alias[alias] = live_by_alias.get(alias, 0) + 1

    for tr in bundle.get("stage_traces") or []:
        if not isinstance(tr, dict):
            continue
        alias = str(tr.get("model_alias_used") or "").strip()
        if not alias:
            continue
        stage = str(tr.get("stage_name") or "pipeline stage").strip()
        roles.setdefault(alias, set()).add(stage)

    mode = str(
        _as_dict(_as_dict(bundle.get("pipeline_case_inputs")).get("extraction")).get("mode")
        or ""
    ).strip()
    if not roles and mode in {"frontier", "local"}:
        default_alias = (
            llm_settings.frontier_extract_model
            if mode == "frontier"
            else llm_settings.local_extract_model
        )
        roles[default_alias] = {"proposition extraction (configured, no trace rows)"}

    rows: list[dict[str, Any]] = []
    for alias in sorted(roles):
        observed = response_models_by_alias.get(alias, set())
        provider_model, provider_note = provider_model_for_alias(
            alias,
            litellm_resolution,
            observed_response_models=observed,
        )
        rows.append(
            {
                "alias": alias,
                "provider_model": provider_model,
                "provider_model_note": provider_note,
                "response_models_observed": sorted(observed),
                "roles": sorted(roles[alias]),
                "live_calls": live_by_alias.get(alias, 0),
                "cached_results": cached_by_alias.get(alias, 0),
            }
        )
    return rows


def _stage_runtime_rows(bundle: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    total_ms = 0
    for tr in bundle.get("stage_traces") or []:
        if not isinstance(tr, dict):
            continue
        name = str(tr.get("stage_name") or "unknown").strip()
        if name == "final export":
            continue
        ms = int(tr.get("duration_ms") or 0)
        total_ms += ms
        rows.append({"stage": name, "duration": format_duration(ms / 1000.0)})
    timing = extraction_timing_metrics_from_bundle(bundle)
    ext_secs = timing.get("extraction_elapsed_seconds")
    if isinstance(ext_secs, (int, float)) and ext_secs > 0:
        rows.append(
            {
                "stage": "proposition extraction (instrumented)",
                "duration": format_duration(float(ext_secs)),
            }
        )
    if total_ms > 0:
        rows.append({"stage": "Σ stage traces (excl. export)", "duration": format_duration(total_ms / 1000.0)})
    return rows


def _token_and_cost_estimates(
    bundle: dict[str, Any],
    *,
    extraction_mode: str,
) -> dict[str, Any]:
    traces = extraction_llm_call_traces_from_bundle(bundle)
    input_tokens = sum(int(t.get("estimated_input_tokens") or 0) for t in traces)
    live_tokens = sum(
        int(t.get("estimated_input_tokens") or 0)
        for t in traces
        if t.get("llm_call_attempted") is True or t.get("llm_invoked") is True
    )
    cached_tokens = sum(
        int(t.get("estimated_input_tokens") or 0)
        for t in traces
        if _trace_is_cached_for_tokens(t)
    )
    output_traces = [
        t
        for t in traces
        if isinstance(t.get("estimated_output_tokens"), int) and int(t["estimated_output_tokens"]) >= 0
    ]
    output_tokens = (
        sum(int(t["estimated_output_tokens"]) for t in output_traces) if output_traces else None
    )
    rate = _INDICATIVE_USD_PER_M_INPUT.get(extraction_mode, _INDICATIVE_USD_PER_M_INPUT["frontier"])
    usd_indicative = round(live_tokens * rate / 1_000_000, 2) if live_tokens and rate else None
    if extraction_mode == "heuristic":
        pricing_note = "No USD estimate for heuristic runs."
    else:
        rate_clause = (
            f"${rate}/1M input-token price ({extraction_mode} mode)"
            if rate
            else "configured input-token price"
        )
        pricing_note = (
            f"Indicative only: live-call input tokens × {rate_clause}. "
            "This is not a total run cost unless output-token and cache-billing data are also included."
        )
    result: dict[str, Any] = {
        "estimated_input_tokens_total": input_tokens,
        "estimated_input_tokens_live_only": live_tokens,
        "estimated_input_tokens_cached_only": cached_tokens,
        "indicative_usd": usd_indicative,
        "pricing_note": pricing_note,
        "has_output_token_data": output_tokens is not None,
    }
    if output_tokens is not None:
        result["estimated_output_tokens"] = output_tokens
    return result


def _additional_cost_estimates(case_data: dict[str, Any]) -> dict[str, Any]:
    overrides = _model_metadata_block(case_data)
    raw = overrides.get("additional_cost_estimates")
    if isinstance(raw, dict):
        return raw
    return {}


def _operator_notes(case_data: dict[str, Any]) -> str:
    overrides = _model_metadata_block(case_data)
    notes = overrides.get("notes")
    if isinstance(notes, str) and notes.strip():
        return notes.strip()
    if isinstance(notes, list):
        return "\n".join(str(n).strip() for n in notes if str(n).strip())
    return ""


def _settings_lines(
    *,
    case_data: dict[str, Any],
    bundle: dict[str, Any],
    run_config: PersistedRunConfig | None,
    summary: dict[str, Any],
    quality: dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    judit_run = _as_dict(case_data.get("judit_run"))
    ext_mode = str(
        summary.get("extraction_mode_effective")
        or summary.get("extraction_mode")
        or judit_run.get("extraction_mode_effective")
        or "unknown"
    )
    ext_requested = str(
        summary.get("extraction_mode_requested")
        or judit_run.get("extraction_mode_requested")
        or ext_mode
    )
    lines.append(f"**Extraction mode:** `{ext_mode}` (requested `{ext_requested}`)")
    fallback = (
        run_config.extraction_fallback
        if run_config
        else str(_as_dict(case_data.get("extraction")).get("fallback_policy") or "—")
    )
    lines.append(f"**Fallback policy:** `{fallback}`")
    if run_config and run_config.divergence_reasoning:
        lines.append(f"**Divergence reasoning:** `{run_config.divergence_reasoning}`")
    if run_config and run_config.extraction_execution_mode:
        lines.append(f"**Extraction execution:** `{run_config.extraction_execution_mode}`")
    src_sections = run_config.source_sections if run_config else _as_dict(judit_run.get("source_sections"))
    if src_sections:
        parts = []
        if src_sections.get("principal_only") is True:
            parts.append("principal only")
        if src_sections.get("include_amendments"):
            parts.append("amendments")
        if src_sections.get("include_revocations"):
            parts.append("revocations")
        if src_sections.get("max_sources") is not None:
            parts.append(f"max_sources={src_sections['max_sources']}")
        if parts:
            lines.append(f"**Source selection:** {', '.join(parts)}")
    lines.append(
        f"**{_propositions_settings_label()}:** "
        f"{summary.get('sources', 0)} / {summary.get('propositions', 0)}"
    )
    if summary.get("live_llm_calls_attempted") is not None:
        lines.append(
            f"**LLM calls (live / cached ok / fallbacks):** "
            f"{summary.get('live_llm_calls_attempted', 0)} / "
            f"{summary.get('cached_llm_results_successful', 0)} / "
            f"{summary.get('fallback_count', 0)}"
        )
    lines.append(
        f"**Run quality:** {quality.get('status', 'unknown')} "
        f"({quality.get('warning_count', 0)} warnings)"
    )
    pci = _as_dict(bundle.get("pipeline_case_inputs"))
    if pci.get("pipeline_version"):
        lines.append(f"**Pipeline version:** `{pci['pipeline_version']}`")
    lines.append(_proposition_normalisation_line(bundle))
    prompts = _as_dict(pci.get("prompts"))
    if prompts:
        lines.append(f"**Prompt overrides:** {', '.join(sorted(prompts))}")
    return lines


def load_case_data_for_run(run_path: str | Path | None, bundle: dict[str, Any]) -> dict[str, Any]:
    """Prefer case.json beside a persisted run; fall back to bundle topic-only context."""
    if run_path is not None:
        case_json = resolve_run_directory(run_path) / "case.json"
        if case_json.is_file():
            payload = json.loads(case_json.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    return {}


def build_run_model_metadata(
    *,
    bundle: dict[str, Any],
    case_data: dict[str, Any] | None = None,
    run_config: PersistedRunConfig | None = None,
    output_dir: str | Path | None = None,
    output_path_anchor: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    case_data = case_data or {}
    if run_config is None:
        run_config = load_persisted_run_config(case_data)
    quality = bundle.get("run_quality_summary")
    if not isinstance(quality, dict):
        quality = build_run_quality_summary(bundle)
    summary = build_cli_completion_summary(
        bundle,
        quality_summary=quality,
        output_dir=str(output_dir) if output_dir else None,
    )
    extraction_mode = str(
        summary.get("extraction_mode_effective") or summary.get("extraction_mode") or "unknown"
    )
    run = _as_dict(bundle.get("run"))
    jobs = [
        row for row in (bundle.get("proposition_extraction_jobs") or []) if isinstance(row, dict)
    ]
    llm_traces = extraction_llm_call_traces_from_bundle(bundle)
    observability = merge_extraction_observability_metrics(jobs=jobs, llm_traces=llm_traces)
    litellm_resolution = resolve_litellm_aliases(
        try_proxy=extraction_mode in {"local", "frontier"},
    )

    norm_quality = load_normalisation_quality_payload(
        bundle=bundle,
        export_dir=output_dir,
    )

    extraction_abort = extraction_abort_metadata_from_bundle(bundle)
    extraction_completeness = assess_extraction_benchmark_completeness(bundle)

    return {
        "schema_version": "1",
        "generated_at": generated_at or _utc_now_iso(),
        "extraction_abort": extraction_abort,
        "extraction_completeness": extraction_completeness,
        "description": _resolve_description(case_data, bundle),
        "input_pipeline": _resolve_input_pipeline(case_data),
        "input_asset": _resolve_input_asset(case_data, bundle),
        "run_id": str(run.get("id") or ""),
        "workflow_mode": str(bundle.get("workflow_mode") or run.get("workflow_mode") or ""),
        "completed_at": (run_config.completed_at if run_config else "") or str(
            _as_dict(case_data.get("judit_run")).get("completed_at") or ""
        ),
        "output_directory": _format_output_directory(output_dir, anchor=output_path_anchor),
        "run_quality": {
            "status": str(quality.get("status") or "unknown"),
            "warning_count": int(quality.get("warning_count") or 0),
        },
        "litellm_resolution": {
            "sources": litellm_resolution.sources,
            "config_path": litellm_resolution.config_path,
            "proxy_reachable": litellm_resolution.proxy_reachable,
        },
        "models_used": _collect_models_used(bundle, litellm_resolution=litellm_resolution),
        "runtime": {
            "stages": _stage_runtime_rows(bundle),
            "extraction_timing": extraction_timing_metrics_from_bundle(bundle),
        },
        "approx_cost": _token_and_cost_estimates(bundle, extraction_mode=extraction_mode),
        "additional_cost_estimates": _additional_cost_estimates(case_data),
        "settings_summary": summary,
        "observability": observability,
        "operator_notes": _operator_notes(case_data),
        "settings_lines": _settings_lines(
            case_data=case_data,
            bundle=bundle,
            run_config=run_config,
            summary=summary,
            quality=quality,
        ),
        "pipeline_case_inputs": _as_dict(bundle.get("pipeline_case_inputs")),
        "proposition_normalisation_line": _proposition_normalisation_line(bundle),
        "proposition_normalisation_quality": norm_quality,
        "proposition_normalisation_quality_lines": _proposition_normalisation_quality_lines(
            bundle,
            output_dir=output_dir,
        ),
    }


def render_model_md(metadata: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Model & run metadata",
        "",
        "Human-readable summary of how this Law Proposition Extractor run was produced.",
        f"Generated **{metadata.get('generated_at', '—')}**.",
    ]
    quality = _as_dict(metadata.get("run_quality"))
    if quality:
        lines.extend(
            [
                "",
                f"> **Run quality:** {quality.get('status', 'unknown')} — "
                f"{int(quality.get('warning_count') or 0)} warnings.",
            ]
        )
    extraction_abort = _as_dict(metadata.get("extraction_abort"))
    extraction_completeness = _as_dict(metadata.get("extraction_completeness"))
    if extraction_abort.get("aborted") or extraction_completeness.get("incomplete"):
        lines.extend(
            [
                "",
                "> **Extraction aborted / export incomplete — not benchmarkable.**",
            ]
        )
        if extraction_abort.get("failure_reason"):
            lines.append(f"> Failure reason: `{extraction_abort['failure_reason']}`.")
        if extraction_abort.get("last_provider_error_message"):
            excerpt = str(extraction_abort["last_provider_error_message"])[:280]
            lines.append(f"> Last provider error: {excerpt}")
        if extraction_completeness.get("sources_with_zero_propositions"):
            zero = extraction_completeness["sources_with_zero_propositions"]
            lines.append(f"> Sources with zero propositions: `{zero}`.")
    lines.extend(
        [
            "",
            "## Run identity",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| **Description** | {metadata.get('description', '—')} |",
            f"| **Input pipeline** | {metadata.get('input_pipeline', '—')} |",
            f"| **Input asset** | {metadata.get('input_asset', '—')} |",
        ]
    )
    if metadata.get("run_id"):
        lines.append(f"| **Run ID** | `{metadata['run_id']}` |")
    if metadata.get("workflow_mode"):
        lines.append(f"| **Workflow** | `{metadata['workflow_mode']}` |")
    if metadata.get("completed_at"):
        lines.append(f"| **Completed** | {metadata['completed_at']} |")
    if metadata.get("output_directory"):
        lines.append(f"| **Output directory** | `{metadata['output_directory']}` |")
    lines.extend(["", "## Models used", ""])
    resolution = _as_dict(metadata.get("litellm_resolution"))
    if resolution.get("sources"):
        src = ", ".join(str(s) for s in resolution["sources"])
        lines.append(f"_Provider models resolved from: {src}._")
        lines.append("")
    models = metadata.get("models_used")
    if isinstance(models, list) and models:
        lines.extend(
            [
                "| Role(s) | LiteLLM alias | Provider model | Live | Cached |",
                "| --- | --- | --- | ---: | ---: |",
            ]
        )
        for row in models:
            if not isinstance(row, dict):
                continue
            roles = ", ".join(row.get("roles") or [])
            provider = str(row.get("provider_model") or "—")
            lines.append(
                f"| {roles} | `{row.get('alias', '—')}` | `{provider}` | "
                f"{row.get('live_calls', 0)} | {row.get('cached_results', 0)} |"
            )
    else:
        lines.append("_No model aliases recorded (heuristic run or traces not retained)._")
    lines.extend(["", "## Runtime", ""])
    runtime = _as_dict(metadata.get("runtime"))
    stages = runtime.get("stages")
    if isinstance(stages, list) and stages:
        lines.extend(["| Phase | Duration |", "| --- | --- |"])
        for row in stages:
            if isinstance(row, dict):
                lines.append(f"| {row.get('stage', '—')} | {row.get('duration', '—')} |")
    else:
        lines.append("_No stage timing available._")
    lines.extend(["", "## Indicative cost estimate", ""])
    cost = _as_dict(metadata.get("approx_cost"))
    lines.extend(
        [
            "| Measure | Value |",
            "| --- | --- |",
            f"| Estimated input tokens (all traces) | {cost.get('estimated_input_tokens_total', 0):,} |",
            f"| Estimated input tokens (live calls only) | {cost.get('estimated_input_tokens_live_only', 0):,} |",
        ]
    )
    cached_only = int(cost.get("estimated_input_tokens_cached_only") or 0)
    if cached_only > 0:
        lines.append(f"| Estimated input tokens (cached calls only) | {cached_only:,} |")
    if cost.get("has_output_token_data"):
        lines.append(
            f"| Estimated output tokens | {int(cost.get('estimated_output_tokens') or 0):,} |"
        )
    usd = cost.get("indicative_usd")
    if usd is not None:
        lines.append(f"| Lower-bound indicative USD (live input tokens only) | ~${usd:.2f} |")
    elif cost.get("pricing_note") and "heuristic" not in str(cost.get("pricing_note") or "").lower():
        lines.append("| Lower-bound indicative USD | — |")
    if cost.get("pricing_note"):
        lines.append("")
        lines.append(f"_{cost['pricing_note']}_")
    lines.extend(["", "## Additional cost estimates", ""])
    extra = _as_dict(metadata.get("additional_cost_estimates"))
    if extra:
        lines.extend(["| Key | Value |", "| --- | --- |"])
        for key, value in sorted(extra.items()):
            display = "—" if value is None else str(value)
            lines.append(f"| {key} | {display} |")
    else:
        lines.append(
            "_Not estimated. Add `model_metadata.additional_cost_estimates` in case.json "
            "(e.g. `co2_kg`, `water_litres`) to record CO₂, water, or other impacts._"
        )
    lines.extend(["", "## Settings & notes", ""])
    for setting_line in metadata.get("settings_lines") or []:
        lines.append(f"- {setting_line}")
    notes = str(metadata.get("operator_notes") or "").strip()
    lines.extend(["", "### Operator notes", ""])
    if notes:
        lines.append(notes)
    else:
        lines.append(
            "_None. Set `model_metadata.notes` in case.json for free-text about prompts, "
            "ablations, or why this run is interesting._"
        )
    norm_raw = str(metadata.get("proposition_normalisation_line") or "").strip()
    lines.extend(
        [
            "",
            "### Proposition normalisation",
            "",
            "Deterministic passes after extraction (tier, legal effect, territory, labels, relationship keys). "
            "Full reference: docs/architecture/proposition-classification.md.",
            "",
        ]
    )
    if norm_raw:
        lines.append(f"- {norm_raw}")
    else:
        lines.append("- _Not recorded (export predates normalisation metadata)._")
    lines.append(
        "- Bundle field: `pipeline_case_inputs.proposition_normalisation` "
        "(`version`, `enabled`, `passes`). Optional case.json note: `model_metadata.proposition_normalisation`."
    )
    lines.append("")
    for quality_line in metadata.get("proposition_normalisation_quality_lines") or []:
        if quality_line.endswith(":"):
            lines.append(f"**{quality_line}**")
        elif quality_line.startswith("- "):
            lines.append(quality_line)
        else:
            lines.append(f"_{quality_line}_")
    lines.extend(
        [
            "",
            "_Interpretation:_ warnings do not necessarily invalidate a run. "
            "Errors mean the export should not be used for downstream comparison without review. "
            "Legacy `categories` conflicts are expected during migration but should trend down over time. "
            "Full detail: `normalisation_quality.json`, `NORMALISATION_QUALITY.md`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_model_md(
    path: str | Path,
    *,
    bundle: dict[str, Any],
    case_data: dict[str, Any] | None = None,
    run_config: PersistedRunConfig | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    target = Path(path)
    anchor = target.parent.resolve()
    metadata = build_run_model_metadata(
        bundle=bundle,
        case_data=case_data,
        run_config=run_config,
        output_dir=output_dir or anchor,
        output_path_anchor=anchor,
    )
    target.write_text(render_model_md(metadata), encoding="utf-8")
    return target


def attach_run_model_metadata(
    bundle: dict[str, Any],
    *,
    case_data: dict[str, Any] | None = None,
    run_config: PersistedRunConfig | None = None,
    output_dir: str | Path | None = None,
    output_path_anchor: Path | None = None,
) -> dict[str, Any]:
    anchor = output_path_anchor
    if anchor is None and output_dir is not None:
        anchor = Path(output_dir).resolve()
    metadata = build_run_model_metadata(
        bundle=bundle,
        case_data=case_data,
        run_config=run_config,
        output_dir=output_dir,
        output_path_anchor=anchor,
    )
    bundle["run_model_metadata"] = metadata
    return metadata
