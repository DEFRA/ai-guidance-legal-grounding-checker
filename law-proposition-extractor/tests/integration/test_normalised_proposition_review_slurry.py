"""Integration: slurry export review uses the same normalisation as acceptance tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from law_proposition_extractor_domain.enums import LegalEffectType, PropositionTier
from law_proposition_extractor_pipeline.normalised_proposition_review import build_review_from_export_dir
from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import (
    DIFFUSE_SOURCE_2018,
    EXPECTED_REG1D_LABEL_FRAGMENT,
    default_slurry_export_path,
    slurry_export_available,
)

pytestmark = pytest.mark.skipif(
    not slurry_export_available(),
    reason="slurry export fixture missing (runs/slurry-gb-principal-5-frontier-export/propositions.json)",
)

REG1D_PROP_ID = "prop:1a60ff5b0ef1ff43"


@pytest.fixture(scope="module")
def slurry_export_dir() -> Path:
    return default_slurry_export_path()


@pytest.fixture(scope="module")
def slurry_review(slurry_export_dir: Path):
    return build_review_from_export_dir(slurry_export_dir)


def test_reg1d_in_application_scope_rows(slurry_review) -> None:
    scope_ids = {row.proposition_id for row in slurry_review.application_scope_rows}
    assert REG1D_PROP_ID in scope_ids
    row = next(r for r in slurry_review.application_scope_rows if r.proposition_id == REG1D_PROP_ID)
    assert row.fields["legal_effect_type"] == LegalEffectType.APPLICATION_SCOPE.value
    assert row.fields["proposition_tier"] == PropositionTier.SCOPE_RULE.value
    assert EXPECTED_REG1D_LABEL_FRAGMENT in row.fields["label"]
    assert row.fields["territorial_application"] == ["England"]


def test_citation_rows_not_generic_blank_in_shortest_labels(slurry_review) -> None:
    """Citation/commencement rows must be normalised, not raw generic labels with blank tier/effect."""
    generic_by_id = {r.proposition_id: r for r in slurry_review.shortest_generic_labels}
    for row in slurry_review.shortest_generic_labels:
        tier = row.fields.get("proposition_tier", "")
        effect = row.fields.get("legal_effect_type", "")
        label = row.fields.get("label", "")
        assert tier and effect, (
            f"{row.proposition_id} in shortest_generic_labels has blank classification "
            f"(tier={tier!r}, effect={effect!r}, label={label!r})"
        )
        if label in {"Citation", "Commencement", "Commencement date", "Territorial extent"}:
            assert effect in {
                LegalEffectType.CITATION.value,
                LegalEffectType.COMMENCEMENT.value,
                LegalEffectType.APPLICATION_SCOPE.value,
            } or row.fields.get("proposition_tier") == PropositionTier.INSTRUMENT_METADATA.value, (
                f"{row.proposition_id} still looks like unnormalised boilerplate: {row.fields}"
            )

    # Diffuse 2018 reg 1(a) citation — enriched label, not bare "Citation" with blank fields
    diffuse_citation = [
        r
        for r in slurry_review.shortest_generic_labels
        if r.fields.get("source_record_id") == DIFFUSE_SOURCE_2018
        and r.fields.get("locator", "").lower() == "regulation 1(a)"
    ]
    for row in diffuse_citation:
        assert row.fields["legal_effect_type"] == LegalEffectType.CITATION.value
        assert row.fields["proposition_tier"] == PropositionTier.INSTRUMENT_METADATA.value
        assert row.fields["label"] != "Citation"


def test_review_sections_nonzero_after_normalisation(slurry_review) -> None:
    counts = slurry_review.to_dict()["counts"]
    assert counts["application_scope_rows"] > 0
    assert counts["cross_reference_rows"] > 0
    assert counts["semantic_comparison_buckets"] > 0
    assert slurry_review.proposition_count == 678


def test_no_unlisted_blank_classifications(slurry_review) -> None:
    """Sanity: if counts say zero unknown, no section row may have blank tier/effect."""
    unknown_ids = {r.proposition_id for r in slurry_review.unknown_classifications}
    sections = [
        slurry_review.application_scope_rows,
        slurry_review.cross_reference_rows,
        slurry_review.longest_labels,
        slurry_review.shortest_generic_labels,
        slurry_review.compliance_without_clear_actor,
    ]
    for section in sections:
        for row in section:
            tier = str(row.fields.get("proposition_tier") or "").strip()
            effect = str(row.fields.get("legal_effect_type") or "").strip()
            if not tier or not effect:
                assert row.proposition_id in unknown_ids, (
                    f"{row.proposition_id} has blank classification in a detail section "
                    f"but is not in unknown_classifications"
                )
