"""Prompt-lab single-fragment extraction workbench (no LLM in dry mode)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.extraction_workbench import (
    EXTRACTION_TRACE_JSON,
    FRAGMENT_TXT,
    MODEL_MD,
    PARSED_EXTRACTION_JSON,
    PROMPT_TXT,
    PROPOSITIONS_NORMALISED_JSON,
    PROPOSITIONS_RAW_JSON,
    RAW_MODEL_OUTPUT_TXT,
    REVIEW_MD,
    WORKBENCH_OUTPUT_FILENAMES,
    build_fragment_review_markdown,
    load_extraction_fixture,
    load_prompt_lab_fixture,
    run_extract_fragment_workbench,
    write_extract_fragment_workbench_outputs,
)

SLURRY_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "extraction_prompt_cases" / "slurry"
DRY_FIXTURE = SLURRY_FIXTURES / "_workbench_dry_smoke.json"
PROMPT_LAB_FIXTURE = SLURRY_FIXTURES / "slurry-bad-diffuse-2018-reg-1-boilerplate.json"


def test_load_prompt_lab_fixture() -> None:
    data = load_prompt_lab_fixture(PROMPT_LAB_FIXTURE)
    assert data["case_id"] == "slurry-bad-diffuse-2018-reg-1-boilerplate"
    assert len(data["expected_propositions"]) >= 4
    assert data["expected_challenges"]


def test_load_extraction_fixture_from_prompt_lab_schema() -> None:
    ctx = load_extraction_fixture(PROMPT_LAB_FIXTURE)
    assert ctx.source_id == "lex-2459c955ee13be52"
    assert ctx.fragment_locator == "regulation:1"
    assert "agricultural land in England" in ctx.fragment_text
    assert ctx.work_source.metadata.get("prompt_lab_case_id")


def test_all_slurry_prompt_lab_fixtures_validate() -> None:
    paths = sorted(SLURRY_FIXTURES.glob("slurry-*.json"))
    assert len(paths) == 11
    for path in paths:
        data = load_prompt_lab_fixture(path)
        assert data["fragment_text"].strip()


def test_dry_workbench_writes_all_artifacts(tmp_path: Path) -> None:
    result = run_extract_fragment_workbench(
        fixture_path=DRY_FIXTURE,
        extraction_mode="dry",
    )
    assert result.extraction_mode == "dry"
    assert len(result.parsed_extraction_rows) >= 1
    assert len(result.raw_propositions) >= 1
    assert len(result.normalised_propositions) >= 1
    assert result.fragment_text in result.user_prompt
    assert "=== system ===" not in result.user_prompt

    out = write_extract_fragment_workbench_outputs(result, tmp_path)
    assert out == tmp_path.resolve()

    for name in WORKBENCH_OUTPUT_FILENAMES:
        path = tmp_path / name
        assert path.is_file(), f"missing {name}"

    assert (tmp_path / FRAGMENT_TXT).read_text(encoding="utf-8") == result.fragment_text
    prompt_file = (tmp_path / PROMPT_TXT).read_text(encoding="utf-8")
    assert "=== system ===" in prompt_file
    assert "=== user ===" in prompt_file
    assert result.fragment_text in prompt_file

    raw_out = (tmp_path / RAW_MODEL_OUTPUT_TXT).read_text(encoding="utf-8")
    assert raw_out.strip().startswith("{")

    parsed = json.loads((tmp_path / PARSED_EXTRACTION_JSON).read_text(encoding="utf-8"))
    assert isinstance(parsed, list)
    assert parsed

    raw_props = json.loads((tmp_path / PROPOSITIONS_RAW_JSON).read_text(encoding="utf-8"))
    norm_props = json.loads((tmp_path / PROPOSITIONS_NORMALISED_JSON).read_text(encoding="utf-8"))
    assert len(raw_props) == len(result.raw_propositions)
    assert len(norm_props) == len(result.normalised_propositions)

    trace = json.loads((tmp_path / EXTRACTION_TRACE_JSON).read_text(encoding="utf-8"))
    assert trace["extraction_mode"] == "dry"
    assert trace["schema_version"]

    review = (tmp_path / REVIEW_MD).read_text(encoding="utf-8")
    assert "Propositions (raw / normalised)" in review

    model_md = (tmp_path / MODEL_MD).read_text(encoding="utf-8")
    assert "Prompt version" in model_md
    assert "normalisation" in model_md.lower()


def test_review_markdown_counts_compliance() -> None:
    md = build_fragment_review_markdown(
        raw_propositions=[
            {
                "id": "p1",
                "proposition_text": "Operators must store slurry safely unless exempt.",
                "legal_subject": "operators",
                "action": "must store",
                "conditions": [],
                "label": "Storage duty",
            }
        ],
        normalised_propositions=[
            {
                "id": "p1",
                "proposition_text": "Operators must store slurry safely unless exempt.",
                "legal_subject": "operators",
                "action": "must store",
                "conditions": [],
                "label": "Storage duty",
                "proposition_tier": "substantive",
                "legal_effect_type": "obligation",
                "is_compliance_relevant": True,
            }
        ],
        parsed_rows=[{"proposition_text": "x"}],
        validation_issue_records=[],
    )
    assert "**Compliance-relevant:** 1" in md
    assert "Possible missed conditions" in md


def test_fixture_missing_fragment_text_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "topic": {"name": "t"},
                "cluster": {"name": "c"},
                "source": {"id": "s1", "fragment_locator": "regulation:1"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fragment_text"):
        load_extraction_fixture(bad)


def test_dry_mode_without_raw_raises(tmp_path: Path) -> None:
    no_dry = tmp_path / "no_dry.json"
    no_dry.write_text(
        json.dumps(
            {
                "topic": {"name": "t", "description": "", "subject_tags": []},
                "cluster": {"name": "c", "description": ""},
                "source": {
                    "id": "s1",
                    "title": "T",
                    "jurisdiction": "UK",
                    "citation": "X",
                    "kind": "regulation",
                    "fragment_locator": "regulation:1",
                    "fragment_text": "Operators must comply.",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dry mode"):
        run_extract_fragment_workbench(fixture_path=no_dry, extraction_mode="dry")
