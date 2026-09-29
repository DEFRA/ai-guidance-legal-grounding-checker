"""Single-fragment extraction workbench: prompt-lab outputs without a full pipeline run."""

from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import Proposition, SourceRecord, is_placeholder_subject
from law_proposition_extractor_domain.proposition_notes import parse_extraction_meta
from law_proposition_extractor_llm import JuditLLMClient

from .extract import (
    EXTRACTION_PROMPT_VERSION_V2,
    EXTRACTION_SCHEMA_VERSION_V2,
    ExtractSourceResult,
    _V2_SYSTEM_PROMPT,
    _build_propositions_from_v2_rows,
    _parse_json,
    _parse_model_propositions_container,
    _validate_v2_items,
    _v2_model_prompt,
    estimate_llm_input_tokens,
    extract_propositions_from_source,
    local_few_shot_prompt_used,
)
from .extraction_debug import resolve_debug_extraction_context
from .intake import content_hash
from .proposition_normalisation import (
    PROPOSITION_NORMALISATION_METADATA,
    PROPOSITION_NORMALISATION_VERSION,
    normalise_extracted_propositions,
)

FragmentExtractionMode = Literal["local", "frontier", "dry"]

FRAGMENT_TXT = "fragment.txt"
PROMPT_TXT = "prompt.txt"
RAW_MODEL_OUTPUT_TXT = "raw_model_output.txt"
PARSED_EXTRACTION_JSON = "parsed_extraction.json"
PROPOSITIONS_RAW_JSON = "propositions.raw.json"
PROPOSITIONS_NORMALISED_JSON = "propositions.normalised.json"
EXTRACTION_TRACE_JSON = "extraction_trace.json"
REVIEW_MD = "review.md"
MODEL_MD = "MODEL.md"

WORKBENCH_OUTPUT_FILENAMES = (
    FRAGMENT_TXT,
    PROMPT_TXT,
    RAW_MODEL_OUTPUT_TXT,
    PARSED_EXTRACTION_JSON,
    PROPOSITIONS_RAW_JSON,
    PROPOSITIONS_NORMALISED_JSON,
    EXTRACTION_TRACE_JSON,
    REVIEW_MD,
    MODEL_MD,
)


@dataclass(frozen=True)
class FragmentWorkbenchInput:
    work_source: SourceRecord
    fragment_text: str
    fragment_locator: str
    source_id: str
    topic: Any
    cluster: Any
    source_fragment_id: str | None = None


@dataclass
class FragmentWorkbenchResult:
    fragment_text: str
    fragment_locator: str
    source_id: str
    source_fragment_id: str | None
    extraction_mode: FragmentExtractionMode
    user_prompt: str
    system_prompt: str
    model_alias: str | None
    estimated_input_tokens: int
    local_few_shot_prompt_mode: bool
    raw_model_output: str
    parsed_extraction_rows: list[dict[str, Any]]
    raw_propositions: list[Proposition]
    normalised_propositions: list[Proposition]
    extraction_outcome: ExtractSourceResult | None
    extraction_trace: dict[str, Any]
    validation_issue_records: list[dict[str, Any]]
    prompt_version: str
    schema_version: str
    extraction_output_mode: str | None
    workbench_status: str = "success"
    empty_reasons: list[str] = field(default_factory=list)
    actual_proposition_count: int = 0


def _is_prompt_lab_fixture(data: dict[str, Any]) -> bool:
    return bool(str(data.get("case_id") or "").strip() and str(data.get("fragment_text") or "").strip())


