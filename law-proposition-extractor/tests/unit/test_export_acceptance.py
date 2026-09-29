"""Unit tests for export repair-and-acceptance workflow (no LLM)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from law_proposition_extractor_domain.enums import LegalEffectType, PropositionTier
from law_proposition_extractor_pipeline.export_acceptance import (
    ACCEPTANCE_JSON_FILENAME,
    backfill_evidence_from_alternate_meta,
    compute_acceptance_status,
    detect_repairable_issues,
    repair_application_scope_territory,
    repair_debug_leakage_in_review_notes,
    repair_dangerous_legacy_relationship_key,
    run_export_acceptance_workflow,
    run_proposition_quality_gates,
)
from law_proposition_extractor_domain import Proposition, SourceRecord
from law_proposition_extractor_pipeline.fresh_extraction_verification import build_fresh_extraction_verification

_PROP_DEFAULTS = {
    "topic_id": "topic-test",
    "cluster_id": "cluster-test",
    "legal_subject": "subject",
    "action": "means",
}


def _prop(**fields: object) -> Proposition:
    return Proposition.model_validate({**_PROP_DEFAULTS, **fields})


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "fresh_extraction_verification"
OK_EXPORT = FIXTURE_ROOT / "minimal_ok"


@pytest.fixture
def ok_export(tmp_path: Path) -> Path:
    dest = tmp_path / "export"
    shutil.copytree(OK_EXPORT, dest)
    return dest


def test_clean_export_accepted(ok_export: Path) -> None:
    report = run_export_acceptance_workflow(
        export_dir=ok_export,
        auto_repair=True,
        acceptance_report=True,
        repair_mode="deterministic",
        use_llm_coverage=False,
    )
    assert report.acceptance_status in {"accepted", "accepted_with_warnings"}
    assert (ok_export / ACCEPTANCE_JSON_FILENAME).is_file()


def test_unknown_definition_classifier_repair(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    rows[0]["label"] = "Definition: slurry"
    rows[0]["proposition_text"] = '"slurry" means livestock excreta.'
    rows[0]["proposition_tier"] = "unknown"
    rows[0]["legal_effect_type"] = "unknown"
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    report = run_export_acceptance_workflow(
        export_dir=ok_export,
        auto_repair=True,
        acceptance_report=True,
        repair_mode="deterministic",
        use_llm_coverage=False,
    )
    assert report.acceptance_status in {"accepted", "accepted_with_warnings"}
    repaired = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    assert repaired[0]["legal_effect_type"] == LegalEffectType.DEFINITION.value


def test_missing_evidence_copied_from_alternate_meta() -> None:
    prop = _prop(
        id="prop-test",
        source_record_id="lex-1",
        fragment_locator="regulation 1",
        jurisdiction="UK",
        proposition_text="Test text.",
        label="Test",
        extraction_debug_meta={"verbatim_evidence": "Test text."},
    )
    assert backfill_evidence_from_alternate_meta(prop)
    meta = prop.extraction_debug_meta or {}
    assert meta.get("evidence_quote") == "Test text."


def test_application_scope_territory_inherited() -> None:
    prop = Proposition.model_construct(
        id="prop-scope",
        topic_id="topic-test",
        cluster_id="cluster-test",
        source_record_id="lex-1",
        fragment_locator="regulation 1(d)",
        jurisdiction="UK",
        legal_subject="these regulations",
        action="apply to",
        proposition_text="These Regulations apply to agricultural land in England.",
        label="Application to England",
        proposition_tier=PropositionTier.SCOPE_RULE,
        legal_effect_type=LegalEffectType.APPLICATION_SCOPE,
        territorial_application=[],
    )
    source = SourceRecord.model_validate(
        {
            "id": "lex-1",
            "title": "Test Regs",
            "jurisdiction": "UK",
            "citation": "Test Regs",
            "kind": "regulation",
            "metadata": {"extent": "England"},
        }
    )
    assert repair_application_scope_territory(prop, source=source, instrument_extent=["England"])
    assert prop.territorial_application == ["England"]


def test_dangerous_key_repaired() -> None:
    prop = _prop(
        id="prop-key",
        source_record_id="lex-120b4f9c395b3f94",
        fragment_locator="regulation 1",
        jurisdiction="UK",
        proposition_text="Must comply.",
        label="Duty",
        legal_subject="occupier",
        action="must",
        proposition_tier=PropositionTier.SUBSTANTIVE_RULE.value,
        legal_effect_type=LegalEffectType.OBLIGATION.value,
        cross_reference_key="uk:these-regulations:must-ensure",
    )
    assert repair_dangerous_legacy_relationship_key(prop)
    assert not str(prop.cross_reference_key or "").startswith("uk:these-regulations")


def test_debug_leakage_repaired() -> None:
    prop = _prop(
        id="prop-leak",
        source_record_id="lex-1",
        fragment_locator="regulation 1",
        jurisdiction="UK",
        proposition_text="Text.",
        label="Label",
        review_notes='Note judit_extraction_meta:{"x":1}',
    )
    assert repair_debug_leakage_in_review_notes(prop)
    assert "judit_extraction_meta" not in str(prop.review_notes or "")


def test_dangerous_key_fails_without_repair(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    rows[0]["cross_reference_key"] = "uk:these-regulations:must-ensure"
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    report = run_export_acceptance_workflow(
        export_dir=ok_export,
        auto_repair=False,
        acceptance_report=True,
        repair_mode="deterministic",
        use_llm_coverage=False,
    )
    assert report.acceptance_status == "failed"


def test_missing_anchor_needs_review_without_llm(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    for row in rows:
        row["source_record_id"] = "lex-120b4f9c395b3f94"
        row["fragment_locator"] = "regulation 2"
        row["proposition_text"] = "Unrelated text without definition anchors."
        row["label"] = "Other"
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    bundle = {
        "propositions": rows,
        "source_fragments": [
            {
                "id": "frag-reg2",
                "source_record_id": "lex-120b4f9c395b3f94",
                "locator": "regulation:2",
                "fragment_text": (
                    '"slurry" means livestock excreta; "organic manure" means fertiliser; '
                    '"agricultural" has the meaning given; "spreading" includes applying.'
                ),
            }
        ],
    }
    issues = detect_repairable_issues(
        bundle=bundle,
        verification=build_fresh_extraction_verification(ok_export, propositions=rows),
    )
    assert any(i.check_id in {"missing_definition_anchor", "missing_fragment_anchor"} for i in issues)

    report = run_export_acceptance_workflow(
        export_dir=ok_export,
        auto_repair=True,
        acceptance_report=True,
        repair_mode="deterministic",
        use_llm_coverage=False,
    )
    assert report.acceptance_status == "needs_review"
    assert any("agricultural" in w for w in report.remaining_human_review_warnings)


def test_compute_acceptance_failed_on_zero_propositions(ok_export: Path) -> None:
    verification = build_fresh_extraction_verification(ok_export, propositions=[])
    quality = run_proposition_quality_gates([], newly_normalised=True)
    status, hard, _human, _warnings = compute_acceptance_status(
        proposition_count=0,
        verification=verification,
        quality=quality,
        issues_after=[],
        anchor_summary={"anchors": {}},
    )
    assert status == "failed"
    assert "no_propositions" in hard
