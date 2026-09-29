"""Deterministic salvage of propositions from failed extraction JSON excerpts."""

from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import Cluster, Proposition, SourceFragment, SourceRecord, Topic

from .extract import (
    EXTRACTION_SCHEMA_VERSION_V2,
    _build_propositions_from_v2_rows,
    _parse_model_propositions_container,
    _proposition_id_stem,
    _validate_v2_items,
    assign_proposition_extraction_debug,
)
from .extraction_empty_failure import NON_JSON_RESPONSE
from .extraction_repair import _gather_extraction_llm_traces
from .export import export_bundle

JSON_PARSE_FAILURE_TYPES: frozenset[str] = frozenset(
    {"non_json_response", "json_parse_or_llm_failure"}
)

_STRING_FIELD_NAMES: tuple[str, ...] = (
    "proposition_text",
    "display_label",
    "subject",
    "rule",
    "object",
    "evidence_text",
    "reason",
    "temporal_condition",
    "source_locator",
)


@dataclass(frozen=True)
class JsonRepairCandidate:
    job_id: str | None
    trace_id: str | None
    source_record_id: str
    source_fragment_id: str | None
    fragment_locator: str | None
    failure_type: str
    repair_reason: str | None
    raw_excerpt: str
    parse_error_message: str | None

    def job_key(self) -> tuple[str, str | None]:
        return (self.source_record_id, self.source_fragment_id)


@dataclass(frozen=True)
class JsonRepairAttemptResult:
    ok: bool
    repair_method: str | None
    parsed: dict[str, Any] | None
    raw_rows: list[dict[str, Any]]
    validated_rows: list[dict[str, Any]]
    validation_errors: list[str]
    error: str | None = None


@dataclass(frozen=True)
class ExtractionJsonParseResult:
    """Parsed extraction JSON plus optional deterministic repair metadata."""

    parsed: dict[str, Any]
    json_repair_applied: bool = False
    json_repair_method: str | None = None
    raw_model_output: str | None = None


@dataclass(frozen=True)
class JsonRepairChunkOutcome:
    candidate: JsonRepairCandidate
    repaired: bool
    repair_method: str | None
    proposition_count: int
    validation_errors: list[str]
    validated_rows: tuple[dict[str, Any], ...] = ()
    error: str | None = None


def strip_markdown_json_fence(text: str) -> str:
    """Remove leading/trailing markdown ``` fences (including incomplete closing fences)."""
    out = text.strip()
    if out.startswith("```"):
        lines = out.splitlines()
        if lines:
            first = lines[0].strip().lower()
            if first.startswith("```"):
                lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        out = "\n".join(lines).strip()
    while out.rstrip().endswith("```"):
        out = out.rstrip()[:-3].rstrip()
    return out


def extract_json_object_substring(text: str) -> str:
    """Drop leading non-JSON prose; keep from first ``{``."""
    start = text.find("{")
    if start < 0:
        return text.strip()
    return text[start:].strip()