def load_extraction_fixture(path: str | Path) -> FragmentWorkbenchInput:
    """Load a prompt-lab fixture JSON (prompt-lab schema or legacy topic/cluster/source)."""
    resolved = Path(path).expanduser().resolve()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"fixture must be a JSON object: {resolved}")

    from law_proposition_extractor_domain import Cluster, Topic

    if _is_prompt_lab_fixture(data):
        source_id = str(data.get("source_record_id") or "").strip()
        if not source_id:
            raise ValueError("fixture.source_record_id is required")
        fragment_locator = str(data.get("fragment_locator") or "document:full").strip()
        fragment_text = str(data.get("fragment_text") or "").strip()
        label = str(data.get("label") or data.get("case_id") or "fixture")
        topic = Topic(
            id="topic-prompt-lab",
            name="slurry prompt-lab",
            description=label,
            subject_tags=["slurry", "prompt-lab"],
        )
        cluster = Cluster(
            id="cluster-prompt-lab",
            topic_id=topic.id,
            name=str(data.get("source_title") or "fixture source")[:120],
            description=str(data.get("why_this_case") or "")[:500],
        )
        meta: dict[str, Any] = {
            "prompt_lab_case_id": str(data.get("case_id") or ""),
            "prompt_lab_label": label,
            "expected_challenges": list(data.get("expected_challenges") or []),
            "expected_propositions": list(data.get("expected_propositions") or []),
        }
        work = SourceRecord(
            id=source_id,
            title=str(data.get("source_title") or source_id),
            jurisdiction=str(data.get("source_jurisdiction") or "UK"),
            citation="",
            kind="regulation",
            authoritative_text=fragment_text,
            authoritative_locator=fragment_locator,
            metadata=meta,
        )
        return FragmentWorkbenchInput(
            work_source=work,
            fragment_text=fragment_text,
            fragment_locator=fragment_locator,
            source_id=source_id,
            topic=topic,
            cluster=cluster,
            source_fragment_id=None,
        )

    topic_raw = data.get("topic") or {}
    cluster_raw = data.get("cluster") or {}
    source_raw = data.get("source")
    if not isinstance(source_raw, dict):
        raise ValueError("fixture.source must be an object")

    topic = Topic(
        id="topic-fixture",
        name=str(topic_raw.get("name") or "fixture"),
        description=str(topic_raw.get("description") or ""),
        subject_tags=list(topic_raw.get("subject_tags") or []),
    )
    cluster = Cluster(
        id="cluster-fixture",
        topic_id=topic.id,
        name=str(cluster_raw.get("name") or "fixture"),
        description=str(cluster_raw.get("description") or ""),
    )

    source_id = str(source_raw.get("id") or "").strip()
    if not source_id:
        raise ValueError("fixture.source.id is required")
    fragment_locator = str(
        source_raw.get("fragment_locator") or source_raw.get("locator") or "document:full"
    ).strip()
    fragment_text = str(source_raw.get("fragment_text") or source_raw.get("text") or "").strip()
    if not fragment_text:
        raise ValueError("fixture.source.fragment_text (or .text) is required")

    meta = dict(source_raw.get("metadata") or {})
    frag_id = source_raw.get("source_fragment_id") or source_raw.get("fragment_id")
    if frag_id:
        meta["extraction_fragment_id"] = str(frag_id)

    work = SourceRecord(
        id=source_id,
        title=str(source_raw.get("title") or source_id),
        jurisdiction=str(source_raw.get("jurisdiction") or "UK"),
        citation=str(source_raw.get("citation") or ""),
        kind=str(source_raw.get("kind") or "regulation"),
        authoritative_text=fragment_text,
        authoritative_locator=fragment_locator,
        metadata=meta,
    )
    return FragmentWorkbenchInput(
        work_source=work,
        fragment_text=fragment_text,
        fragment_locator=fragment_locator,
        source_id=source_id,
        topic=topic,
        cluster=cluster,
        source_fragment_id=str(frag_id) if frag_id else None,
    )


def _fixture_dry_raw_model_output(_fixture_path: Path, data: dict[str, Any]) -> str | None:
    dry = data.get("dry")
    if isinstance(dry, dict):
        raw = dry.get("raw_model_output")
        if isinstance(raw, str) and raw.strip():
            return raw
    return None


def load_prompt_lab_fixture(path: str | Path) -> dict[str, Any]:
    """Load and validate a prompt-lab fixture (metadata + review targets)."""
    resolved = Path(path).expanduser().resolve()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not _is_prompt_lab_fixture(data):
        raise ValueError(f"not a prompt-lab fixture: {resolved}")
    required = (
        "case_id",
        "label",
        "source_title",
        "source_record_id",
        "fragment_locator",
        "fragment_text",
        "why_this_case",
        "expected_challenges",
        "expected_propositions",
    )
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"fixture missing keys: {', '.join(missing)}")
    return data


