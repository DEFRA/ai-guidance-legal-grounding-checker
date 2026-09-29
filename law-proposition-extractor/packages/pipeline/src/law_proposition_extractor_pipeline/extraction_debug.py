"""Single-fragment LLM extraction debugging for operators."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import Cluster, SourceRecord, SourceFragment, Topic
from law_proposition_extractor_llm import JuditLLMClient

from .extract import (
    EXTRACTION_PROMPT_VERSION_V2,
    _V2_SYSTEM_PROMPT,
    _v2_model_prompt,
    estimate_llm_input_tokens,
    extract_propositions_from_source,
    local_few_shot_prompt_used,
)
from .extraction_empty_failure import empty_extraction_retry_not_eligible_reason
from .file_input import load_case_file
from .intake import register_sources
from .linting import load_exported_bundle
from .run_persistence import load_persisted_run_bundle, resolve_run_directory


def _normalize_locator(locator: str) -> str:
    return str(locator or "").strip().lower()


def _find_fragment_in_bundle(
    bundle: dict[str, Any],
    *,
    source_id: str,
    locator: str,
) -> tuple[SourceRecord, SourceFragment | None, str]:
    target = _normalize_locator(locator)
    sources = [
        SourceRecord.model_validate(x)
        for x in bundle.get("source_records") or []
        if isinstance(x, dict)
    ]
    fragments = [
        SourceFragment.model_validate(x)
        for x in bundle.get("source_fragments") or []
        if isinstance(x, dict)
    ]
    source = next((s for s in sources if s.id == source_id), None)
    if source is None:
        raise ValueError(f"source_record_id not found in bundle: {source_id}")
    frag = next(
        (
            f
            for f in fragments
            if f.source_record_id == source_id and _normalize_locator(str(f.locator or "")) == target
        ),
        None,
    )
    if frag is not None:
        work = source.model_copy(
            deep=True,
            update={
                "authoritative_text": frag.fragment_text,
                "authoritative_locator": frag.locator,
                "metadata": {
                    **(dict(source.metadata) if isinstance(source.metadata, dict) else {}),
                    "extraction_fragment_id": frag.id,
                },
            },
        )
        return work, frag, frag.fragment_text
    if _normalize_locator(str(source.authoritative_locator or "")) == target:
        return source, None, source.authoritative_text
    raise ValueError(
        f"fragment locator {locator!r} not found for source {source_id!r} "
        f"({len(fragments)} fragment(s) in bundle)"
    )


def _topic_cluster_from_case(case_data: dict[str, Any]) -> tuple[Topic, Cluster]:
    topic_raw = case_data.get("topic") or {}
    cluster_raw = case_data.get("cluster") or {}
    topic = Topic(
        id="topic-debug",
        name=str(topic_raw.get("name") or "debug"),
        description=str(topic_raw.get("description") or ""),
        subject_tags=list(topic_raw.get("subject_tags") or []),
    )
    cluster = Cluster(
        id="cluster-debug",
        topic_id=topic.id,
        name=str(cluster_raw.get("name") or "debug"),
        description=str(cluster_raw.get("description") or ""),
    )
    return topic, cluster


def _find_fragment_from_case(
    case_data: dict[str, Any],
    *,
    source_id: str,
    locator: str,
) -> tuple[SourceRecord, SourceFragment | None, str, Topic, Cluster]:
    topic, cluster = _topic_cluster_from_case(case_data)
    sources, _snapshots, fragments, _reviews = register_sources(case_data.get("sources") or [])
    source = next((s for s in sources if s.id == source_id), None)
    if source is None:
        raise ValueError(f"source id not found in case: {source_id}")
    target = _normalize_locator(locator)
    frag = next(
        (
            f
            for f in fragments
            if f.source_record_id == source_id and _normalize_locator(str(f.locator or "")) == target
        ),
        None,
    )
    if frag is not None:
        work = source.model_copy(
            deep=True,
            update={
                "authoritative_text": frag.fragment_text,
                "authoritative_locator": frag.locator,
                "metadata": {
                    **(dict(source.metadata) if isinstance(source.metadata, dict) else {}),
                    "extraction_fragment_id": frag.id,
                },
            },
        )
        return work, frag, frag.fragment_text, topic, cluster
    if _normalize_locator(str(source.authoritative_locator or "")) == target:
        return source, None, source.authoritative_text, topic, cluster
    raise ValueError(f"fragment locator {locator!r} not found for source {source_id!r}")


def resolve_debug_extraction_context(
    path: str | Path,
    *,
    source_id: str,
    locator: str,
) -> tuple[SourceRecord, SourceFragment | None, str, Topic, Cluster]:
    resolved = Path(path).expanduser().resolve()
    if resolved.is_file() and resolved.name == "case.json":
        return _find_fragment_from_case(load_case_file(resolved), source_id=source_id, locator=locator)
    run_dir = resolve_run_directory(resolved)
    bundle_path = run_dir / "run_bundle.json"
    if bundle_path.is_file():
        bundle = load_persisted_run_bundle(run_dir)
        topic, cluster = _topic_cluster_from_case(bundle)
        work, frag, text = _find_fragment_in_bundle(bundle, source_id=source_id, locator=locator)
        return work, frag, text, topic, cluster
    try:
        bundle = load_exported_bundle(resolved)
        topic, cluster = _topic_cluster_from_case(bundle)
        work, frag, text = _find_fragment_in_bundle(bundle, source_id=source_id, locator=locator)
        return work, frag, text, topic, cluster
    except ValueError:
        case_path = run_dir / "case.json"
        if case_path.is_file():
            return _find_fragment_from_case(
                load_case_file(case_path), source_id=source_id, locator=locator
            )
        raise


def _llm_invocation_traces(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        trace
        for trace in traces
        if isinstance(trace, dict) and trace.get("llm_invoked") is True
    ]


def _attempt_from_trace(
    trace: dict[str, Any],
    *,
    proposition_count: int | None,
) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "attempt_index": int(trace.get("attempt_index") or 0) + 1,
        "raw_model_response": trace.get("raw_model_output_excerpt"),
        "failure_type": trace.get("failure_type"),
    }
    if trace.get("raw_model_output_truncated") is not None:
        attempt["raw_model_response_truncated"] = trace.get("raw_model_output_truncated")
    if trace.get("finish_reason") is not None:
        attempt["finish_reason"] = trace.get("finish_reason")
    if trace.get("previous_failure_type"):
        attempt["previous_failure_type"] = trace.get("previous_failure_type")
    if proposition_count is not None:
        attempt["proposition_count"] = proposition_count
    return attempt


def _parse_result_from_trace(trace: dict[str, Any], *, validation_errors: list[str]) -> dict[str, Any]:
    return {
        "model_error": trace.get("model_error"),
        "failure_type": trace.get("failure_type"),
        "candidate_row_count": trace.get("candidate_row_count"),
        "validated_row_count": trace.get("accepted_row_count"),
        "validation_errors": validation_errors[:20],
        "parse_diagnostics": {
            key: trace[key]
            for key in (
                "failure_type",
                "failure_reason",
                "raw_model_output_excerpt",
                "raw_model_output_truncated",
                "finish_reason",
                "parse_error_message",
                "parse_error_line",
                "parse_error_column",
                "candidate_row_count",
                "accepted_row_count",
            )
            if key in trace
        },
    }


def debug_extract_fragment(
    path: str | Path,
    *,
    source_id: str,
    locator: str,
    extraction_mode: Literal["local", "frontier"] = "local",
    max_propositions: int = 4,
    prompt_preview_chars: int = 1200,
    retry_empty_extraction: bool = True,
    retry_empty_extraction_transport: bool = False,
    extraction_output_mode: str | None = None,
    allow_output_mode_fallback: bool = False,
) -> dict[str, Any]:
    """Run production fragment extraction and return operator diagnostics."""
    work, frag, fragment_text, topic, cluster = resolve_debug_extraction_context(
        path, source_id=source_id, locator=locator
    )
    llm_mode: Literal["local", "frontier"] = (
        "frontier" if extraction_mode == "frontier" else "local"
    )
    client = JuditLLMClient()
    model_alias = (
        client.settings.frontier_extract_model
        if llm_mode == "frontier"
        else client.settings.local_extract_model
    )
    prompt = _v2_model_prompt(
        work,
        topic,
        cluster,
        extraction_mode=llm_mode,
        max_propositions=max_propositions,
        prompt_source_text=fragment_text,
        fragment_locator_hint=locator,
    )
    est_tokens = estimate_llm_input_tokens(prompt=prompt, system_prompt=_V2_SYSTEM_PROMPT)

    outcome = extract_propositions_from_source(
        work,
        topic,
        cluster,
        llm_client=client,
        limit=max_propositions,
        extraction_mode=llm_mode,
        extraction_fallback="fail_closed",
        prompt_version=EXTRACTION_PROMPT_VERSION_V2,
        retry_empty_extraction=retry_empty_extraction,
        retry_empty_extraction_transport=retry_empty_extraction_transport,
        extraction_output_mode=extraction_output_mode,  # type: ignore[arg-type]
        allow_output_mode_fallback=allow_output_mode_fallback,
    )

    llm_traces = _llm_invocation_traces(outcome.extraction_llm_call_traces)
    attempts: list[dict[str, Any]] = []
    for trace in llm_traces:
        succeeded = trace.get("llm_call_succeeded") is True
        attempt_prop_count = len(outcome.propositions) if succeeded else 0
        attempts.append(
            _attempt_from_trace(trace, proposition_count=attempt_prop_count if succeeded else None)
        )

    payload: dict[str, Any] = {
        "source_record_id": source_id,
        "source_fragment_id": frag.id if frag is not None else None,
        "fragment_locator": locator,
        "fragment_text": fragment_text,
        "fragment_text_chars": len(fragment_text),
        "extraction_mode": extraction_mode,
        "local_few_shot_prompt_mode": local_few_shot_prompt_used(llm_mode),
        "model_alias": model_alias,
        "estimated_input_tokens": est_tokens,
        "prompt_preview": prompt[:prompt_preview_chars],
        "prompt_preview_truncated": len(prompt) > prompt_preview_chars,
        "retry_empty_extraction": retry_empty_extraction,
        "attempts": attempts,
        "proposition_count": len(outcome.propositions),
    }

    if retry_empty_extraction and llm_traces:
        first_trace = llm_traces[0]
        first_failed = first_trace.get("llm_call_succeeded") is not True
        if first_failed:
            not_eligible_reason = empty_extraction_retry_not_eligible_reason(
                first_trace.get("failure_type"),
                extraction_mode=llm_mode,
                retry_transport_empty=retry_empty_extraction_transport,
            )
            if not_eligible_reason is None and len(llm_traces) < 2:
                raise RuntimeError(
                    "debug_extract_fragment: empty-extraction retry was eligible but not attempted"
                )
            if not_eligible_reason is not None:
                payload["retry_eligible"] = False
                payload["retry_not_eligible_reason"] = not_eligible_reason

    last_trace = llm_traces[-1] if llm_traces else {}
    payload.update(
        {
            "raw_model_response": last_trace.get("raw_model_output_excerpt"),
            "raw_model_response_truncated": last_trace.get("raw_model_output_truncated"),
            "finish_reason": last_trace.get("finish_reason"),
            "extraction_output_mode": last_trace.get("extraction_output_mode"),
            "response_format_type": last_trace.get("response_format_type"),
            "schema_hash": last_trace.get("schema_hash"),
            "response_format": last_trace.get("response_format"),
            "parse_result": _parse_result_from_trace(
                last_trace,
                validation_errors=list(outcome.validation_errors),
            ),
        }
    )
    return payload
