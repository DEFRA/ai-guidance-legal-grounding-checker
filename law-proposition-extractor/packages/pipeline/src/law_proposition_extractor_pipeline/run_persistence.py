"""Persist pipeline run outputs and enforce safe export semantics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .cli_run_summary import (
    build_cli_completion_summary,
    extraction_mode_from_bundle,
    extraction_mode_requested_from_bundle,
)
from .llm_extraction_config import resolve_extraction_fallback_for_run, resolve_extraction_mode_requested
from .run_quality import build_run_quality_summary
from .source_bundle_intake import resolve_case_output_paths

RUN_BUNDLE_FILENAME = "run_bundle.json"


@dataclass
class PersistedRunConfig:
    use_llm: bool
    extraction_mode_requested: str
    extraction_mode_effective: str
    extraction_fallback: str
    extraction_execution_mode: str | None = None
    divergence_reasoning: str | None = None
    principal_only: bool | None = None
    include_amendments: bool | None = None
    include_revocations: bool | None = None
    max_sources: int | None = None
    proposition_count: int = 0
    completed_at: str = ""
    source_sections: dict[str, Any] = field(default_factory=dict)
    run_status: str | None = None
    failure_reason: str | None = None
    export_incomplete: bool | None = None
    export_not_benchmarkable: bool | None = None
    benchmark_verdict: str | None = None

    def to_case_extraction_block(self) -> dict[str, Any]:
        block: dict[str, Any] = {
            "mode": self.extraction_mode_effective,
            "fallback_policy": self.extraction_fallback,
        }
        if self.extraction_execution_mode:
            block["execution_mode"] = self.extraction_execution_mode
        return block

    def to_judit_run_block(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["run_bundle_file"] = RUN_BUNDLE_FILENAME
        return {k: v for k, v in payload.items() if v is not None}


def resolve_run_directory(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if resolved.is_file():
        return resolved.parent
    return resolved


def run_bundle_path(run_dir: str | Path) -> Path:
    return Path(run_dir).resolve() / RUN_BUNDLE_FILENAME


def has_persisted_run_bundle(path: str | Path) -> bool:
    run_dir = resolve_run_directory(path)
    return run_bundle_path(run_dir).is_file()


def load_persisted_run_bundle(path: str | Path) -> dict[str, Any]:
    bundle_file = run_bundle_path(resolve_run_directory(path))
    if not bundle_file.is_file():
        raise ValueError(
            f"No persisted run bundle at {bundle_file}. "
            f"Run `run-bundle` or `run-case` first, then use `export-run`."
        )
    payload = json.loads(bundle_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid run bundle JSON: {bundle_file}")
    return payload


def load_persisted_run_config(case_data: dict[str, Any]) -> PersistedRunConfig | None:
    raw = case_data.get("judit_run")
    if not isinstance(raw, dict):
        return None
    try:
        return PersistedRunConfig(
            use_llm=bool(raw.get("use_llm")),
            extraction_mode_requested=str(raw.get("extraction_mode_requested") or ""),
            extraction_mode_effective=str(raw.get("extraction_mode_effective") or ""),
            extraction_fallback=str(raw.get("extraction_fallback") or "fallback"),
            extraction_execution_mode=(
                str(raw["extraction_execution_mode"])
                if raw.get("extraction_execution_mode") is not None
                else None
            ),
            divergence_reasoning=(
                str(raw["divergence_reasoning"]) if raw.get("divergence_reasoning") is not None else None
            ),
            principal_only=raw.get("principal_only"),
            include_amendments=raw.get("include_amendments"),
            include_revocations=raw.get("include_revocations"),
            max_sources=raw.get("max_sources"),
            proposition_count=int(raw.get("proposition_count") or 0),
            completed_at=str(raw.get("completed_at") or ""),
            source_sections=dict(raw.get("source_sections") or {}),
        )
    except (TypeError, ValueError):
        return None


def build_persisted_run_config(
    *,
    bundle: dict[str, Any],
    use_llm: bool,
    extraction_mode: str | None,
    extraction_fallback: str | None,
    extraction_execution_mode: str | None = None,
    divergence_reasoning: str | None = None,
    case_data: dict[str, Any] | None = None,
    principal_only: bool | None = None,
    include_amendments: bool | None = None,
    include_revocations: bool | None = None,
    max_sources: int | None = None,
    source_sections: dict[str, Any] | None = None,
) -> PersistedRunConfig:
    case_data = case_data or {}
    requested = extraction_mode_requested_from_bundle(bundle)
    if requested == "unknown":
        requested = resolve_extraction_mode_requested(
            use_llm=use_llm,
            extraction_mode=extraction_mode,
            case_data=case_data,
        )
    effective = extraction_mode_from_bundle(bundle)
    if effective == "unknown":
        effective = requested
    props = bundle.get("propositions")
    prop_count = len(props) if isinstance(props, list) else 0
    abort = bundle.get("extraction_abort_metadata")
    abort_dict = abort if isinstance(abort, dict) else {}
    run_status = str(bundle.get("run_status") or abort_dict.get("run_status") or "") or None
    failure_reason = (
        str(bundle.get("failure_reason") or abort_dict.get("failure_reason") or "") or None
    )
    export_incomplete = bundle.get("export_incomplete")
    if export_incomplete is None:
        export_incomplete = abort_dict.get("export_incomplete")
    export_not_benchmarkable = bundle.get("export_not_benchmarkable")
    if export_not_benchmarkable is None:
        export_not_benchmarkable = abort_dict.get("export_not_benchmarkable")
    benchmark_verdict = str(bundle.get("benchmark_verdict") or abort_dict.get("benchmark_verdict") or "") or None
    return PersistedRunConfig(
        use_llm=use_llm,
        extraction_mode_requested=requested,
        extraction_mode_effective=effective,
        extraction_fallback=resolve_extraction_fallback_for_run(
            use_llm=use_llm,
            extraction_fallback=extraction_fallback,
        ),
        extraction_execution_mode=extraction_execution_mode,
        divergence_reasoning=divergence_reasoning,
        principal_only=principal_only,
        include_amendments=include_amendments,
        include_revocations=include_revocations,
        max_sources=max_sources,
        proposition_count=prop_count,
        completed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        source_sections=dict(source_sections or {}),
        run_status=run_status,
        failure_reason=failure_reason,
        export_incomplete=bool(export_incomplete) if export_incomplete is not None else None,
        export_not_benchmarkable=(
            bool(export_not_benchmarkable) if export_not_benchmarkable is not None else None
        ),
        benchmark_verdict=benchmark_verdict,
    )


def stamp_case_with_run_metadata(
    case_data: dict[str, Any],
    run_config: PersistedRunConfig,
) -> dict[str, Any]:
    updated = dict(case_data)
    extraction = dict(updated.get("extraction") or {})
    extraction.update(run_config.to_case_extraction_block())
    updated["extraction"] = extraction
    updated["judit_run"] = run_config.to_judit_run_block()
    return updated


def persist_run_outputs(
    *,
    output: str | Path,
    case_data: dict[str, Any],
    bundle: dict[str, Any],
    run_config: PersistedRunConfig,
) -> Path:
    case_dir, case_json = resolve_case_output_paths(output)
    case_dir.mkdir(parents=True, exist_ok=True)
    stamped = stamp_case_with_run_metadata(case_data, run_config)
    case_json.write_text(json.dumps(stamped, indent=2) + "\n", encoding="utf-8")
    from .export import attach_proposition_normalisation_quality
    from .run_model_md import MODEL_MD_FILENAME, attach_run_model_metadata, render_model_md

    attach_proposition_normalisation_quality(bundle, output_dir=case_dir)
    metadata = attach_run_model_metadata(
        bundle,
        case_data=stamped,
        run_config=run_config,
        output_dir=case_dir,
        output_path_anchor=case_dir.resolve(),
    )
    (case_dir / MODEL_MD_FILENAME).write_text(render_model_md(metadata), encoding="utf-8")
    run_bundle_path(case_dir).write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return case_json


def planned_extraction_mode(
    *,
    use_llm: bool,
    extraction_mode: str | None,
    case_data: dict[str, Any],
) -> str:
    return resolve_extraction_mode_requested(
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        case_data=case_data,
    )


def validate_rerun_extraction_allowed(
    *,
    persisted: PersistedRunConfig | None,
    rerun: bool,
    use_llm: bool,
    extraction_mode: str | None,
    case_data: dict[str, Any],
) -> str:
    """
    Return the extraction mode that will run, or raise ValueError when rerun is unsafe.

    When a prior run exists, reruns require explicit ``--rerun`` and ``--extraction-mode``.
    """
    if persisted is None:
        return planned_extraction_mode(
            use_llm=use_llm,
            extraction_mode=extraction_mode,
            case_data=case_data,
        )
    if not rerun:
        return persisted.extraction_mode_effective
    if extraction_mode is None:
        raise ValueError(
            "Refusing to re-run extraction: prior run used "
            f"extraction_mode={persisted.extraction_mode_effective!r}. "
            "Pass --rerun and an explicit --extraction-mode "
            "(heuristic | local | frontier)."
        )
    return planned_extraction_mode(
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        case_data=case_data,
    )


def export_mismatch_messages(
    *,
    source_bundle: dict[str, Any],
    exported_bundle: dict[str, Any],
) -> list[str]:
    source_summary = build_cli_completion_summary(
        source_bundle,
        quality_summary=build_run_quality_summary(source_bundle),
        output_dir=None,
    )
    export_summary = build_cli_completion_summary(
        exported_bundle,
        quality_summary=build_run_quality_summary(exported_bundle),
        output_dir=None,
    )
    messages: list[str] = []
    src_mode = str(source_summary.get("extraction_mode_effective") or source_summary.get("extraction_mode"))
    out_mode = str(export_summary.get("extraction_mode_effective") or export_summary.get("extraction_mode"))
    if src_mode and out_mode and src_mode != out_mode:
        messages.append(f"extraction_mode {src_mode} -> {out_mode}")
    src_props = int(source_summary.get("propositions") or 0)
    out_props = int(export_summary.get("propositions") or 0)
    if src_props != out_props:
        messages.append(f"propositions {src_props} -> {out_props}")
    return messages


def assert_export_matches_source(
    *,
    source_bundle: dict[str, Any],
    exported_bundle: dict[str, Any],
) -> None:
    messages = export_mismatch_messages(source_bundle=source_bundle, exported_bundle=exported_bundle)
    if not messages:
        return
    joined = " and ".join(messages)
    raise ValueError(f"Refusing to export: export would change {joined}.")


def rerun_extraction_warning(mode: str) -> str:
    return f"This will re-run extraction with mode {mode}."


def expects_persisted_run_layout(path: str | Path) -> bool:
    resolved = Path(path)
    if resolved.is_dir():
        return True
    return resolved.name == "case.json"