def extract_first_balanced_json_object(text: str) -> str | None:
    """Return the first top-level JSON object substring, ignoring trailing prose."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def strip_trailing_prose_after_json(text: str) -> str:
    """Keep only the first balanced JSON object (drops trailing explanatory prose)."""
    obj = extract_first_balanced_json_object(text)
    return obj if obj is not None else text.strip()


def _iter_json_object_substrings(text: str) -> list[str]:
    """Yield candidate top-level JSON object substrings in document order."""
    found: list[str] = []
    pos = 0
    while pos < len(text):
        start = text.find("{", pos)
        if start < 0:
            break
        obj = extract_first_balanced_json_object(text[start:])
        if obj is None:
            pos = start + 1
            continue
        found.append(obj)
        pos = start + len(obj)
    return found


def close_truncated_json(text: str) -> str:
    """Close open strings/arrays/objects when output was cut mid-stream."""
    out: list[str] = []
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        out.append(ch)
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in ("}", "]") and stack and stack[-1] == ch:
            stack.pop()
    if in_string:
        out.append('"')
    while stack:
        out.append(stack.pop())
    return "".join(out)


def _fix_unescaped_quotes_in_string_fields(text: str) -> str:
    """Escape interior double-quotes inside known string-valued proposition fields."""
    pattern = re.compile(
        r'"(?P<field>' + "|".join(re.escape(name) for name in _STRING_FIELD_NAMES) + r')"\s*:\s*"'
    )
    pieces: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        pieces.append(text[cursor : match.start()])
        field_start = match.end()
        value_chars: list[str] = []
        idx = field_start
        # Model sometimes doubles the opening quote before a defined term: ""slurry" means …"
        if idx + 1 < len(text) and text[idx : idx + 2] == '""' and text[idx + 2 : idx + 3].isalpha():
            value_chars.append('\\"')
            idx += 2
        while idx < len(text):
            ch = text[idx]
            if ch == "\\":
                value_chars.append(ch)
                if idx + 1 < len(text):
                    value_chars.append(text[idx + 1])
                    idx += 2
                    continue
            elif ch == '"':
                tail = text[idx + 1 : idx + 80].lstrip()
                if not tail or tail[0] in {",", "}", "]"}:
                    pieces.append(match.group(0))
                    pieces.append("".join(value_chars))
                    pieces.append('"')
                    cursor = idx + 1
                    break
                value_chars.append('\\"')
                idx += 1
                continue
            value_chars.append(ch)
            idx += 1
        else:
            pieces.append(text[cursor:])
            return "".join(pieces)
    pieces.append(text[cursor:])
    return "".join(pieces)


def salvage_complete_proposition_objects(text: str, *, apply_quote_fix: bool = True) -> dict[str, Any] | None:
    """Extract fully closed proposition objects from a truncated ``propositions`` array."""
    cleaned = strip_markdown_json_fence(text)
    if apply_quote_fix:
        cleaned = _fix_unescaped_quotes_in_string_fields(cleaned)
    idx = cleaned.find('"propositions"')
    if idx < 0:
        return None
    arr_start = cleaned.find("[", idx)
    if arr_start < 0:
        return None

    objects: list[dict[str, Any]] = []
    pos = arr_start + 1
    length = len(cleaned)
    while pos < length:
        while pos < length and cleaned[pos] in " \t\r\n,":
            pos += 1
        if pos >= length or cleaned[pos] == "]":
            break
        if cleaned[pos] != "{":
            break

        depth = 0
        in_string = False
        escape = False
        obj_start = pos
        obj_end: int | None = None
        for idx_char in range(pos, length):
            ch = cleaned[idx_char]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    obj_end = idx_char
                    break
        if obj_end is None:
            break
        fragment = cleaned[obj_start : obj_end + 1]
        try:
            parsed_obj = json.loads(fragment)
        except json.JSONDecodeError:
            break
        if isinstance(parsed_obj, dict) and parsed_obj.get("proposition_text"):
            objects.append(parsed_obj)
        pos = obj_end + 1

    if not objects:
        return None
    return {"propositions": objects}


def _attempt_parse(text: str, *, repair_method: str) -> JsonRepairAttemptResult:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return JsonRepairAttemptResult(
            ok=False,
            repair_method=repair_method,
            parsed=None,
            raw_rows=[],
            validated_rows=[],
            validation_errors=[],
            error=str(exc),
        )
    if not isinstance(parsed, dict):
        return JsonRepairAttemptResult(
            ok=False,
            repair_method=repair_method,
            parsed=None,
            raw_rows=[],
            validated_rows=[],
            validation_errors=[],
            error="parsed value is not a JSON object",
        )
    if "propositions" not in parsed:
        return JsonRepairAttemptResult(
            ok=False,
            repair_method=repair_method,
            parsed=None,
            raw_rows=[],
            validated_rows=[],
            validation_errors=[],
            error="parsed object missing top-level propositions key",
        )
    raw_rows = _parse_model_propositions_container(parsed)
    return JsonRepairAttemptResult(
        ok=True,
        repair_method=repair_method,
        parsed=parsed,
        raw_rows=raw_rows,
        validated_rows=[],
        validation_errors=[],
    )


def _repair_candidate_texts(raw: str) -> list[tuple[str, str]]:
    """Build ordered (method, text) candidates for deterministic JSON repair."""
    base = raw.strip()
    fenced = strip_markdown_json_fence(base)
    fixed = _fix_unescaped_quotes_in_string_fields(fenced)
    first_obj = extract_first_balanced_json_object(fenced)
    fixed_first_obj = extract_first_balanced_json_object(fixed)

    candidates: list[tuple[str, str]] = [
        ("direct_parse", base),
        ("strip_fenced_json", fenced),
        ("extract_json_substring", extract_json_object_substring(fenced)),
    ]
    if first_obj is not None:
        candidates.append(("strip_trailing_prose", first_obj))
    candidates.extend(
        [
            ("fix_unescaped_quotes", fixed),
            ("fix_unescaped_and_close_truncated", close_truncated_json(fixed)),
        ]
    )
    if fixed_first_obj is not None:
        candidates.append(("fix_unescaped_quotes_and_strip_prose", fixed_first_obj))

    for index, block in enumerate(_iter_json_object_substrings(fixed)):
        block_fixed = _fix_unescaped_quotes_in_string_fields(block)
        candidates.append((f"multi_block_{index}", block))
        if block_fixed != block:
            candidates.append((f"multi_block_{index}_fixed", block_fixed))

    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for method, text in candidates:
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append((method, text))
    return ordered


def repair_extraction_json_text(raw: str) -> JsonRepairAttemptResult:
    """Try deterministic JSON repair strategies until one yields parseable JSON."""
    if not str(raw or "").strip():
        return JsonRepairAttemptResult(
            ok=False,
            repair_method=None,
            parsed=None,
            raw_rows=[],
            validated_rows=[],
            validation_errors=[],
            error="empty excerpt",
        )

    last_error = "no strategy succeeded"
    empty_ok: JsonRepairAttemptResult | None = None

    for method, candidate_text in _repair_candidate_texts(raw):
        attempt = _attempt_parse(candidate_text, repair_method=method)
        if not attempt.ok:
            last_error = attempt.error or last_error
            continue
        if attempt.raw_rows:
            return attempt
        if empty_ok is None:
            empty_ok = attempt

    salvaged = salvage_complete_proposition_objects(raw, apply_quote_fix=True)
    if salvaged is not None:
        attempt = _attempt_parse(json.dumps(salvaged), repair_method="salvage_complete_objects")
        if attempt.ok:
            if attempt.raw_rows:
                return attempt
            if empty_ok is None:
                empty_ok = attempt
        else:
            last_error = attempt.error or last_error

    if empty_ok is not None:
        return empty_ok

    return JsonRepairAttemptResult(
        ok=False,
        repair_method=None,
        parsed=None,
        raw_rows=[],
        validated_rows=[],
        validation_errors=[],
        error=last_error,
    )


def parse_extraction_json(raw: str) -> ExtractionJsonParseResult:
    """Parse model extraction JSON, applying deterministic repair when needed."""
    preserved = raw if isinstance(raw, str) else str(raw or "")
    try:
        parsed = json.loads(strip_markdown_json_fence(preserved.strip()))
    except json.JSONDecodeError as orig:
        repaired = repair_extraction_json_text(preserved)
        if not repaired.ok or not isinstance(repaired.parsed, dict):
            # Preserve the original parse position so downstream traces report the real
            # error line/column rather than always 1:1.
            raise json.JSONDecodeError(
                repaired.error or "JSON repair failed", preserved, orig.pos
            ) from orig
        return ExtractionJsonParseResult(
            parsed=repaired.parsed,
            json_repair_applied=True,
            json_repair_method=repaired.repair_method,
            raw_model_output=preserved,
        )
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("parsed value is not a JSON object", preserved, 0)
    if "propositions" not in parsed:
        repaired = repair_extraction_json_text(preserved)
        if repaired.ok and isinstance(repaired.parsed, dict):
            return ExtractionJsonParseResult(
                parsed=repaired.parsed,
                json_repair_applied=True,
                json_repair_method=repaired.repair_method,
                raw_model_output=preserved,
            )
        raise json.JSONDecodeError("parsed object missing top-level propositions key", preserved, 0)
    return ExtractionJsonParseResult(
        parsed=parsed,
        json_repair_applied=False,
        json_repair_method=None,
        raw_model_output=preserved,
    )


def _job_is_json_parse_candidate(job: dict[str, Any]) -> bool:
    excerpt = job.get("raw_model_output_excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        return False
    repair_reason = str(job.get("repair_reason") or "").strip()
    if repair_reason == "json_parse_or_llm_failure":
        return True
    errors = job.get("errors")
    if isinstance(errors, list):
        blob = " ".join(str(x) for x in errors).lower()
        if "json parse" in blob or "jsondecode" in blob or "non-json" in blob:
            return True
    return False


def _trace_is_json_parse_candidate(trace: dict[str, Any]) -> bool:
    excerpt = trace.get("raw_model_output_excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        return False
    failure_type = str(trace.get("failure_type") or "").strip()
    if failure_type in JSON_PARSE_FAILURE_TYPES:
        return True
    blob = " ".join(
        str(trace.get(key) or "")
        for key in ("failure_reason", "model_error", "skip_reason", "error")
    ).lower()
    return "json parse" in blob or "jsondecode" in blob or "non-json" in blob


def list_json_repair_candidates(bundle: dict[str, Any]) -> list[JsonRepairCandidate]:
    """Return failed extraction chunks eligible for deterministic JSON repair."""
    by_key: dict[tuple[str, str | None], JsonRepairCandidate] = {}

    def upsert(candidate: JsonRepairCandidate) -> None:
        key = candidate.job_key()
        existing = by_key.get(key)
        if existing is None or len(candidate.raw_excerpt) > len(existing.raw_excerpt):
            by_key[key] = candidate

    for job in bundle.get("proposition_extraction_jobs") or []:
        if not isinstance(job, dict) or not _job_is_json_parse_candidate(job):
            continue
        sid = str(job.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = job.get("source_fragment_id")
        frag_id = str(frag_raw).strip() if frag_raw else None
        excerpt = str(job.get("raw_model_output_excerpt") or "")
        upsert(
            JsonRepairCandidate(
                job_id=str(job.get("id") or "") or None,
                trace_id=None,
                source_record_id=sid,
                source_fragment_id=frag_id,
                fragment_locator=str(job.get("fragment_locator") or "") or None,
                failure_type=str(job.get("repair_reason") or "json_parse_or_llm_failure"),
                repair_reason=str(job.get("repair_reason") or "") or None,
                raw_excerpt=excerpt,
                parse_error_message=str(job.get("parse_error_message") or "") or None,
            )
        )

    for trace in _gather_extraction_llm_traces(bundle):
        if not _trace_is_json_parse_candidate(trace):
            continue
        sid = str(trace.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = trace.get("source_fragment_id")
        frag_id = str(frag_raw).strip() if frag_raw else None
        excerpt = str(trace.get("raw_model_output_excerpt") or "")
        failure_type = str(trace.get("failure_type") or NON_JSON_RESPONSE)
        upsert(
            JsonRepairCandidate(
                job_id=None,
                trace_id=str(trace.get("id") or trace.get("trace_id") or "") or None,
                source_record_id=sid,
                source_fragment_id=frag_id,
                fragment_locator=str(trace.get("fragment_locator") or "") or None,
                failure_type=failure_type,
                repair_reason="json_parse_or_llm_failure"
                if failure_type == NON_JSON_RESPONSE
                else failure_type,
                raw_excerpt=excerpt,
                parse_error_message=str(trace.get("parse_error_message") or "") or None,
            )
        )

    return sorted(by_key.values(), key=lambda c: (c.source_record_id, c.fragment_locator or "", c.job_id or ""))


def _bundle_sources(bundle: dict[str, Any]) -> list[SourceRecord]:
    raw = bundle.get("source_records") or bundle.get("sources") or []
    return [SourceRecord.model_validate(row) for row in raw if isinstance(row, dict)]


def _read_optional_export_json(root: Path, filename: str) -> Any | None:
    path = root / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _enrich_bundle_from_export_files(bundle: dict[str, Any], export_root: Path) -> dict[str, Any]:
    enriched = copy.deepcopy(bundle)
    for key, filename in (
        ("topic", "topic.json"),
        ("clusters", "clusters.json"),
        ("narrative", "narrative.json"),
    ):
        if enriched.get(key):
            continue
        payload = _read_optional_export_json(export_root, filename)
        if payload is not None:
            enriched[key] = payload

    if not enriched.get("narrative"):
        case_inputs = enriched.get("pipeline_case_inputs")
        if not isinstance(case_inputs, dict):
            case_inputs = _read_optional_export_json(export_root, "pipeline_case_inputs.json")
            if isinstance(case_inputs, dict):
                enriched["pipeline_case_inputs"] = case_inputs
        narrative = case_inputs.get("narrative") if isinstance(case_inputs, dict) else None
        if isinstance(narrative, dict) and narrative.get("title"):
            enriched["narrative"] = narrative
        else:
            enriched["narrative"] = {
                "title": str(enriched.get("run", {}).get("id") or "Repaired export"),
                "summary": "Bundle repaired from failed extraction JSON excerpts.",
                "sections": [],
            }

    if "sections" not in (enriched.get("narrative") or {}):
        narrative = dict(enriched.get("narrative") or {})
        narrative.setdefault("title", "Repaired export")
        narrative.setdefault("summary", "")
        narrative.setdefault("sections", [])
        enriched["narrative"] = narrative

    return enriched


def _bundle_topic_cluster(bundle: dict[str, Any]) -> tuple[Topic, Cluster]:
    topic_raw = dict(bundle.get("topic") or {})
    topic_raw.setdefault("id", "topic-json-repair")
    topic_raw.setdefault("name", "")
    topic_raw.setdefault("description", "")
    topic_raw.setdefault("subject_tags", [])
    topic = Topic.model_validate(topic_raw)
    clusters = bundle.get("clusters") or []
    cluster_raw = dict(clusters[0] if isinstance(clusters, list) and clusters else {})
    cluster_raw.setdefault("id", "cluster-json-repair")
    cluster_raw.setdefault("topic_id", topic.id)
    cluster_raw.setdefault("name", "")
    cluster_raw.setdefault("description", "")
    cluster = Cluster.model_validate(cluster_raw)
    return topic, cluster


def _bundle_fragments(bundle: dict[str, Any]) -> list[SourceFragment]:
    return [
        SourceFragment.model_validate(row)
        for row in (bundle.get("source_fragments") or [])
        if isinstance(row, dict)
    ]


def _resolve_fragment(
    *,
    bundle: dict[str, Any],
    candidate: JsonRepairCandidate,
) -> SourceFragment | None:
    fragments = _bundle_fragments(bundle)
    if candidate.source_fragment_id:
        for frag in fragments:
            if str(frag.id) == candidate.source_fragment_id:
                return frag
    if candidate.fragment_locator:
        locator = candidate.fragment_locator.strip().lower()
        for frag in fragments:
            if str(frag.locator or "").strip().lower() == locator and str(frag.source_record_id) == candidate.source_record_id:
                return frag
    for frag in fragments:
        if str(frag.source_record_id) == candidate.source_record_id:
            return frag
    return None


def _extraction_limit(bundle: dict[str, Any]) -> int:
    inputs = bundle.get("pipeline_case_inputs")
    if isinstance(inputs, dict):
        extraction = inputs.get("extraction")
        if isinstance(extraction, dict):
            raw = extraction.get("max_propositions_per_source")
            if isinstance(raw, int) and raw > 0:
                return raw
    for trace in bundle.get("stage_traces") or []:
        if not isinstance(trace, dict):
            continue
        if str(trace.get("stage_name") or "") != "proposition extraction":
            continue
        inputs = trace.get("inputs")
        if isinstance(inputs, dict):
            raw = inputs.get("max_propositions_per_source") or inputs.get(
                "effective_max_propositions_per_source"
            )
            if isinstance(raw, int) and raw > 0:
                return raw
    return 4


def _next_proposition_index(*, bundle: dict[str, Any], source: SourceRecord) -> int:
    stem = _proposition_id_stem(source)
    prefix = f"prop-{stem}-"
    max_index = 0
    for row in bundle.get("propositions") or []:
        if not isinstance(row, dict):
            continue
        prop_id = str(row.get("id") or "")
        if not prop_id.startswith(prefix):
            continue
        suffix = prop_id[len(prefix) :]
        if suffix.isdigit():
            max_index = max(max_index, int(suffix))
    return max_index + 1


def validate_repaired_rows(
    *,
    raw_rows: list[dict[str, Any]],
    fragment_text: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    validated, errors, _issues = _validate_v2_items(raw_rows, fragment_text, limit=limit)
    return validated, errors


def build_repaired_propositions(
    *,
    bundle: dict[str, Any],
    candidate: JsonRepairCandidate,
    validated_rows: list[dict[str, Any]],
    repair_method: str,
) -> list[Proposition]:
    sources = _bundle_sources(bundle)
    source = next((s for s in sources if s.id == candidate.source_record_id), None)
    if source is None:
        return []
    topic, cluster = _bundle_topic_cluster(bundle)
    fragment = _resolve_fragment(bundle=bundle, candidate=candidate)
    start_index = _next_proposition_index(bundle=bundle, source=source)
    props = _build_propositions_from_v2_rows(
        rows=validated_rows,
        source=source,
        topic=topic,
        cluster=cluster,
        limit=len(validated_rows),
        id_sequence_start=start_index,
    )
    provenance = {
        "extraction_mode": "json_repair",
        "repair_source_trace_id": candidate.trace_id or candidate.job_id,
        "repair_method": repair_method,
        "original_failure_type": candidate.failure_type,
        "original_raw_excerpt": candidate.raw_excerpt[:4000],
        "schema_version": EXTRACTION_SCHEMA_VERSION_V2,
        "validation_errors": [],
    }
    for prop in props:
        if fragment is not None:
            prop.source_fragment_id = fragment.id
            prop.fragment_locator = fragment.locator
            prop.source_snapshot_id = fragment.source_snapshot_id or source.current_snapshot_id
        assign_proposition_extraction_debug(prop, provenance)
    return props


def attempt_json_repair_for_candidate(
    *,
    bundle: dict[str, Any],
    candidate: JsonRepairCandidate,
) -> JsonRepairChunkOutcome:
    fragment = _resolve_fragment(bundle=bundle, candidate=candidate)
    fragment_text = str(fragment.fragment_text if fragment else "") or ""
    if not fragment_text.strip():
        return JsonRepairChunkOutcome(
            candidate=candidate,
            repaired=False,
            repair_method=None,
            proposition_count=0,
            validation_errors=[],
            error="source fragment text unavailable",
        )

    parse_result = repair_extraction_json_text(candidate.raw_excerpt)
    if not parse_result.ok:
        return JsonRepairChunkOutcome(
            candidate=candidate,
            repaired=False,
            repair_method=parse_result.repair_method,
            proposition_count=0,
            validation_errors=[],
            error=parse_result.error or "JSON repair failed",
        )
    if not parse_result.raw_rows:
        return JsonRepairChunkOutcome(
            candidate=candidate,
            repaired=True,
            repair_method=parse_result.repair_method or "unknown",
            proposition_count=0,
            validation_errors=[],
            validated_rows=(),
        )

    limit = _extraction_limit(bundle)
    validated_rows, validation_errors = validate_repaired_rows(
        raw_rows=parse_result.raw_rows,
        fragment_text=fragment_text,
        limit=limit,
    )
    if not validated_rows:
        return JsonRepairChunkOutcome(
            candidate=candidate,
            repaired=False,
            repair_method=parse_result.repair_method,
            proposition_count=0,
            validation_errors=validation_errors,
            error="schema validation removed all rows",
        )

    return JsonRepairChunkOutcome(
        candidate=candidate,
        repaired=True,
        repair_method=parse_result.repair_method or "unknown",
        proposition_count=len(validated_rows),
        validation_errors=validation_errors,
        validated_rows=tuple(validated_rows),
    )


def _job_index(bundle: dict[str, Any]) -> dict[tuple[str, str | None], dict[str, Any]]:
    out: dict[tuple[str, str | None], dict[str, Any]] = {}
    for job in bundle.get("proposition_extraction_jobs") or []:
        if not isinstance(job, dict):
            continue
        sid = str(job.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = job.get("source_fragment_id")
        frag_id = str(frag_raw).strip() if frag_raw else None
        out[(sid, frag_id)] = job
    return out


def apply_json_repairs_to_bundle(
    *,
    bundle: dict[str, Any],
    outcomes: list[JsonRepairChunkOutcome],
    validated_rows_by_key: dict[tuple[str, str | None], list[dict[str, Any]]],
    repair_methods_by_key: dict[tuple[str, str | None], str],
) -> dict[str, Any]:
    updated = copy.deepcopy(bundle)
    job_by_key = _job_index(updated)
    repaired_keys: set[tuple[str, str | None]] = set()
    recovered_props: list[Proposition] = []

    for outcome in outcomes:
        if not outcome.repaired:
            continue
        key = outcome.candidate.job_key()
        repaired_keys.add(key)
        rows = validated_rows_by_key.get(key) or []
        method = repair_methods_by_key.get(key) or outcome.repair_method or "unknown"
        props = build_repaired_propositions(
            bundle=updated,
            candidate=outcome.candidate,
            validated_rows=rows,
            repair_method=method,
        )
        recovered_props.extend(props)

    if not repaired_keys:
        return updated

    kept_props: list[dict[str, Any]] = []
    for row in updated.get("propositions") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("source_record_id") or "").strip()
        frag_raw = row.get("source_fragment_id")
        frag_id = str(frag_raw).strip() if frag_raw else None
        if (sid, frag_id) in repaired_keys:
            continue
        kept_props.append(row)

    for prop in recovered_props:
        kept_props.append(prop.model_dump(mode="json"))

    updated["propositions"] = kept_props

    for key in repaired_keys:
        job = job_by_key.get(key)
        if not isinstance(job, dict):
            continue
        outcome = next(o for o in outcomes if o.candidate.job_key() == key and o.repaired)
        method = repair_methods_by_key.get(key) or outcome.repair_method or "unknown"
        job["repairable"] = False
        job["repair_reason"] = None
        job["proposition_count"] = outcome.proposition_count
        job["errors"] = []
        job["warnings"] = list(job.get("warnings") or [])
        job["json_repair_applied"] = True
        job["json_repair_method"] = method
        job["json_repair_source_trace_id"] = outcome.candidate.trace_id or outcome.candidate.job_id
        job["original_failure_type"] = outcome.candidate.failure_type
        job["original_raw_excerpt"] = outcome.candidate.raw_excerpt[:4000]

    return updated


def summarize_json_repair_run(
    *,
    candidates: list[JsonRepairCandidate],
    outcomes: list[JsonRepairChunkOutcome],
) -> dict[str, Any]:
    repaired = [o for o in outcomes if o.repaired]
    still_failed = [o for o in outcomes if not o.repaired]
    recovered = sum(o.proposition_count for o in repaired)
    return {
        "failed_chunks_considered": len(candidates),
        "repaired_chunks": len(repaired),
        "recovered_propositions": recovered,
        "still_failed_chunks": len(still_failed),
        "repaired_chunk_details": [
            {
                "source_record_id": o.candidate.source_record_id,
                "source_fragment_id": o.candidate.source_fragment_id,
                "fragment_locator": o.candidate.fragment_locator,
                "repair_method": o.repair_method,
                "proposition_count": o.proposition_count,
            }
            for o in repaired
        ],
        "still_failed_details": [
            {
                "source_record_id": o.candidate.source_record_id,
                "source_fragment_id": o.candidate.source_fragment_id,
                "fragment_locator": o.candidate.fragment_locator,
                "failure_type": o.candidate.failure_type,
                "error": o.error,
                "validation_errors": o.validation_errors,
            }
            for o in still_failed
        ],
    }


def run_extraction_json_repair_pipeline(
    *,
    export_dir: Path,
    output_dir: Path,
    use_llm_repair: bool = False,
) -> dict[str, Any]:
    from .linting import load_exported_bundle

    if use_llm_repair:
        raise NotImplementedError(
            "--use-llm-repair is reserved for a future model-backed repair pass; "
            "deterministic repair only is supported today."
        )

    root = Path(export_dir).expanduser()
    out_dir = Path(output_dir).expanduser()
    base_bundle = _enrich_bundle_from_export_files(load_exported_bundle(root), root)
    candidates = list_json_repair_candidates(base_bundle)
    outcomes: list[JsonRepairChunkOutcome] = []
    validated_rows_by_key: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    repair_methods_by_key: dict[tuple[str, str | None], str] = {}

    for candidate in candidates:
        outcome = attempt_json_repair_for_candidate(bundle=base_bundle, candidate=candidate)
        outcomes.append(outcome)
        if not outcome.repaired:
            continue
        key = candidate.job_key()
        validated_rows_by_key[key] = list(outcome.validated_rows)
        repair_methods_by_key[key] = outcome.repair_method or "unknown"

    summary = summarize_json_repair_run(candidates=candidates, outcomes=outcomes)
    repaired_bundle = apply_json_repairs_to_bundle(
        bundle=base_bundle,
        outcomes=outcomes,
        validated_rows_by_key=validated_rows_by_key,
        repair_methods_by_key=repair_methods_by_key,
    )

    run_existing = base_bundle.get("run") if isinstance(base_bundle.get("run"), dict) else {}
    base_run_id = str(run_existing.get("id") or "run-unknown")
    new_run_id = f"{base_run_id}-json-repaired-{uuid.uuid4().hex[:8]}"
    if isinstance(repaired_bundle.get("run"), dict):
        repaired_bundle["run"] = dict(repaired_bundle["run"])
        repaired_bundle["run"]["id"] = new_run_id

    repaired_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    repaired_bundle["extraction_json_repair_metadata"] = {
        "repaired_from_run_id": run_existing.get("id"),
        "repaired_from_export_dir": str(root.resolve()),
        "repaired_at": repaired_at,
        **summary,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    export_bundle(repaired_bundle, output_dir=str(out_dir.resolve()))
    return repaired_bundle


def run_cli_json_repair_pipeline(
    *,
    export_dir: Path,
    output_dir: Path,
    use_llm_repair: bool = False,
) -> dict[str, Any]:
    return run_extraction_json_repair_pipeline(
        export_dir=export_dir,
        output_dir=output_dir,
        use_llm_repair=use_llm_repair,
    )
