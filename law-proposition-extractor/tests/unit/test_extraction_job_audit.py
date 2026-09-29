import json
from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.runner import _normalize_locator_for_match, build_bundle_from_case


@pytest.fixture(autouse=True)
def _noop_llm_preflight_in_unit_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests use fakes or no LiteLLM proxy; preflight is covered in test_llm_extraction_config."""
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.runner.preflight_llm_extraction",
        lambda _client, _mode: None,
    )


class _FakeLlmClient:
    def __init__(self) -> None:
        class _Settings:
            frontier_extract_model = "frontier_extract"
            local_extract_model = "local_extract"
            max_extract_input_tokens = 150_000
            extract_model_context_limit = 200_000
            skip_llm_preflight = True

        self.settings = _Settings()
        self.calls = 0

    def complete_text(self, *_args: object, **_kwargs: object) -> str:
        self.calls += 1
        return json.dumps(
            {
                "propositions": [
                    {
                        "proposition_text": "Operators must keep register entries.",
                        "display_label": "Register entries",
                        "subject": "operators",
                        "rule": "must keep register entries",
                        "object": "",
                        "conditions": [],
                        "exceptions": [],
                        "temporal_condition": "",
                        "provision_type": "core",
                        "source_locator": "document:full",
                        "evidence_text": (
                            "Operators must keep register entries for passport control "
                            "and identification document checks."
                        ),
                        "completeness_status": "complete",
                        "confidence": "high",
                        "reason": "fake llm",
                    }
                ]
            }
        )


def _case_data() -> dict:
    return {
        "topic": {"name": "Passport extraction", "description": "", "subject_tags": ["equine"]},
        "cluster": {"name": "passport", "description": ""},
        "analysis_mode": "single_jurisdiction",
        "sources": [
            {
                "id": "src-article-1",
                "title": "Article 1",
                "jurisdiction": "EU",
                "citation": "EU-2015-262-A1",
                "kind": "regulation",
                "fragment_locator": "article:1",
                "text": "Article 1. Operators must keep register entries for passport control and identification document checks.",
            },
            {
                "id": "src-article-4",
                "title": "Article 4",
                "jurisdiction": "EU",
                "citation": "EU-2015-262-A4",
                "kind": "regulation",
                "fragment_locator": "article:4",
                "text": "Article 4. Operators must keep register entries and maintain competent authority records.",
            },
            {
                "id": "src-annex-i",
                "title": "Annex I",
                "jurisdiction": "EU",
                "citation": "EU-2015-262-ANNEX-I",
                "kind": "regulation",
                "fragment_locator": "annex:i",
                "text": "Annex I. Operators must keep register entries for transponder mapping.",
            },
            {
                "id": "src-article-10",
                "title": "Article 10",
                "jurisdiction": "EU",
                "citation": "EU-2015-262-A10",
                "kind": "regulation",
                "fragment_locator": "article:10",
                "text": "Article 10. This covers movement logs.",
            },
            {
                "id": "src-article-99",
                "title": "Article 99",
                "jurisdiction": "EU",
                "citation": "EU-2015-262-A99",
                "kind": "regulation",
                "fragment_locator": "article:99",
                "text": "Article 99. General publication notes and formatting statements with no operational terms.",
            },
        ],
        "comparison": {"jurisdiction_a": "EU", "jurisdiction_b": "EU", "proposition_index": 1},
        "narrative": {"title": "Narrative", "summary": "Summary"},
        "extraction": {
            "focus_terms": ["passport", "identification document", "transponder"],
            "required_fragment_locators": ["article:4"],
            "include_annexes": True,
            "fragment_selection_mode": "all_matching",
            "max_propositions_per_source": 3,
        },
    }


def test_proposition_extraction_jobs_audit_and_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)

    bundle = build_bundle_from_case(
        case_data=_case_data(),
        use_llm=True,
        extraction_mode="frontier",
        extraction_fallback="fallback",
        divergence_reasoning="none",
        derived_cache_dir=str(tmp_path / "derived-cache-audit"),
    )

    jobs = bundle.get("proposition_extraction_jobs")
    assert isinstance(jobs, list)
    assert len(jobs) == len(bundle.get("source_fragments", []))
    assert all("selected_for_extraction" in row for row in jobs)
    assert all("skip_reason" in row for row in jobs)

    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    assert by_locator["article:1"]["selected_for_extraction"] is True
    assert by_locator["article:1"]["selection_reason"] == "focus_term_match"
    assert by_locator["article:4"]["selected_for_extraction"] is True
    assert by_locator["article:4"]["selection_reason"] == "required_locator"
    assert by_locator["annex:i"]["selected_for_extraction"] is True
    assert by_locator["annex:i"]["selection_reason"] == "annex_included"
    assert by_locator["article:10"]["selected_for_extraction"] is False
    assert by_locator["article:10"]["skip_reason"] in {"no_focus_match", "too_short"}
    assert by_locator["article:99"]["selected_for_extraction"] is False
    assert by_locator["article:99"]["skip_reason"] in {"no_focus_match", "non_operative"}

    invoked_jobs = [row for row in jobs if row.get("llm_invoked") is True]
    assert fake.calls == len(invoked_jobs)
    assert len({str(p["id"]) for p in bundle["propositions"]}) == len(bundle["propositions"])
    traces = bundle["proposition_extraction_traces"]
    assert len({str(t["id"]) for t in traces}) == len(traces)


def test_locator_matching_is_exact_and_canonical() -> None:
    assert _normalize_locator_for_match("article:01") == "article:1"
    assert _normalize_locator_for_match("article:1") == "article:1"
    assert _normalize_locator_for_match("article:10") == "article:10"
    assert _normalize_locator_for_match("article:1|chunk:001") == "article:1"
    assert _normalize_locator_for_match("annex:I") == "annex:i"
    assert _normalize_locator_for_match("annex:ii") == "annex:ii"
    assert _normalize_locator_for_match("article:1") != _normalize_locator_for_match("article:10")


class _FakeRepairableLlmClient(_FakeLlmClient):
    def complete_text(self, *_args: object, **_kwargs: object) -> str:
        self.calls += 1
        if self.calls == 2:
            return "{not-valid-json"
        return json.dumps(
            {
                "propositions": [
                    {
                        "proposition_text": "Operators must keep register entries.",
                        "display_label": "Register entries",
                        "subject": "operators",
                        "rule": "must keep register entries",
                        "object": "",
                        "conditions": [],
                        "exceptions": [],
                        "temporal_condition": "",
                        "provision_type": "core",
                        "source_locator": "document:full",
                        "evidence_text": (
                            "Operators must keep register entries for passport control "
                            "and identification document checks."
                        ),
                        "completeness_status": "complete",
                        "confidence": "high",
                        "reason": "fake llm",
                    }
                ]
            }
        )


class _FakeLongInvalidJsonRepairableLlmClient(_FakeLlmClient):
    def complete_text(self, *_args: object, **_kwargs: object) -> str:
        self.calls += 1
        if self.calls == 1:
            return (
                "Authorization: Bearer sk-live-super-secret\n"
                "x-api-key: test-key-123\n"
                "{not-valid-json"
                + ("X" * 7000)
            )
        return super().complete_text(*_args, **_kwargs)


def test_repairable_failure_is_surface_on_job_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeRepairableLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)
    case_data = _case_data()
    case_data["extraction"]["required_fragment_locators"] = ["article:1", "article:4"]
    case_data["extraction"]["focus_terms"] = []
    case_data["extraction"]["model_error_policy"] = "stop_repairable"
    case_data["extraction"]["include_annexes"] = False
    for source in case_data["sources"]:
        if source["id"] == "src-article-4":
            source["text"] = "Article 4. Bad payload trigger text for repair path and authority sync."
            break

    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=True,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
        derived_cache_dir=str(tmp_path / "derived-cache-repairable"),
    )

    jobs = bundle.get("proposition_extraction_jobs") or []
    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    failed = by_locator["article:4"]
    assert failed["selected_for_extraction"] is True
    assert failed["llm_invoked"] is True
    assert failed["proposition_count"] == 0
    assert failed["repairable"] is True
    assert failed["repair_reason"] == "json_parse_or_llm_failure"
    assert failed["errors"]
    assert failed["estimated_retry_tokens"] is not None
    assert failed["model_alias"] == "frontier_extract"
    assert failed["source_fragment_id"] is not None
    assert failed["fragment_locator"] == "article:4"
    assert isinstance(failed.get("raw_model_output_excerpt"), str)
    assert str(failed["raw_model_output_excerpt"]).startswith("{not-valid-json")
    assert len(str(failed["raw_model_output_excerpt"])) <= 4000
    assert failed["raw_model_output_truncated"] is False
    assert isinstance(failed.get("parse_error_message"), str)
    assert failed.get("parse_error_line") == 1
    assert failed.get("parse_error_column") == 2


def test_repairable_failure_truncates_and_redacts_raw_model_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeLongInvalidJsonRepairableLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)
    case_data = _case_data()
    case_data["extraction"]["required_fragment_locators"] = ["article:1"]
    case_data["extraction"]["focus_terms"] = []
    case_data["extraction"]["model_error_policy"] = "stop_repairable"
    case_data["extraction"]["include_annexes"] = False

    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=True,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
        derived_cache_dir=str(tmp_path / "derived-cache-repairable-redact"),
    )

    jobs = bundle.get("proposition_extraction_jobs") or []
    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    failed = by_locator["article:1"]
    assert failed["repair_reason"] == "json_parse_or_llm_failure"
    excerpt = str(failed.get("raw_model_output_excerpt") or "")
    assert excerpt
    assert len(excerpt) == 4000
    assert failed["raw_model_output_truncated"] is True
    assert "sk-live-super-secret" not in excerpt
    assert "test-key-123" not in excerpt
    assert "[REDACTED]" in excerpt


def test_stop_repairable_marks_later_jobs_as_unprocessed_with_skip_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeRepairableLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)
    case_data = _case_data()
    case_data["extraction"]["required_fragment_locators"] = ["article:1", "article:4", "article:10"]
    case_data["extraction"]["focus_terms"] = []
    case_data["extraction"]["model_error_policy"] = "stop_repairable"
    case_data["extraction"]["include_annexes"] = False

    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=True,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
        derived_cache_dir=str(tmp_path / "derived-cache-stop-policy"),
    )

    jobs = bundle.get("proposition_extraction_jobs") or []
    assert len(jobs) == len(bundle.get("source_fragments", []))
    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    assert by_locator["article:4"]["repairable"] is True
    assert by_locator["article:10"]["selected_for_extraction"] is False
    assert by_locator["article:10"]["skip_reason"] == "model_error_policy_stop_repairable"
    assert by_locator["article:10"]["llm_invoked"] is False


def test_continue_repairable_policy_continues_after_repairable_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeRepairableLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)
    case_data = _case_data()
    case_data["extraction"]["required_fragment_locators"] = ["article:1", "article:4", "article:10"]
    case_data["extraction"]["focus_terms"] = []
    case_data["extraction"]["model_error_policy"] = "continue_repairable"
    case_data["extraction"]["include_annexes"] = False

    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=True,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
        derived_cache_dir=str(tmp_path / "derived-cache-continue-policy"),
    )

    jobs = bundle.get("proposition_extraction_jobs") or []
    assert len(jobs) == len(bundle.get("source_fragments", []))
    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    assert by_locator["article:4"]["repairable"] is True
    assert by_locator["article:10"]["selected_for_extraction"] is True
    assert by_locator["article:10"]["llm_invoked"] is True
    assert by_locator["article:10"]["skip_reason"] is None


def test_missing_required_locators_are_reported() -> None:
    case_data = _case_data()
    case_data["extraction"]["required_fragment_locators"] = ["article:4", "annex:iii"]
    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=False,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
    )
    assert bundle.get("missing_required_fragment_locators") == ["annex:iii"]


def test_required_only_selects_required_locators_only() -> None:
    case_data = _case_data()
    case_data["extraction"]["fragment_selection_mode"] = "required_only"
    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=False,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
    )
    jobs = bundle.get("proposition_extraction_jobs") or []
    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    assert by_locator["article:4"]["selected_for_extraction"] is True
    assert by_locator["article:4"]["selection_reason"] == "required_locator"
    assert by_locator["annex:i"]["selected_for_extraction"] is True
    assert by_locator["annex:i"]["selection_reason"] == "annex_included"
    assert by_locator["article:1"]["selected_for_extraction"] is False
    assert by_locator["article:1"]["skip_reason"] == "skipped_not_required_in_required_only_mode"


def test_required_plus_focus_selects_required_plus_focus_matches() -> None:
    case_data = _case_data()
    case_data["extraction"]["fragment_selection_mode"] = "required_plus_focus"
    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=False,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
    )
    jobs = bundle.get("proposition_extraction_jobs") or []
    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    assert by_locator["article:4"]["selected_for_extraction"] is True
    assert by_locator["article:1"]["selected_for_extraction"] is True
    assert by_locator["article:1"]["selection_reason"] == "focus_term_match"
    assert by_locator["article:10"]["selected_for_extraction"] is False
    assert by_locator["article:10"]["skip_reason"] == "no_focus_match"


def test_all_matching_preserves_current_behaviour_for_non_focus_fragments() -> None:
    case_data = _case_data()
    case_data["extraction"]["fragment_selection_mode"] = "all_matching"
    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=False,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
    )
    jobs = bundle.get("proposition_extraction_jobs") or []
    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    assert by_locator["article:10"]["selected_for_extraction"] is False
    assert by_locator["article:10"]["skip_reason"] in {"too_short", "no_focus_match"}


def test_definition_fallback_job_row_tracks_strategy_and_multi_prop_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _FailingDefinitionClient(_FakeLlmClient):
        def complete_text(self, *_args: object, **_kwargs: object) -> str:
            self.calls += 1
            return "{not-valid-json"

    fake = _FailingDefinitionClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)
    case_data = {
        "topic": {"name": "Passport definitions", "description": "", "subject_tags": ["equine"]},
        "cluster": {"name": "passport-defs", "description": ""},
        "analysis_mode": "single_jurisdiction",
        "sources": [
            {
                "id": "src-article-2",
                "title": "Article 2",
                "jurisdiction": "EU",
                "citation": "EU-2015-262-A2",
                "kind": "regulation",
                "fragment_locator": "article:2",
                "text": (
                    "Article 2\n"
                    "For the purposes of this Regulation, the following definitions shall apply:\n"
                    "'equidae' or 'equine animals' means animals of domestic or wild species of the family Equidae;\n"
                    "'keeper' means a natural or legal person having permanent or temporary responsibility for equidae;\n"
                    "'transponder' means a read-only passive radio-frequency identification device."
                ),
            }
        ],
        "comparison": {"jurisdiction_a": "EU", "jurisdiction_b": "EU", "proposition_index": 1},
        "narrative": {"title": "Narrative", "summary": "Summary"},
        "extraction": {
            "required_fragment_locators": ["article:2"],
            "focus_terms": [],
            "fragment_selection_mode": "required_only",
            "max_propositions_per_source": 8,
        },
    }
    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=True,
        extraction_mode="frontier",
        divergence_reasoning="none",
        extraction_fallback="mark_needs_review",
        derived_cache_dir=str(tmp_path / "derived-cache-definition-fallback"),
    )
    jobs = bundle.get("proposition_extraction_jobs") or []
    by_locator = {str(row.get("fragment_locator")): row for row in jobs}
    row = by_locator["article:2"]
    assert row["selected_for_extraction"] is True
    assert row["llm_invoked"] is True
    assert row["fallback_used"] is True
    assert row["fallback_strategy"] == "definition_extractor"
    assert row["repairable"] is True
    assert row["repair_reason"] == "json_parse_or_llm_failure"
    assert int(row["proposition_count"]) > 1
    traces = [
        tr
        for tr in (bundle.get("proposition_extraction_traces") or [])
        if str(tr.get("source_record_id")) == "src-article-2"
    ]
    assert len(traces) > 1
    assert len({str(tr.get("id")) for tr in traces}) == len(traces)


def test_load_old_export_without_extraction_jobs_file(tmp_path: Path) -> None:
    from law_proposition_extractor_pipeline.linting import load_exported_bundle

    (tmp_path / "run.json").write_text('{"id":"run-old-002"}', encoding="utf-8")
    (tmp_path / "sources.json").write_text("[]", encoding="utf-8")
    (tmp_path / "propositions.json").write_text("[]", encoding="utf-8")
    for name in (
        "source_snapshots.json",
        "source_fragments.json",
        "source_parse_traces.json",
        "source_fetch_metadata.json",
        "source_fetch_attempts.json",
        "source_target_links.json",
        "source_inventory.json",
        "source_categorisation_rationales.json",
        "proposition_extraction_traces.json",
        "divergence_observations.json",
        "divergence_assessments.json",
        "divergence_findings.json",
        "run_artifacts.json",
        "legal_scopes.json",
        "proposition_scope_links.json",
        "scope_inventory.json",
        "scope_review_candidates.json",
    ):
        payload = "{}" if name in {"source_inventory.json", "scope_inventory.json"} else "[]"
        (tmp_path / name).write_text(payload, encoding="utf-8")
    loaded = load_exported_bundle(tmp_path)
    assert loaded.get("proposition_extraction_jobs") == []
