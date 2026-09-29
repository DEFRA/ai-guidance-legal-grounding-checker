"""Human-readable MODEL.md metadata for Law Discovery run output directories."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_discovery import __version__ as ada_version
from law_discovery.models import (
    CandidateSource,
    DiscoveryRun,
    RelatedSourceExpansionRun,
    SourceBundle,
    SourceRegister,
)
from law_discovery.progress import format_duration

MODEL_MD_FILENAME = "MODEL.md"

RunKind = Literal[
    "discovery",
    "source-register",
    "related-source-expansion",
    "source-bundle",
    "law-proposition-extractor-selected-sources",
    "law-proposition-extractor-source-bundle-export",
]

# Indicative USD per 1M input tokens (operator ballpark; not billing truth).
_INDICATIVE_USD_PER_M_INPUT: dict[str, float] = {
    "frontier": 3.0,
    "default": 3.0,
}

_DESCRIPTION_MAX_LEN = 280


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_safe_relative_display(rel: Path) -> bool:
    if rel == Path("."):
        return True
    parts = rel.parts
    if not parts or parts[0] == "..":
        return False
    risky_roots = {"private", "var", "Users", "tmp", "pytest-of"}
    return parts[0] not in risky_roots and not any(p in risky_roots for p in parts)


def _format_relative_path(
    path: str | Path | None,
    *,
    anchor: Path | None = None,
) -> str:
    if not path:
        return ""
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        return raw.as_posix()
    resolved = raw.resolve()
    anchors: list[Path] = []
    if anchor is not None:
        anchors.append(Path(anchor).resolve())
    anchors.append(Path.cwd().resolve())
    for base in anchors:
        try:
            rel = resolved.relative_to(base)
            if _is_safe_relative_display(rel):
                return "." if rel == Path(".") else rel.as_posix()
        except ValueError:
            continue
    return ""


def _excerpt(text: str, *, max_len: int = _DESCRIPTION_MAX_LEN) -> str:
    stripped = text.strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 1].rstrip() + "…"


def _run_status_line(*, warnings: list[str], metadata: dict[str, Any]) -> str:
    warning_count = len(warnings)
    if metadata.get("ai_triage_failed") is True:
        return f"> **Run status:** completed with warnings — {warning_count} warnings."
    if metadata.get("partial_results") is True or metadata.get("ai_triage_partial") is True:
        n = warning_count or 1
        return f"> **Run status:** completed with warnings — {n} warnings."
    if warning_count:
        return f"> **Run status:** completed with warnings — {warning_count} warnings."
    return "> **Run status:** completed"


def _llm_usage_block(metadata: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(metadata.get("llm_usage"))


def _collect_models_used(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    usage = _llm_usage_block(metadata)
    models = usage.get("models")
    if isinstance(models, list) and models:
        rows: list[dict[str, Any]] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "roles": item.get("roles") or ([item["role"]] if item.get("role") else []),
                    "alias": str(item.get("alias") or item.get("model_alias") or "").strip(),
                    "provider_model": str(item.get("provider_model") or "").strip(),
                    "live_calls": int(item.get("live_calls") or 0),
                    "cached_calls": int(
                        item.get("cached_calls") or item.get("cached_results") or 0
                    ),
                    "failed_calls": int(item.get("failed_calls") or 0),
                }
            )
        return [r for r in rows if r["alias"] or r["provider_model"]]

    rows = []
    alias = str(metadata.get("ai_triage_model") or "").strip()
    if alias:
        live = int(metadata.get("ai_triage_successful_batch_count") or 0)
        failed = int(metadata.get("ai_triage_failed_batch_count") or 0)
        rows.append(
            {
                "roles": ["candidate triage"],
                "alias": alias,
                "provider_model": str(metadata.get("ai_triage_provider_model") or "").strip(),
                "live_calls": live,
                "cached_calls": 0,
                "failed_calls": failed,
            }
        )
    return rows


def _phase_duration_rows(metadata: dict[str, Any]) -> list[dict[str, str]]:
    usage = _llm_usage_block(metadata)
    phases = usage.get("phase_durations_seconds")
    if not isinstance(phases, dict):
        return []
    rows: list[dict[str, str]] = []
    for name, seconds in phases.items():
        if isinstance(seconds, (int, float)) and seconds > 0:
            rows.append({"phase": str(name), "duration": format_duration(float(seconds))})
    return rows


def _token_and_cost_estimates(metadata: dict[str, Any]) -> dict[str, Any]:
    usage = _llm_usage_block(metadata)
    input_total = usage.get("estimated_input_tokens_total")
    live_only = usage.get("estimated_input_tokens_live_only")
    cached_only = usage.get("estimated_input_tokens_cached_only")
    output_tokens = usage.get("estimated_output_tokens")
    pricing_tier = str(usage.get("pricing_tier") or "default").strip() or "default"
    rate = _INDICATIVE_USD_PER_M_INPUT.get(pricing_tier, _INDICATIVE_USD_PER_M_INPUT["default"])

    if input_total is None and live_only is None:
        return {"has_data": False}

    total = int(input_total or 0)
    live = int(live_only if live_only is not None else total)
    cached = int(cached_only or 0)
    has_output = isinstance(output_tokens, int) and output_tokens >= 0
    usd = round(live * rate / 1_000_000, 2) if live and rate else None
    pricing_note = (
        f"Indicative only: live-call input tokens × ${rate}/1M input-token price. "
        "This is not a total run cost unless output-token and cache-billing data are also included."
    )
    result: dict[str, Any] = {
        "has_data": True,
        "estimated_input_tokens_total": total,
        "estimated_input_tokens_live_only": live,
        "estimated_input_tokens_cached_only": cached,
        "indicative_usd": usd,
        "pricing_note": pricing_note,
        "has_output_token_data": has_output,
    }
    if has_output:
        result["estimated_output_tokens"] = int(output_tokens)
    return result


def _count_high_confidence(sources: list[CandidateSource]) -> int:
    return sum(1 for s in sources if s.confidence == "high")


def _table_row(label: str, value: str) -> str:
    safe = value.replace("|", "\\|") if value else "—"
    return f"| **{label}** | {safe} |"


def build_discovery_model_metadata(
    run: DiscoveryRun,
    *,
    output_path: Path | None = None,
    input_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    meta = _as_dict(run.metadata)
    category = run.category
    anchor = output_path.parent.resolve() if output_path else None
    return {
        "run_kind": "discovery",
        "generated_at": generated_at or _utc_now_iso(),
        "run_status": _run_status_line(warnings=run.warnings, metadata=meta),
        "run_id": run.run_id,
        "completed_at": run.created_at.isoformat().replace("+00:00", "Z"),
        "category_id": category.category_id,
        "category_title": category.label,
        "category_description": _excerpt(category.description),
        "jurisdiction_hints": category.jurisdiction_hints,
        "exclusions": category.exclusions,
        "output_directory": _format_relative_path(
            output_path.parent if output_path else None,
            anchor=anchor,
        ),
        "output_file": _format_relative_path(output_path.name if output_path else None),
        "input_path": _format_relative_path(input_path, anchor=anchor),
        "input_hash": str(meta.get("input_hash") or "").strip(),
        "ada_version": ada_version,
        "models_used": _collect_models_used(meta),
        "runtime_phases": _phase_duration_rows(meta),
        "approx_cost": _token_and_cost_estimates(meta),
        "results": {
            "queries_generated": len(run.query_plan),
            "candidates_found": int(
                meta.get("raw_candidate_count") or len(run.candidate_sources)
            ),
            "candidates_after_deduplication": int(
                meta.get("candidate_count") or len(run.candidate_sources)
            ),
            "high_confidence_candidates": _count_high_confidence(run.candidate_sources),
            "successful_queries": meta.get("successful_query_count"),
            "failed_queries": meta.get("failed_query_count"),
        },
        "settings": _discovery_settings_lines(meta, category_metadata=category.metadata),
        "operator_notes": _operator_notes(category.metadata, meta),
        "warnings": run.warnings,
    }


def _discovery_settings_lines(
    meta: dict[str, Any],
    *,
    category_metadata: dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    if meta.get("use_network") is not None:
        lines.append(f"**Network discovery:** {'enabled' if meta['use_network'] else 'disabled'}")
    if meta.get("use_ai_triage") is not None:
        lines.append(f"**AI triage:** {'enabled' if meta['use_ai_triage'] else 'disabled'}")
    if meta.get("use_ai_assessment") is not None:
        enabled = "enabled" if meta["use_ai_assessment"] else "disabled"
        lines.append(f"**AI per-candidate assessment:** {enabled}")
    if meta.get("ai_triage_batch_size"):
        lines.append(f"**AI triage batch size:** {meta['ai_triage_batch_size']}")
    if meta.get("apply_ai_review_status") is not None:
        lines.append(
            f"**Apply AI review status:** {'yes' if meta['apply_ai_review_status'] else 'no'}"
        )
    profile = category_metadata.get("discovery_profile")
    if profile:
        lines.append(f"**Discovery profile:** `{profile}`")
    guidance = category_metadata.get("triage_guidance")
    if isinstance(guidance, str) and guidance.strip():
        lines.append("**Category triage guidance:** present")
    return lines


def build_related_expansion_model_metadata(
    run: RelatedSourceExpansionRun,
    *,
    category_label: str | None = None,
    category_description: str | None = None,
    jurisdiction_hints: list[str] | None = None,
    output_path: Path | None = None,
    input_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    meta = _as_dict(run.metadata)
    anchor = output_path.parent.resolve() if output_path else None
    review_related = _as_dict(meta.get("related_source_review_counts"))
    review_relationship = _as_dict(meta.get("relationship_review_counts"))
    return {
        "run_kind": "related-source-expansion",
        "generated_at": generated_at or _utc_now_iso(),
        "run_status": _run_status_line(warnings=run.warnings, metadata=meta),
        "run_id": run.run_id,
        "completed_at": run.created_at.isoformat().replace("+00:00", "Z"),
        "category_id": run.category_id,
        "category_title": category_label or run.category_id,
        "category_description": _excerpt(category_description or ""),
        "jurisdiction_hints": jurisdiction_hints or [],
        "output_directory": _format_relative_path(
            output_path.parent if output_path else None,
            anchor=anchor,
        ),
        "output_file": _format_relative_path(output_path.name if output_path else None),
        "input_path": _format_relative_path(input_path, anchor=anchor),
        "input_hash": str(meta.get("input_hash") or "").strip(),
        "ada_version": ada_version,
        "models_used": _collect_models_used(meta),
        "runtime_phases": _phase_duration_rows(meta),
        "approx_cost": _token_and_cost_estimates(meta),
        "results": {
            "queries_generated": meta.get("query_count"),
            "seed_sources": meta.get("seed_source_count") or len(run.seed_sources),
            "raw_candidates_found": meta.get("raw_candidate_count"),
            "related_sources": meta.get("related_source_count") or len(run.related_sources),
            "relationships_found": meta.get("relationship_count") or len(run.relationships),
            "orphan_related_sources": meta.get("orphan_related_source_count"),
            "related_sources_accepted": review_related.get("accepted"),
            "related_sources_rejected": review_related.get("rejected"),
            "related_sources_needs_review": review_related.get("needs_more_research"),
            "relationships_accepted": review_relationship.get("accepted"),
            "relationships_rejected": review_relationship.get("rejected"),
            "relationships_needs_review": review_relationship.get("needs_more_research"),
            "successful_queries": meta.get("successful_query_count"),
            "failed_queries": meta.get("failed_query_count"),
        },
        "settings": _related_settings_lines(meta),
        "operator_notes": _operator_notes({}, meta),
        "warnings": run.warnings,
    }


def _related_settings_lines(meta: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if meta.get("expansion_profile"):
        lines.append(f"**Expansion profile:** `{meta['expansion_profile']}`")
    if meta.get("seed_source_type"):
        lines.append(f"**Seed source selection:** `{meta['seed_source_type']}`")
    if meta.get("max_seed_sources") is not None:
        lines.append(f"**Max seed sources:** {meta['max_seed_sources']}")
    if meta.get("use_network") is not None:
        lines.append(f"**Network expansion:** {'enabled' if meta['use_network'] else 'disabled'}")
    if meta.get("use_ai_triage") is not None:
        triage = "enabled" if meta["use_ai_triage"] else "disabled"
        lines.append(f"**AI relationship triage:** {triage}")
    return lines


def build_source_register_model_metadata(
    register: SourceRegister,
    *,
    category_label: str | None = None,
    run_kind: RunKind = "source-register",
    output_path: Path | None = None,
    input_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    meta = _as_dict(register.metadata)
    anchor = output_path.parent.resolve() if output_path else None
    return {
        "run_kind": run_kind,
        "generated_at": generated_at or _utc_now_iso(),
        "run_status": _run_status_line(warnings=[], metadata=meta),
        "run_id": register.register_id,
        "completed_at": register.created_at.isoformat().replace("+00:00", "Z"),
        "category_id": register.category_id,
        "category_title": category_label or register.category_id,
        "output_directory": _format_relative_path(
            output_path.parent if output_path else None,
            anchor=anchor,
        ),
        "output_file": _format_relative_path(output_path.name if output_path else None),
        "input_path": _format_relative_path(input_path, anchor=anchor),
        "ada_version": ada_version,
        "models_used": _collect_models_used(meta),
        "runtime_phases": _phase_duration_rows(meta),
        "approx_cost": _token_and_cost_estimates(meta),
        "results": {
            "accepted_sources": len(register.accepted_sources),
            "rejected_sources": len(register.rejected_sources),
            "parked_sources": len(register.parked_sources),
            "principal_sources": sum(
                1
                for s in register.accepted_sources
                if s.relationship_to_category
                in {"directly_regulates", "defines_terms", "operationalises"}
            ),
        },
        "settings": [f"**Export target:** `{register.export_target}`"],
        "operator_notes": _operator_notes({}, meta),
        "warnings": [],
    }


def build_source_bundle_model_metadata(
    bundle: SourceBundle,
    *,
    category_label: str | None = None,
    run_kind: RunKind = "source-bundle",
    output_path: Path | None = None,
    input_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    meta = _as_dict(bundle.metadata)
    intake = _as_dict(meta.get("intake"))
    anchor = output_path.parent.resolve() if output_path else None
    return {
        "run_kind": run_kind,
        "generated_at": generated_at or _utc_now_iso(),
        "run_status": _run_status_line(warnings=[], metadata=meta),
        "run_id": bundle.bundle_id,
        "completed_at": bundle.created_at.isoformat().replace("+00:00", "Z"),
        "category_id": bundle.category_id,
        "category_title": category_label or bundle.category_id,
        "output_directory": _format_relative_path(
            output_path.parent if output_path else None,
            anchor=anchor,
        ),
        "output_file": _format_relative_path(output_path.name if output_path else None),
        "input_path": _format_relative_path(input_path, anchor=anchor),
        "ada_version": ada_version,
        "models_used": _collect_models_used(meta),
        "runtime_phases": _phase_duration_rows(meta),
        "approx_cost": _token_and_cost_estimates(meta),
        "results": {
            "principal_sources": len(bundle.principal_sources),
            "amending_sources": len(bundle.amending_sources),
            "commencement_sources": len(bundle.commencement_sources),
            "correction_sources": len(bundle.correction_sources),
            "revocation_sources": len(bundle.revocation_sources),
            "interpretive_sources": len(bundle.interpretive_sources),
            "guidance_sources": len(bundle.guidance_sources),
            "form_sources": len(bundle.form_sources),
            "contextual_sources": len(bundle.contextual_sources),
            "rejected_sources": len(bundle.rejected_sources),
            "relationships": len(bundle.relationships),
            "intake_kind": intake.get("kind"),
        },
        "settings": _bundle_settings_lines(meta, intake),
        "operator_notes": _operator_notes({}, meta),
        "warnings": [],
    }


def _bundle_settings_lines(meta: dict[str, Any], intake: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if intake.get("kind"):
        lines.append(f"**Bundle kind:** `{intake['kind']}`")
    policy = _as_dict(intake.get("filter_policy"))
    if policy.get("principal_only") is True:
        lines.append("**Source selection:** principal only")
    if policy.get("exclude_jurisdictions"):
        lines.append(f"**Jurisdiction exclusions:** {policy['exclude_jurisdictions']}")
    if policy.get("max_principal_sources") is not None:
        lines.append(f"**Max principal sources:** {policy['max_principal_sources']}")
    if meta.get("source_register_id"):
        lines.append(f"**Source register ID:** `{meta['source_register_id']}`")
    if meta.get("related_run_id"):
        lines.append(f"**Related expansion run ID:** `{meta['related_run_id']}`")
    return lines


def _operator_notes(category_metadata: dict[str, Any], run_metadata: dict[str, Any]) -> str:
    for source in (run_metadata, category_metadata):
        notes = source.get("notes")
        if isinstance(notes, str) and notes.strip():
            return notes.strip()
    conversion = category_metadata.get("conversion_note")
    if isinstance(conversion, str) and conversion.strip():
        return conversion.strip()
    return ""


def render_model_md(metadata: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Model & run metadata",
        "",
        "Human-readable summary of how this Law Discovery run was produced.",
        f"Generated **{metadata.get('generated_at', '—')}**.",
        "",
        str(metadata.get("run_status") or "> **Run status:** completed"),
        "",
        "## Run identity",
        "",
        "| Field | Value |",
        "| --- | --- |",
        _table_row("Run type", str(metadata.get("run_kind") or "—")),
        _table_row("Category ID", str(metadata.get("category_id") or "—")),
        _table_row("Category title", str(metadata.get("category_title") or "—")),
    ]
    if metadata.get("run_id"):
        lines.append(_table_row("Run ID", f"`{metadata['run_id']}`"))
    if metadata.get("completed_at"):
        lines.append(_table_row("Completed", str(metadata["completed_at"])))
    if metadata.get("output_directory"):
        lines.append(_table_row("Output directory", f"`{metadata['output_directory']}`"))
    if metadata.get("output_file"):
        lines.append(_table_row("Output file", f"`{metadata['output_file']}`"))
    lines.append(_table_row("Law Discovery version", f"`{metadata.get('ada_version', '—')}`"))

    lines.extend(["", "## Category / input", ""])
    if metadata.get("category_description"):
        lines.append(metadata["category_description"])
        lines.append("")
    jurisdiction = metadata.get("jurisdiction_hints")
    if isinstance(jurisdiction, list) and jurisdiction:
        lines.append(f"**Jurisdiction hints:** {', '.join(str(j) for j in jurisdiction)}")
    if metadata.get("input_path"):
        lines.append(f"**Input path:** `{metadata['input_path']}`")
    if metadata.get("input_hash"):
        lines.append(f"**Input hash:** `{metadata['input_hash']}`")

    lines.extend(["", "## Models used", ""])
    models = metadata.get("models_used")
    if isinstance(models, list) and models:
        lines.extend(
            [
                "| Role(s) | Model alias | Provider model | Live | Cached | Failed |",
                "| --- | --- | --- | ---: | ---: | ---: |",
            ]
        )
        for row in models:
            if not isinstance(row, dict):
                continue
            roles = ", ".join(row.get("roles") or [])
            alias = row.get("alias") or "—"
            provider = row.get("provider_model") or "—"
            live = row.get("live_calls", 0)
            cached = row.get("cached_calls", 0)
            failed = row.get("failed_calls", 0)
            lines.append(
                f"| {roles} | `{alias}` | `{provider}` | {live} | {cached} | {failed} |"
            )
    else:
        lines.append("_No model call metadata recorded for this run._")

    lines.extend(["", "## Runtime", ""])
    phases = metadata.get("runtime_phases")
    if isinstance(phases, list) and phases:
        lines.extend(["| Phase | Duration |", "| --- | --- |"])
        for row in phases:
            if isinstance(row, dict):
                lines.append(f"| {row.get('phase', '—')} | {row.get('duration', '—')} |")
    else:
        lines.append("_No phase timing recorded._")

    lines.extend(["", "## Indicative cost estimate", ""])
    cost = _as_dict(metadata.get("approx_cost"))
    if cost.get("has_data"):
        total_tokens = int(cost.get("estimated_input_tokens_total") or 0)
        live_tokens = int(cost.get("estimated_input_tokens_live_only") or 0)
        lines.extend(
            [
                "| Measure | Value |",
                "| --- | --- |",
                f"| Estimated input tokens (all traces) | {total_tokens:,} |",
                f"| Estimated input tokens (live calls only) | {live_tokens:,} |",
            ]
        )
        cached = int(cost.get("estimated_input_tokens_cached_only") or 0)
        if cached > 0:
            lines.append(f"| Estimated input tokens (cached calls only) | {cached:,} |")
        if cost.get("has_output_token_data"):
            lines.append(
                f"| Estimated output tokens | {int(cost.get('estimated_output_tokens') or 0):,} |"
            )
        usd = cost.get("indicative_usd")
        if usd is not None:
            lines.append(f"| Lower-bound indicative USD (live input tokens only) | ~${usd:.2f} |")
        if cost.get("pricing_note"):
            lines.append("")
            lines.append(f"_{cost['pricing_note']}_")
    else:
        lines.append("_No token usage recorded for this run._")

    lines.extend(["", "## Results summary", ""])
    results = _as_dict(metadata.get("results"))
    if results:
        lines.extend(["| Metric | Count |", "| --- | ---: |"])
        for key, value in results.items():
            if value is None:
                continue
            label = key.replace("_", " ").strip().title()
            lines.append(f"| {label} | {value} |")
    else:
        lines.append("_No result counts available._")

    lines.extend(["", "## Settings & notes", ""])
    for setting in metadata.get("settings") or []:
        lines.append(f"- {setting}")
    notes = str(metadata.get("operator_notes") or "").strip()
    if notes:
        lines.extend(["", notes])
    warnings = metadata.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "**Warnings:**"])
        for warning in warnings:
            lines.append(f"- {warning}")

    lines.append("")
    return "\n".join(lines)


def write_model_md(path: Path, content: str) -> Path:
    target = path.parent / MODEL_MD_FILENAME
    target.write_text(content, encoding="utf-8")
    return target


def persist_model_md_for_discovery(
    run: DiscoveryRun,
    output_path: Path,
    *,
    input_path: Path | None = None,
) -> Path:
    metadata = build_discovery_model_metadata(run, output_path=output_path, input_path=input_path)
    return write_model_md(output_path, render_model_md(metadata))


def persist_model_md_for_related_expansion(
    run: RelatedSourceExpansionRun,
    output_path: Path,
    *,
    input_path: Path | None = None,
    category_label: str | None = None,
    category_description: str | None = None,
    jurisdiction_hints: list[str] | None = None,
) -> Path:
    metadata = build_related_expansion_model_metadata(
        run,
        output_path=output_path,
        input_path=input_path,
        category_label=category_label,
        category_description=category_description,
        jurisdiction_hints=jurisdiction_hints,
    )
    return write_model_md(output_path, render_model_md(metadata))


def persist_model_md_for_source_register(
    register: SourceRegister,
    output_path: Path,
    *,
    input_path: Path | None = None,
    category_label: str | None = None,
    run_kind: RunKind = "source-register",
) -> Path:
    metadata = build_source_register_model_metadata(
        register,
        output_path=output_path,
        input_path=input_path,
        category_label=category_label,
        run_kind=run_kind,
    )
    return write_model_md(output_path, render_model_md(metadata))


def persist_model_md_for_source_bundle(
    bundle: SourceBundle,
    output_path: Path,
    *,
    input_path: Path | None = None,
    category_label: str | None = None,
    run_kind: RunKind = "source-bundle",
) -> Path:
    metadata = build_source_bundle_model_metadata(
        bundle,
        output_path=output_path,
        input_path=input_path,
        category_label=category_label,
        run_kind=run_kind,
    )
    return write_model_md(output_path, render_model_md(metadata))
