"""Acceptance tests for slurry principal-5 export post-extraction normalisation (no LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import (
    assert_slurry_normalisation_acceptance,
    default_slurry_export_path,
    slurry_export_available,
)

pytestmark = pytest.mark.skipif(
    not slurry_export_available(),
    reason="slurry export fixture missing (runs/slurry-gb-principal-5-frontier-export/propositions.json)",
)


@pytest.fixture(scope="module")
def slurry_export_dir() -> Path:
    return default_slurry_export_path()


def test_slurry_principal_5_normalisation_acceptance(slurry_export_dir: Path) -> None:
    summary = assert_slurry_normalisation_acceptance(slurry_export_dir)
    assert summary.before_count == 678
    assert summary.generic_key_count == 0
    assert summary.cross_instrument_link_count == 0