def _render_prompt_file(*, system_prompt: str, user_prompt: str) -> str:
    return f"=== system ===\n{system_prompt.strip()}\n\n=== user ===\n{user_prompt.strip()}\n"


def _build_user_prompt(
    work: SourceRecord,
    topic: Any,
    cluster: Any,
    *,
    extraction_mode: Literal["local", "frontier"],
    max_propositions: int,
    fragment_text: str,
    fragment_locator: str,
) -> str:
    return _v2_model_prompt(
        work,
        topic,
        cluster,
        extraction_mode=extraction_mode,
        max_propositions=max_propositions,
        prompt_source_text=fragment_text,
        fragment_locator_hint=fragment_locator,
    )


def _llm_invocation_traces(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in traces if isinstance(t, dict) and t.get("llm_invoked") is True]


def _collect_raw_model_output_text(
    workbench_capture: dict[str, Any],
    outcome: ExtractSourceResult | None,
) -> str:
    outputs = [str(x) for x in (workbench_capture.get("raw_model_outputs") or []) if str(x).strip()]
    if outputs:
        return "\n\n--- retry attempt ---\n\n".join(outputs)
    if outcome is None:
        return ""
    excerpts: list[str] = []
    for trace in outcome.extraction_llm_call_traces:
        if not isinstance(trace, dict):
            continue
        excerpt = trace.get("raw_model_output_excerpt")
        if isinstance(excerpt, str) and excerpt.strip():
            excerpts.append(excerpt.strip())
    return "\n\n--- retry attempt ---\n\n".join(excerpts)


