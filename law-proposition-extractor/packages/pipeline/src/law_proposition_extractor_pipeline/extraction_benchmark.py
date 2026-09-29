"""Local extraction benchmark harness for operator model selection."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from law_proposition_extractor_llm import JuditLLMClient, LLMSettings

from .extract import (
    EXTRACTION_PROMPT_VERSION_V2,
    LOCAL_FEWSHOT_PROMPT_MARKER,
    _V2_SYSTEM_PROMPT,
    _v2_model_prompt,
    estimate_llm_input_tokens,
    extract_propositions_from_source,
    local_few_shot_prompt_used,
)
from .extraction_output_mode import (
    ExtractionOutputMode,
    resolve_extraction_output_mode,
)
from .extraction_debug import (
    _llm_invocation_traces,
    _parse_result_from_trace,
    resolve_debug_extraction_context,
)
from .extraction_empty_failure import NON_JSON_RESPONSE


JsonOutputMode = ExtractionOutputMode


def resolve_model_output_mode(
    model_alias: str,
    *,
    extraction_mode: Literal["local", "frontier"] = "local",
) -> JsonOutputMode:
    alias = str(model_alias or "").strip().lower()
    if alias.endswith("_schema") or alias.endswith("_json_schema"):
        return "json_schema"
    return resolve_extraction_output_mode(
        extraction_mode=extraction_mode,
        model_alias=model_alias,
        requested=None,
    )


def parse_locators(*, locator: str | None, locators: str | None) -> list[str]:
    raw_parts: list[str] = []
    if locators and str(locators).strip():
        raw_parts.extend(str(locators).split(","))
    elif locator and str(locator).strip():
        raw_parts.append(str(locator))
    parsed = [part.strip() for part in raw_parts if part.strip()]
    if not parsed:
        raise ValueError("At least one locator is required via --locators or --locator")
    return parsed


def parse_model_aliases(models: str) -> list[str]:
    aliases = [part.strip() for part in str(models or "").split(",") if part.strip()]
    if not aliases:
        raise ValueError("At least one model alias is required via --models")
    return aliases


def _parse_json_container(raw: str | None) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def is_benchmark_extraction_success(
    *,
    outcome_proposition_count: int,
    parse_result: dict[str, Any],
    last_trace: dict[str, Any],
) -> bool:
    failure_type = parse_result.get("failure_type") or last_trace.get("failure_type")
    if failure_type == NON_JSON_RESPONSE:
        return False

    validated_count = parse_result.get("validated_row_count")
    if isinstance(validated_count, int) and validated_count >= 1:
        return True
    if outcome_proposition_count >= 1:
        return True

    raw = last_trace.get("raw_model_output_excerpt")
    parsed = _parse_json_container(raw if isinstance(raw, str) else None)
    if parsed is None:
        return False
    if "propositions" not in parsed or not isinstance(parsed.get("propositions"), list):
        return False
    propositions = parsed["propositions"]
    if len(propositions) >= 1:
        return False
    return bool(str(parsed.get("empty_rationale") or "").strip())


def _few_shot_marker_present(*, prompt: str, extraction_mode: Literal["local", "frontier"]) -> bool:
    return local_few_shot_prompt_used(extraction_mode) and LOCAL_FEWSHOT_PROMPT_MARKER in prompt


def _attempt_records_from_outcome(
    outcome: Any,
    *,
    parse_result: dict[str, Any],
    last_trace: dict[str, Any],
    success: bool,
) -> list[dict[str, Any]]:
    llm_traces = _llm_invocation_traces(outcome.extraction_llm_call_traces)
    records: list[dict[str, Any]] = []
    for trace in llm_traces:
        succeeded = trace.get("llm_call_succeeded") is True
        record: dict[str, Any] = {
            "attempt_index": int(trace.get("attempt_index") or 0) + 1,
            "raw_output_excerpt": trace.get("raw_model_output_excerpt"),
            "failure_type": trace.get("failure_type"),
            "proposition_count": len(outcome.propositions) if succeeded else 0,
            "validated_row_count": trace.get("accepted_row_count"),
            "finish_reason": trace.get("finish_reason"),
            "previous_failure_type": trace.get("previous_failure_type"),
        }
        if trace.get("raw_model_output_truncated") is not None:
            record["raw_output_excerpt_truncated"] = trace.get("raw_model_output_truncated")
        records.append(record)
    if not records:
        records.append(
            {
                "attempt_index": 1,
                "raw_output_excerpt": last_trace.get("raw_model_output_excerpt"),
                "failure_type": parse_result.get("failure_type"),
                "proposition_count": len(outcome.propositions),
                "validated_row_count": parse_result.get("validated_row_count"),
                "finish_reason": last_trace.get("finish_reason"),
            }
        )
    records[-1]["success"] = success
    return records


def run_single_benchmark_extraction(
    path: str | Path,
    *,
    source_id: str,
    locator: str,
    model_alias: str,
    extraction_mode: Literal["local", "frontier"] = "local",
    max_propositions: int = 4,
    retry_empty_extraction: bool = True,
    json_output_mode: JsonOutputMode | None = None,
    extraction_output_mode: ExtractionOutputMode | str | None = None,
    allow_output_mode_fallback: bool = False,
) -> dict[str, Any]:
    """Run one production extraction attempt for benchmark measurement."""
    work, frag, fragment_text, topic, cluster = resolve_debug_extraction_context(
        path, source_id=source_id, locator=locator
    )
    llm_mode: Literal["local", "frontier"] = (
        "frontier" if extraction_mode == "frontier" else "local"
    )
    output_mode = (
        extraction_output_mode
        or json_output_mode
        or resolve_model_output_mode(model_alias, extraction_mode=extraction_mode)
    )
    client = JuditLLMClient(
        LLMSettings(
            local_extract_model=model_alias,
            frontier_extract_model=model_alias,
        )
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
    started = perf_counter()
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
        extraction_output_mode=output_mode,
    )
    latency_ms = int(max(0.0, (perf_counter() - started) * 1000))

    llm_traces = _llm_invocation_traces(outcome.extraction_llm_call_traces)
    last_trace = llm_traces[-1] if llm_traces else {}
    parse_result = _parse_result_from_trace(
        last_trace,
        validation_errors=list(outcome.validation_errors),
    )
    validated_row_count = parse_result.get("validated_row_count")
    if validated_row_count is None:
        validated_row_count = len(outcome.propositions)
    success = is_benchmark_extraction_success(
        outcome_proposition_count=len(outcome.propositions),
        parse_result=parse_result,
        last_trace=last_trace,
    )
    retry_fired = len(llm_traces) > 1 or any(
        int(trace.get("attempt_index") or 0) > 0 for trace in llm_traces
    )
    return {
        "source_record_id": source_id,
        "source_fragment_id": frag.id if frag is not None else None,
        "fragment_locator": locator,
        "model_alias": model_alias,
        "output_mode": output_mode,
        "extraction_output_mode": last_trace.get("extraction_output_mode") or output_mode,
        "response_format_type": last_trace.get("response_format_type"),
        "schema_hash": last_trace.get("schema_hash"),
        "extraction_mode": extraction_mode,
        "estimated_input_tokens": est_tokens,
        "latency_ms": latency_ms,
        "few_shot_marker_present": _few_shot_marker_present(prompt=prompt, extraction_mode=llm_mode),
        "retry_fired": retry_fired,
        "success": success,
        "failure_type": parse_result.get("failure_type") or last_trace.get("failure_type"),
        "proposition_count": len(outcome.propositions),
        "validated_row_count": validated_row_count,
        "raw_output_excerpt": last_trace.get("raw_model_output_excerpt"),
        "finish_reason": last_trace.get("finish_reason"),
        "parse_result": parse_result,
        "llm_attempts": _attempt_records_from_outcome(
            outcome,
            parse_result=parse_result,
            last_trace=last_trace,
            success=success,
        ),
    }


def _dominant_failure(failure_types: list[str | None]) -> str | None:
    filtered = [str(x) for x in failure_types if x]
    if not filtered:
        return None
    return Counter(filtered).most_common(1)[0][0]


def _aggregate_model_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {
            "model_alias": "",
            "output_mode": "",
            "attempts": 0,
            "success_rate": 0.0,
            "avg_props": 0.0,
            "dominant_failure": None,
            "avg_latency_ms": 0.0,
        }
    successes = sum(1 for run in runs if run.get("success"))
    props = [float(run.get("proposition_count") or 0) for run in runs]
    latencies = [float(run.get("latency_ms") or 0) for run in runs]
    return {
        "model_alias": runs[0].get("model_alias"),
        "output_mode": runs[0].get("output_mode"),
        "attempts": len(runs),
        "success_rate": round(successes / len(runs), 4),
        "avg_props": round(sum(props) / len(props), 2),
        "dominant_failure": _dominant_failure([run.get("failure_type") for run in runs]),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
    }


def benchmark_local_extraction(
    path: str | Path,
    *,
    source_id: str,
    locator: str | None = None,
    locators: str | None = None,
    models: str,
    attempts: int = 3,
    extraction_mode: Literal["local", "frontier"] = "local",
    retry_empty_extraction: bool = True,
    max_propositions: int = 4,
) -> dict[str, Any]:
    """Benchmark local extraction models across locators and attempts."""
    if attempts < 1:
        raise ValueError("--attempts must be at least 1")
    locator_list = parse_locators(locator=locator, locators=locators)
    model_aliases = parse_model_aliases(models)

    runs: list[dict[str, Any]] = []
    by_model: dict[str, list[dict[str, Any]]] = {alias: [] for alias in model_aliases}
    by_locator: dict[str, list[dict[str, Any]]] = {loc: [] for loc in locator_list}

    for model_alias in model_aliases:
        for fragment_locator in locator_list:
            for attempt_index in range(1, attempts + 1):
                run = run_single_benchmark_extraction(
                    path,
                    source_id=source_id,
                    locator=fragment_locator,
                    model_alias=model_alias,
                    extraction_mode=extraction_mode,
                    max_propositions=max_propositions,
                    retry_empty_extraction=retry_empty_extraction,
                )
                run["benchmark_attempt"] = attempt_index
                runs.append(run)
                by_model[model_alias].append(run)
                by_locator[fragment_locator].append(run)

    model_summaries = [_aggregate_model_summary(by_model[alias]) for alias in model_aliases]
    return {
        "benchmark": "local-extraction",
        "path": str(Path(path).expanduser().resolve()),
        "source_id": source_id,
        "locators": locator_list,
        "models": model_aliases,
        "attempts_per_model_locator": attempts,
        "extraction_mode": extraction_mode,
        "retry_empty_extraction": retry_empty_extraction,
        "runs": runs,
        "by_model": {alias: by_model[alias] for alias in model_aliases},
        "by_locator": {loc: by_locator[loc] for loc in locator_list},
        "summary_by_model": model_summaries,
    }


def format_benchmark_summary_table(summary_rows: list[dict[str, Any]]) -> str:
    headers = (
        "model_alias",
        "output_mode",
        "attempts",
        "success_rate",
        "avg_props",
        "dominant_failure",
        "avg_latency",
    )

    def _cell(value: object) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            if headers[3] == "success_rate" and 0 <= value <= 1:
                return f"{value:.2f}"
            return f"{value:.1f}" if value % 1 else str(int(value))
        text = str(value).strip()
        return text if text else "-"

    widths = [len(header) for header in headers]
    rendered_rows: list[list[str]] = []
    for row in summary_rows:
        cells = [
            _cell(row.get("model_alias")),
            _cell(row.get("output_mode")),
            _cell(row.get("attempts")),
            _cell(row.get("success_rate")),
            _cell(row.get("avg_props")),
            _cell(row.get("dominant_failure")),
            _cell(row.get("avg_latency_ms")),
        ]
        rendered_rows.append(cells)
        widths = [max(width, len(cell)) for width, cell in zip(widths, cells, strict=True)]

    def _fmt_line(cells: list[str]) -> str:
        return " | ".join(cell.ljust(width) for cell, width in zip(cells, widths, strict=True))

    lines = [_fmt_line(list(headers)), _fmt_line(["-" * width for width in widths])]
    lines.extend(_fmt_line(cells) for cells in rendered_rows)
    return "\n".join(lines)
