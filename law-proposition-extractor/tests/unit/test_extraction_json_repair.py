"""Tests for deterministic JSON extraction repair."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.extraction_json_repair import (
    JsonRepairCandidate,
    attempt_json_repair_for_candidate,
    list_json_repair_candidates,
    parse_extraction_json,
    repair_extraction_json_text,
    run_extraction_json_repair_pipeline,
    salvage_complete_proposition_objects,
    strip_markdown_json_fence,
)
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_domain import resolve_extraction_meta_for_proposition
from law_proposition_extractor_pipeline.intake import content_hash
from law_proposition_extractor_pipeline.linting import load_exported_bundle


def _valid_prop(*, evidence: str, locator: str = "regulation:1") -> dict:
    return {
        "proposition_text": "Operators must keep register entries.",
        "display_label": "Register entries",
        "subject": "operators",
        "rule": "must keep register entries",
        "object": "",
        "conditions": [],
        "exceptions": [],
        "temporal_condition": "",
        "provision_type": "core",
        "source_locator": locator,
        "evidence_text": evidence,
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "test fixture",
    }


FRAGMENT_TEXT = (
    "Regulation 1. Operators must keep register entries for passport control "
    "and identification document checks."
)


def _repair_bundle(*, excerpt: str, parse_error: str = "Expecting ',' delimiter") -> dict:
    return {
        "run": {"id": "run-json-repair", "workflow_mode": "single_jurisdiction"},
        "topic": {"id": "topic-1", "name": "T", "description": "", "subject_tags": []},
        "clusters": [{"id": "cluster-1", "topic_id": "topic-1", "name": "C", "description": ""}],
        "source_records": [
            {
                "id": "src-a",
                "title": "Source A",
                "jurisdiction": "GB",
                "citation": "GB-TEST",
                "kind": "regulation",
                "authoritative_locator": "regulation:1",
                "current_snapshot_id": "snap-a",
            }
        ],
        "source_fragments": [
            {
                "id": "frag-a",
                "source_record_id": "src-a",
                "source_snapshot_id": "snap-a",
                "locator": "regulation:1",
                "fragment_text": FRAGMENT_TEXT,
                "fragment_hash": content_hash(FRAGMENT_TEXT),
            }
        ],
        "propositions": [],
        "proposition_extraction_traces": [],
        "proposition_extraction_jobs": [
            {
                "id": "job-json",
                "selected_for_extraction": True,
                "source_record_id": "src-a",
                "source_fragment_id": "frag-a",
                "fragment_locator": "regulation:1",
                "llm_invoked": True,
                "proposition_count": 0,
                "repairable": True,
                "repair_reason": "json_parse_or_llm_failure",
                "raw_model_output_excerpt": excerpt,
                "parse_error_message": parse_error,
                "errors": ["chunk 1/1: model call or JSON parse failed: " + parse_error],
            }
        ],
        "extraction_llm_call_traces": [
            {
                "id": "trace-json",
                "source_record_id": "src-a",
                "source_fragment_id": "frag-a",
                "fragment_locator": "regulation:1",
                "failure_type": "non_json_response",
                "failure_reason": "model returned non-JSON or unparseable JSON",
                "raw_model_output_excerpt": excerpt,
                "parse_error_message": parse_error,
                "llm_call_succeeded": False,
            }
        ],
        "divergence_assessments": [],
        "divergence_observations": [],
        "divergence_findings": [],
        "narrative": {"title": "N", "summary": "S", "sections": []},
    }


def test_strip_markdown_json_fence_removes_open_and_trailing_fence() -> None:
    raw = """```json
{"propositions": []}
```
extra"""
    assert strip_markdown_json_fence(raw).startswith('{"propositions"')


def test_repair_fenced_json_with_valid_content() -> None:
    payload = {"propositions": [_valid_prop(evidence=FRAGMENT_TEXT.split(". ", 1)[1])]}
    raw = "```json\n" + json.dumps(payload) + "\n```"
    result = repair_extraction_json_text(raw)
    assert result.ok is True
    assert result.repair_method == "strip_fenced_json"
    assert len(result.raw_rows) == 1


def test_repair_json_with_unescaped_quotes_in_evidence_text() -> None:
    broken = {
        "propositions": [
            {
                **_valid_prop(evidence='Operators must keep "register" entries.'),
            }
        ]
    }
    raw = json.dumps(broken).replace('\\"register\\"', '"register"')
    result = repair_extraction_json_text(raw)
    assert result.ok is True
    assert result.repair_method == "fix_unescaped_quotes"
    assert result.raw_rows[0]["evidence_text"] == 'Operators must keep "register" entries.'


def test_repair_json_with_leading_prose() -> None:
    payload = {"propositions": [_valid_prop(evidence=FRAGMENT_TEXT.split(". ", 1)[1])]}
    raw = "Here is the JSON you asked for:\n" + json.dumps(payload)
    result = repair_extraction_json_text(raw)
    assert result.ok is True
    assert result.repair_method in {"extract_json_substring", "strip_fenced_json", "direct_parse"}


def test_salvage_complete_objects_from_truncated_fenced_json() -> None:
    prop = _valid_prop(evidence=FRAGMENT_TEXT.split(". ", 1)[1])
    prop_two = {
        **_valid_prop(evidence=FRAGMENT_TEXT.split(". ", 1)[1], locator="regulation:2"),
        "proposition_text": "Operators must maintain identification records.",
    }
    full = {"propositions": [prop, prop_two]}
    raw = "```json\n" + json.dumps(full)
    raw = raw[: raw.index(prop_two["proposition_text"]) + 40]
    salvaged = salvage_complete_proposition_objects(raw)
    assert salvaged is not None
    assert len(salvaged["propositions"]) == 1
    result = repair_extraction_json_text(raw)
    assert result.ok is True
    assert result.repair_method in {
        "salvage_complete_objects",
        "close_truncated_json",
        "fix_unescaped_and_close_truncated",
    }
    assert len(result.raw_rows) >= 1


def test_list_json_repair_candidates_filters_json_parse_failures() -> None:
    excerpt = "```json\n" + json.dumps({"propositions": []}) + "\n```"
    bundle = _repair_bundle(excerpt=excerpt)
    candidates = list_json_repair_candidates(bundle)
    assert len(candidates) == 1
    assert candidates[0].failure_type == "json_parse_or_llm_failure"
    assert candidates[0].raw_excerpt.startswith("```json")


def test_attempt_json_repair_validates_through_proposition_schema() -> None:
    prop = _valid_prop(evidence=FRAGMENT_TEXT.split(". ", 1)[1])
    excerpt = "```json\n" + json.dumps({"propositions": [prop]}) + "\n```"
    bundle = _repair_bundle(excerpt=excerpt)
    candidate = list_json_repair_candidates(bundle)[0]
    outcome = attempt_json_repair_for_candidate(bundle=bundle, candidate=candidate)
    assert outcome.repaired is True
    assert outcome.proposition_count == 1
    assert outcome.repair_method == "strip_fenced_json"


def test_attempt_json_repair_preserves_provenance_fields() -> None:
    prop = _valid_prop(evidence=FRAGMENT_TEXT.split(". ", 1)[1])
    excerpt = "```json\n" + json.dumps({"propositions": [prop]}) + "\n```"
    bundle = _repair_bundle(excerpt=excerpt)
    candidate = list_json_repair_candidates(bundle)[0]
    outcome = attempt_json_repair_for_candidate(bundle=bundle, candidate=candidate)
    assert outcome.repaired is True
    from law_proposition_extractor_pipeline.extraction_json_repair import build_repaired_propositions

    props = build_repaired_propositions(
        bundle=bundle,
        candidate=candidate,
        validated_rows=list(outcome.validated_rows),
        repair_method=str(outcome.repair_method),
    )
    p0 = props[0]
    meta = resolve_extraction_meta_for_proposition(
        notes=p0.notes,
        extraction_debug_meta=p0.extraction_debug_meta,
    )
    assert meta is not None
    assert meta["repair_method"] == "strip_fenced_json"
    assert meta["original_failure_type"] == "json_parse_or_llm_failure"
    assert meta["repair_source_trace_id"] in {"job-json", "trace-json"}
    assert meta["original_raw_excerpt"].startswith("```json")


def test_run_extraction_json_repair_pipeline_exports_repaired_bundle(tmp_path: Path) -> None:
    prop = _valid_prop(evidence=FRAGMENT_TEXT.split(". ", 1)[1])
    excerpt = "```json\n" + json.dumps({"propositions": [prop]}) + "\n```"
    bundle = _repair_bundle(excerpt=excerpt)
    export_in = tmp_path / "in"
    export_out = tmp_path / "out"
    export_bundle(bundle, output_dir=str(export_in))

    repaired = run_extraction_json_repair_pipeline(
        export_dir=export_in,
        output_dir=export_out,
        use_llm_repair=False,
    )
    meta = repaired["extraction_json_repair_metadata"]
    assert meta["failed_chunks_considered"] == 1
    assert meta["repaired_chunks"] == 1
    assert meta["recovered_propositions"] == 1
    assert meta["still_failed_chunks"] == 0

    loaded = load_exported_bundle(export_out)
    assert len(loaded["propositions"]) == 1
    jobs = loaded["proposition_extraction_jobs"]
    assert jobs[0]["json_repair_applied"] is True
    assert jobs[0]["proposition_count"] == 1
    assert jobs[0]["repairable"] is False


def test_use_llm_repair_flag_is_not_implemented(tmp_path: Path) -> None:
    bundle = _repair_bundle(excerpt='{"propositions": []}')
    export_in = tmp_path / "in"
    export_out = tmp_path / "out"
    export_bundle(bundle, output_dir=str(export_in))
    with pytest.raises(NotImplementedError):
        run_extraction_json_repair_pipeline(
            export_dir=export_in,
            output_dir=export_out,
            use_llm_repair=True,
        )


def test_still_failed_when_excerpt_is_not_recoverable() -> None:
    bundle = _repair_bundle(excerpt="{not-valid-json", parse_error="Expecting property name")
    candidate = JsonRepairCandidate(
        job_id="job-json",
        trace_id="trace-json",
        source_record_id="src-a",
        source_fragment_id="frag-a",
        fragment_locator="regulation:1",
        failure_type="non_json_response",
        repair_reason="json_parse_or_llm_failure",
        raw_excerpt="{not-valid-json",
        parse_error_message="Expecting property name",
    )
    outcome = attempt_json_repair_for_candidate(bundle=bundle, candidate=candidate)
    assert outcome.repaired is False
    assert outcome.error


def test_repair_npp_style_unescaped_statutory_quote_in_evidence_text() -> None:
    broken = (
        '{"propositions": [{"proposition_text": "Slurry means liquid or semi-liquid matter '
        'composed of excreta...", "evidence_text": ""slurry" means excreta produced by livestock."}]}'
    )
    result = repair_extraction_json_text(broken)
    assert result.ok is True
    assert result.repair_method in {"fix_unescaped_quotes", "salvage_complete_objects"}
    assert result.raw_rows
    assert result.raw_rows[0]["evidence_text"].startswith('"slurry" means')


def test_repair_empty_propositions_with_trailing_prose() -> None:
    raw = '{"propositions": []}\nThis schedule only contains a reference table...'
    result = repair_extraction_json_text(raw)
    assert result.ok is True
    assert result.repair_method == "strip_trailing_prose"
    assert result.raw_rows == []


def test_repair_fenced_json_with_trailing_prose() -> None:
    raw = '```json\n{"propositions": []}\n```\nThe model returned no rows because...'
    result = repair_extraction_json_text(raw)
    assert result.ok is True
    assert result.repair_method in {"strip_fenced_json", "strip_trailing_prose", "direct_parse"}
    assert result.raw_rows == []


def test_parse_extraction_json_records_repair_metadata() -> None:
    raw = '{"propositions": [{"proposition_text": "x", "evidence_text": ""term" means y."}]}'
    parsed = parse_extraction_json(raw)
    assert parsed.json_repair_applied is True
    assert parsed.json_repair_method
    assert parsed.parsed["propositions"][0]["evidence_text"].startswith('"term"')