def _resolve_workbench_run_status(
    *,
    raw_model_output: str,
    parsed_rows: list[dict[str, Any]],
    normalised_props: list[Proposition],
    outcome: ExtractSourceResult | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not str(raw_model_output or "").strip():
        reasons.append("empty_raw_model_output")
    if not parsed_rows:
        reasons.append("no_parsed_extraction_rows")
    if not normalised_props:
        reasons.append("no_normalised_propositions")

    if not reasons:
        return "success", []

    transport_failed = False
    if outcome is not None:
        blob = " ".join(outcome.validation_errors).lower()
        transport_failed = any(
            token in blob
            for token in (
                "connection error",
                "connection refused",
                "timeout",
                "rate limit",
                "unavailable",
            )
        )
        if outcome.failed_closed or transport_failed:
            if transport_failed:
                reasons.append("llm_transport_or_parse_failure")
            return "failed", reasons
    return "empty_extraction", reasons


def _build_extraction_trace(
    *,
    extraction_mode: FragmentExtractionMode,
    model_alias: str | None,
    estimated_input_tokens: int,
    outcome: ExtractSourceResult | None,
    workbench_capture: dict[str, Any],
    local_few_shot: bool,
    extraction_output_mode: str | None,
    retry_empty_extraction: bool,
    raw_model_output: str,
    parsed_row_count: int,
    normalised_proposition_count: int,
    workbench_status: str,
    empty_reasons: list[str],
) -> dict[str, Any]:
    traces = list(outcome.extraction_llm_call_traces) if outcome else []
    llm_traces = _llm_invocation_traces(traces)
    last = llm_traces[-1] if llm_traces else {}
    prompt_hash = content_hash(
        str(last.get("prompt_hash_source") or last.get("prompt_preview") or "")
    )[:16]
    if last.get("prompt_hash"):
        prompt_hash = str(last["prompt_hash"])

    repair_attempts = max(0, len(llm_traces) - 1)
    evidence_strategies = [
        str(r.get("_validated_evidence_match_strategy") or r.get("evidence_match_strategy") or "")
        for r in workbench_capture.get("validated_rows") or []
        if isinstance(r, dict)
    ]

    validated_rows = workbench_capture.get("validated_rows") or []
    validated_count = len(validated_rows) if isinstance(validated_rows, list) else 0

    return {
        "status": workbench_status,
        "empty_reasons": list(empty_reasons),
        "actual_proposition_count": normalised_proposition_count,
        "parsed_row_count": parsed_row_count,
        "validated_row_count": validated_count,
        "normalised_proposition_count": normalised_proposition_count,
        "raw_model_output_length": len(raw_model_output or ""),
        "extraction_mode": extraction_mode,
        "model_alias": model_alias,
        "estimated_input_tokens": estimated_input_tokens,
        "prompt_hash": prompt_hash,
        "local_few_shot_prompt_mode": local_few_shot,
        "retry_empty_extraction": retry_empty_extraction,
        "repair_attempts": repair_attempts,
        "llm_call_count": len(llm_traces),
        "llm_invoked": last.get("llm_invoked"),
        "llm_call_attempted": last.get("llm_call_attempted"),
        "llm_call_succeeded": last.get("llm_call_succeeded"),
        "finish_reason": last.get("finish_reason"),
        "failure_type": last.get("failure_type"),
        "extraction_output_mode": extraction_output_mode or last.get("extraction_output_mode"),
        "response_format_type": last.get("response_format_type"),
        "schema_hash": last.get("schema_hash"),
        "evidence_match_strategies": [s for s in evidence_strategies if s],
        "validation_errors": list(outcome.validation_errors) if outcome else [],
        "fallback_used": bool(outcome.fallback_used) if outcome else False,
        "llm_traces": llm_traces,
    }


def _run_dry_extraction(
    *,
    work: SourceRecord,
    topic: Any,
    cluster: Any,
    fragment_text: str,
    fragment_locator: str,
    raw_model_output: str,
    max_propositions: int,
) -> tuple[list[dict[str, Any]], list[Proposition], list[dict[str, Any]], list[str]]:
    parsed = _parse_json(raw_model_output)
    raw_rows = _parse_model_propositions_container(parsed)
    validated, verrs, issue_records = _validate_v2_items(
        raw_rows, fragment_text, limit=max_propositions
    )
    props = _build_propositions_from_v2_rows(
        rows=validated,
        source=work,
        topic=topic,
        cluster=cluster,
        limit=max_propositions,
    )
    return validated, props, issue_records, verrs


def run_extract_fragment_workbench(
    *,
    fixture_path: str | Path | None = None,
    case_or_run_dir: str | Path | None = None,
    source_id: str | None = None,
    locator: str | None = None,
    extraction_mode: FragmentExtractionMode = "local",
    max_propositions: int = 8,
    retry_empty_extraction: bool = True,
    extraction_output_mode: str | None = None,
    allow_output_mode_fallback: bool = False,
    dry_raw_model_output: str | None = None,
) -> FragmentWorkbenchResult:
    """Run production single-fragment extraction and assemble prompt-lab artifacts."""
    fixture_data: dict[str, Any] | None = None
    if fixture_path is not None:
        resolved_fixture = Path(fixture_path).expanduser().resolve()
        fixture_data = json.loads(resolved_fixture.read_text(encoding="utf-8"))
        if not isinstance(fixture_data, dict):
            raise ValueError("fixture must be a JSON object")
        ctx = load_extraction_fixture(resolved_fixture)
        if max_propositions == 8 and isinstance(fixture_data.get("max_propositions"), int):
            max_propositions = int(fixture_data["max_propositions"])
        dry_from_fixture = _fixture_dry_raw_model_output(resolved_fixture, fixture_data)
    elif case_or_run_dir is not None:
        if not source_id or not locator:
            raise ValueError("source_id and locator are required when using case_or_run_dir")
        work, frag, fragment_text, topic, cluster = resolve_debug_extraction_context(
            case_or_run_dir, source_id=source_id, locator=locator
        )
        ctx = FragmentWorkbenchInput(
            work_source=work,
            fragment_text=fragment_text,
            fragment_locator=locator,
            source_id=source_id,
            topic=topic,
            cluster=cluster,
            source_fragment_id=frag.id if frag is not None else None,
        )
        dry_from_fixture = None
    else:
        raise ValueError("provide fixture_path or case_or_run_dir")

    llm_mode: Literal["local", "frontier"] = (
        "frontier" if extraction_mode == "frontier" else "local"
    )
    user_prompt = _build_user_prompt(
        ctx.work_source,
        ctx.topic,
        ctx.cluster,
        extraction_mode=llm_mode,
        max_propositions=max_propositions,
        fragment_text=ctx.fragment_text,
        fragment_locator=ctx.fragment_locator,
    )
    est_tokens = estimate_llm_input_tokens(prompt=user_prompt, system_prompt=_V2_SYSTEM_PROMPT)
    local_few_shot = local_few_shot_prompt_used(llm_mode)

    if dry_raw_model_output is not None:
        dry_raw: str | None = dry_raw_model_output
    else:
        dry_raw = dry_from_fixture
    use_dry = extraction_mode == "dry"
    if use_dry and dry_raw is None:
        raise ValueError("dry mode requires fixture.dry.raw_model_output or --dry-raw-model-output")

    model_alias: str | None = None
    outcome: ExtractSourceResult | None = None
    workbench_capture: dict[str, Any] = {}
    validation_issue_records: list[dict[str, Any]] = []
    effective_mode: FragmentExtractionMode = extraction_mode

    if use_dry:
        effective_mode = "dry"
        assert dry_raw is not None
        workbench_capture["raw_model_outputs"] = [dry_raw]
        raw_model_output = dry_raw
        try:
            validated, raw_props, validation_issue_records, _verrs = _run_dry_extraction(
                work=ctx.work_source,
                topic=ctx.topic,
                cluster=ctx.cluster,
                fragment_text=ctx.fragment_text,
                fragment_locator=ctx.fragment_locator,
                raw_model_output=dry_raw,
                max_propositions=max_propositions,
            )
        except json.JSONDecodeError as exc:
            validated = []
            raw_props = []
            validation_issue_records = [
                {
                    "code": "dry_raw_json_decode_error",
                    "message": str(exc),
                }
            ]
        workbench_capture["validated_rows"] = validated
    else:
        if extraction_mode not in {"local", "frontier"}:
            raise ValueError("--mode must be local, frontier, or dry")
        client = JuditLLMClient()
        model_alias = (
            client.settings.frontier_extract_model
            if llm_mode == "frontier"
            else client.settings.local_extract_model
        )
        outcome = extract_propositions_from_source(
            ctx.work_source,
            ctx.topic,
            ctx.cluster,
            llm_client=client,
            limit=max_propositions,
            extraction_mode=llm_mode,
            extraction_fallback="fail_closed",
            prompt_version=EXTRACTION_PROMPT_VERSION_V2,
            retry_empty_extraction=retry_empty_extraction,
            extraction_output_mode=extraction_output_mode,  # type: ignore[arg-type]
            allow_output_mode_fallback=allow_output_mode_fallback,
            workbench_capture=workbench_capture,
        )
        raw_props = list(outcome.propositions)
        validation_issue_records = list(outcome.validation_issue_records)
        raw_model_output = _collect_raw_model_output_text(workbench_capture, outcome)

    parsed_rows = list(workbench_capture.get("validated_rows") or [])
    if not raw_props and parsed_rows:
        raw_props = _build_propositions_from_v2_rows(
            rows=parsed_rows,
            source=ctx.work_source,
            topic=ctx.topic,
            cluster=ctx.cluster,
            limit=max_propositions,
        )

    if not parsed_rows and str(raw_model_output or "").strip():
        try:
            salvaged_rows, salvaged_props, salvage_issues, _salvage_verrs = _run_dry_extraction(
                work=ctx.work_source,
                topic=ctx.topic,
                cluster=ctx.cluster,
                fragment_text=ctx.fragment_text,
                fragment_locator=ctx.fragment_locator,
                raw_model_output=raw_model_output,
                max_propositions=max_propositions,
            )
        except json.JSONDecodeError:
            salvaged_rows = []
            salvaged_props = []
            salvage_issues = []
        if salvaged_rows:
            workbench_capture["validated_rows"] = salvaged_rows
            parsed_rows = salvaged_rows
            if not raw_props:
                raw_props = salvaged_props
            validation_issue_records = list(validation_issue_records) + list(salvage_issues)
            if outcome is not None and outcome.validation_errors:
                validation_issue_records.extend(
                    {"kind": "json_salvage", "failure_reason": err}
                    for err in outcome.validation_errors
                    if isinstance(err, str) and err.strip()
                )

    raw_props_copy = [Proposition.model_validate(p.model_dump(mode="python")) for p in raw_props]
    normalised = normalise_extracted_propositions(
        [Proposition.model_validate(deepcopy(p.model_dump(mode="python"))) for p in raw_props_copy],
        source_by_id={ctx.source_id: ctx.work_source},
    )

    workbench_status, empty_reasons = _resolve_workbench_run_status(
        raw_model_output=raw_model_output,
        parsed_rows=parsed_rows,
        normalised_props=normalised,
        outcome=outcome,
    )

    trace = _build_extraction_trace(
        extraction_mode=effective_mode,
        model_alias=model_alias,
        estimated_input_tokens=est_tokens,
        outcome=outcome,
        workbench_capture=workbench_capture,
        local_few_shot=local_few_shot,
        extraction_output_mode=extraction_output_mode,
        retry_empty_extraction=retry_empty_extraction,
        raw_model_output=raw_model_output,
        parsed_row_count=len(parsed_rows),
        normalised_proposition_count=len(normalised),
        workbench_status=workbench_status,
        empty_reasons=empty_reasons,
    )
    trace["prompt_version"] = EXTRACTION_PROMPT_VERSION_V2
    trace["prompt_hash"] = content_hash(user_prompt)[:16]
    trace["schema_version"] = (
        outcome.schema_version if outcome else EXTRACTION_SCHEMA_VERSION_V2
    )

    return FragmentWorkbenchResult(
        fragment_text=ctx.fragment_text,
        fragment_locator=ctx.fragment_locator,
        source_id=ctx.source_id,
        source_fragment_id=ctx.source_fragment_id,
        extraction_mode=effective_mode,
        user_prompt=user_prompt,
        system_prompt=_V2_SYSTEM_PROMPT,
        model_alias=model_alias,
        estimated_input_tokens=est_tokens,
        local_few_shot_prompt_mode=local_few_shot,
        raw_model_output=raw_model_output,
        parsed_extraction_rows=parsed_rows,
        raw_propositions=raw_props_copy,
        normalised_propositions=normalised,
        extraction_outcome=outcome,
        extraction_trace=trace,
        validation_issue_records=validation_issue_records,
        prompt_version=EXTRACTION_PROMPT_VERSION_V2,
        schema_version=trace["schema_version"],
        extraction_output_mode=extraction_output_mode,
        workbench_status=workbench_status,
        empty_reasons=list(empty_reasons),
        actual_proposition_count=len(normalised),
    )


def _label_for_row(prop: dict[str, Any]) -> str:
    return str(prop.get("label") or prop.get("display_label") or "").strip()


def _proposition_row_dict(prop: Proposition) -> dict[str, Any]:
    return prop.model_dump(mode="json")


def _evidence_issues(prop: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    meta = parse_extraction_meta(prop.get("notes"))
    eq = ""
    if meta:
        eq = str(meta.get("evidence_quote") or "").strip()
        if not eq:
            issues.append("empty_evidence_quote")
        for w in meta.get("trace_warnings") or []:
            if isinstance(w, str) and w.strip():
                issues.append(w.strip())
    text = str(prop.get("proposition_text") or "")
    if "evidence" in str(prop.get("notes") or "").lower() and not meta:
        issues.append("notes_mention_evidence")
    if not eq and re.search(r"\b(must|shall|required)\b", text, re.I):
        issues.append("normative_without_evidence_meta")
    return issues


def build_fragment_review_markdown(
    *,
    raw_propositions: list[dict[str, Any]],
    normalised_propositions: list[dict[str, Any]],
    parsed_rows: list[dict[str, Any]],
    validation_issue_records: list[dict[str, Any]],
    workbench_status: str = "success",
    empty_reasons: list[str] | None = None,
    extraction_trace: dict[str, Any] | None = None,
) -> str:
    """Human-readable fragment extraction summary for review.md."""
    raw_count = len(raw_propositions)
    norm_count = len(normalised_propositions)
    reasons = list(empty_reasons or [])

    tier_counts: Counter[str] = Counter()
    effect_counts: Counter[str] = Counter()
    compliance_relevant = 0
    for row in normalised_propositions:
        tier = str(row.get("proposition_tier") or "(none)")
        effect = str(row.get("legal_effect_type") or "(none)")
        tier_counts[tier] += 1
        effect_counts[effect] += 1
        if row.get("is_compliance_relevant") is True:
            compliance_relevant += 1

    evidence_issues: list[str] = []
    weak_actor_action: list[str] = []
    for row in normalised_propositions:
        pid = str(row.get("id") or row.get("proposition_key") or "?")
        ev = _evidence_issues(row)
        if ev:
            evidence_issues.append(f"- `{pid}`: {', '.join(ev)}")
        subj = str(row.get("legal_subject") or "")
        action = str(row.get("action") or "")
        if is_placeholder_subject(subj) or len(subj.strip()) < 3:
            weak_actor_action.append(f"- `{pid}`: weak subject `{subj!r}`")
        if len(action.strip()) < 3:
            weak_actor_action.append(f"- `{pid}`: weak action `{action!r}`")

    missed_conditions: list[str] = []
    for row in normalised_propositions:
        pid = str(row.get("id") or "?")
        text = str(row.get("proposition_text") or "")
        conditions = row.get("conditions") or []
        if (
            not conditions
            and re.search(r"\b(unless|except|where|provided that|subject to)\b", text, re.I)
        ):
            missed_conditions.append(f"- `{pid}`: text suggests conditions but none extracted")

    label_changes: list[str] = []
    norm_by_key: dict[str, dict[str, Any]] = {}
    for row in normalised_propositions:
        key = str(row.get("proposition_key") or row.get("id") or "")
        if key:
            norm_by_key[key] = row
    for raw in raw_propositions:
        key = str(raw.get("proposition_key") or raw.get("id") or "")
        norm = norm_by_key.get(key)
        if not norm:
            continue
        raw_label = _label_for_row(raw)
        norm_label = _label_for_row(norm)
        if raw_label != norm_label:
            label_changes.append(
                f"- `{key}`: {raw_label!r} → {norm_label!r}"
                if raw_label or norm_label
                else f"- `{key}`: (no label) → {norm_label!r}"
            )

    lines = [
        "# Fragment extraction review",
        "",
        f"- **Workbench status:** `{workbench_status}`",
        f"- **Actual proposition count:** {norm_count}",
        f"- **Propositions (raw / normalised):** {raw_count} / {norm_count}",
        f"- **Parsed extraction rows:** {len(parsed_rows)}",
        f"- **Compliance-relevant:** {compliance_relevant}",
        "",
    ]
    if reasons:
        lines.append("## Empty / failed extraction")
        lines.append("")
        for reason in reasons:
            lines.append(f"- `{reason}`")
        lines.append("")
    if extraction_trace:
        lines.extend(
            [
                "## Extraction trace (summary)",
                "",
                f"- **LLM invoked:** {extraction_trace.get('llm_invoked')}",
                f"- **LLM call succeeded:** {extraction_trace.get('llm_call_succeeded')}",
                f"- **Model alias:** `{extraction_trace.get('model_alias')}`",
                f"- **Finish reason:** {extraction_trace.get('finish_reason')}",
                f"- **Failure type:** {extraction_trace.get('failure_type')}",
                f"- **Raw model output length:** {extraction_trace.get('raw_model_output_length')}",
                f"- **Validated rows:** {extraction_trace.get('validated_row_count')}",
                "",
            ]
        )
    lines.extend(["## Tier counts", ""])
    for tier, count in sorted(tier_counts.items()):
        lines.append(f"- `{tier}`: {count}")
    lines.extend(["", "## Legal effect counts", ""])
    for effect, count in sorted(effect_counts.items()):
        lines.append(f"- `{effect}`: {count}")

    lines.extend(["", "## Evidence issues", ""])
    lines.extend(evidence_issues or ["- None noted."])

    lines.extend(["", "## Weak subject / action", ""])
    lines.extend(weak_actor_action or ["- None noted."])

    lines.extend(["", "## Possible missed conditions / exceptions", ""])
    lines.extend(missed_conditions or ["- None flagged."])

    lines.extend(["", "## Raw vs normalised labels", ""])
    lines.extend(label_changes or ["- No label changes from normalisation passes."])

    if validation_issue_records:
        lines.extend(["", "## Validation issue records", ""])
        for rec in validation_issue_records[:20]:
            if isinstance(rec, dict):
                lines.append(
                    f"- row {rec.get('row_index', '?')}: "
                    f"{rec.get('reason_code') or rec.get('failure_reason') or rec}"
                )

    return "\n".join(lines) + "\n"


def build_fragment_model_md(result: FragmentWorkbenchResult) -> str:
    """Mini MODEL.md for a single-fragment prompt-lab run."""
    generated = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    prompt_hash = content_hash(result.user_prompt)[:16]
    passes = ", ".join(str(p) for p in PROPOSITION_NORMALISATION_METADATA.get("passes") or [])
    return "\n".join(
        [
            "# Fragment extraction (prompt lab)",
            "",
            f"Generated **{generated}**.",
            "",
            "## Identity",
            "",
            f"- **Source record:** `{result.source_id}`",
            f"- **Fragment locator:** `{result.fragment_locator}`",
            f"- **Extraction mode:** `{result.extraction_mode}`",
            "",
            "## Prompt & schema",
            "",
            f"- **Prompt version:** `{result.prompt_version}`",
            f"- **Prompt hash:** `{prompt_hash}`",
            f"- **Schema version:** `{result.schema_version}`",
            "",
            "## Model",
            "",
            f"- **Model alias:** `{result.model_alias or 'n/a (dry)'}`",
            f"- **Extraction output mode:** `{result.extraction_output_mode or result.extraction_trace.get('extraction_output_mode') or 'json_object'}`",
            f"- **Estimated input tokens:** {result.estimated_input_tokens}",
            f"- **Local few-shot block:** {result.local_few_shot_prompt_mode}",
            "",
            "## Normalisation",
            "",
            f"- **Version:** `{PROPOSITION_NORMALISATION_VERSION}`",
            f"- **Passes:** {passes}",
            "",
        ]
    )


def write_extract_fragment_workbench_outputs(
    result: FragmentWorkbenchResult,
    output_dir: str | Path,
) -> Path:
    """Write deterministic prompt-lab artifacts under *output_dir* (created if needed)."""
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    raw_json = [_proposition_row_dict(p) for p in result.raw_propositions]
    norm_json = [_proposition_row_dict(p) for p in result.normalised_propositions]

    (out / FRAGMENT_TXT).write_text(result.fragment_text, encoding="utf-8")
    (out / PROMPT_TXT).write_text(
        _render_prompt_file(system_prompt=result.system_prompt, user_prompt=result.user_prompt),
        encoding="utf-8",
    )
    (out / RAW_MODEL_OUTPUT_TXT).write_text(result.raw_model_output or "", encoding="utf-8")
    (out / PARSED_EXTRACTION_JSON).write_text(
        json.dumps(result.parsed_extraction_rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out / PROPOSITIONS_RAW_JSON).write_text(
        json.dumps(raw_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out / PROPOSITIONS_NORMALISED_JSON).write_text(
        json.dumps(norm_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out / EXTRACTION_TRACE_JSON).write_text(
        json.dumps(result.extraction_trace, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out / REVIEW_MD).write_text(
        build_fragment_review_markdown(
            raw_propositions=raw_json,
            normalised_propositions=norm_json,
            parsed_rows=result.parsed_extraction_rows,
            validation_issue_records=result.validation_issue_records,
            workbench_status=result.workbench_status,
            empty_reasons=result.empty_reasons,
            extraction_trace=result.extraction_trace,
        ),
        encoding="utf-8",
    )
    (out / MODEL_MD).write_text(build_fragment_model_md(result), encoding="utf-8")
    return out


def reapply_normalisation_to_run_dir(run_dir: str | Path) -> int:
    """Re-run deterministic classification passes on propositions.raw.json (no LLM)."""
    root = Path(run_dir).expanduser().resolve()
    raw_path = root / PROPOSITIONS_RAW_JSON
    if not raw_path.is_file():
        raise FileNotFoundError(f"missing {raw_path}")
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{raw_path.name} must be a JSON array")
    props = [Proposition.model_validate(row) for row in payload if isinstance(row, dict)]
    normalised = normalise_extracted_propositions(props)
    norm_json = [_proposition_row_dict(p) for p in normalised]
    (root / PROPOSITIONS_NORMALISED_JSON).write_text(
        json.dumps(norm_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return len(normalised)
