"""Regression: salvage prompt-lab rows from saved raw model output after JSON repair."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_pipeline.extraction_workbench import (
    PARSED_EXTRACTION_JSON,
    PROPOSITIONS_NORMALISED_JSON,
    run_extract_fragment_workbench,
    write_extract_fragment_workbench_outputs,
)

SLURRY = Path(__file__).resolve().parents[1] / "fixtures" / "extraction_prompt_cases" / "slurry"
GOOD_PROHIBITION = SLURRY / "slurry-good-simple-prohibition-spread-buffer.json"
BASELINE_GOOD = Path("runs/prompt-lab/baseline-good-prohibition")


def test_dry_workbench_repairs_good_prohibition_raw_output(tmp_path: Path) -> None:
    if not BASELINE_GOOD.is_dir():
        import pytest

        pytest.skip("baseline good-prohibition run dir not present")
    raw = (BASELINE_GOOD / "raw_model_output.txt").read_text(encoding="utf-8")
    result = run_extract_fragment_workbench(
        fixture_path=GOOD_PROHIBITION,
        extraction_mode="dry",
        dry_raw_model_output=raw,
    )
    assert result.workbench_status == "success"
    assert result.actual_proposition_count >= 1
    assert len(result.parsed_extraction_rows) >= 1
    assert any(
        "must not spread organic manure within 10 metres" in str(r.get("proposition_text") or "")
        for r in result.parsed_extraction_rows
    )
    out = write_extract_fragment_workbench_outputs(result, tmp_path / "salvaged")
    parsed = json.loads((out / PARSED_EXTRACTION_JSON).read_text(encoding="utf-8"))
    normalised = json.loads((out / PROPOSITIONS_NORMALISED_JSON).read_text(encoding="utf-8"))
    assert parsed
    assert normalised
