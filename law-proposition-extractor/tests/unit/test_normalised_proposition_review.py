"""Unit tests for normalised proposition review report builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.normalised_proposition_review import (
    REVIEW_JSON_FILENAME,
    REVIEW_MD_FILENAME,
    build_normalised_proposition_review,
    build_review_from_export_dir,
    load_export_sources,
    render_normalised_proposition_review_md,
    write_normalised_proposition_review,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "normalised_proposition_review"


@pytest.fixture
def fixture_propositions() -> list[dict]:
    raw = json.loads((FIXTURE_DIR / "propositions.json").read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    return raw


@pytest.fixture
def fixture_sources() -> dict[str, dict]:
    return load_export_sources(FIXTURE_DIR)


def test_unknown_classifications_section(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    assert len(review.unknown_classifications) == 1
    assert review.unknown_classifications[0].proposition_id == "prop-unknown"


def test_blank_tier_and_effect_count_as_unknown() -> None:
    rows = [
        {
            "id": "prop-blank",
            "source_record_id": "src-a",
            "fragment_locator": "regulation 1(d)",
            "label": "Territorial application",
            "proposition_tier": "",
            "legal_effect_type": "",
        }
    ]
    review = build_normalised_proposition_review(rows, export_dir="/tmp")
    assert len(review.unknown_classifications) == 1
    assert review.unknown_classifications[0].proposition_id == "prop-blank"


def test_legacy_category_conflict_section(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    ids = {row.proposition_id for row in review.legacy_category_conflicts}
    assert ids == {"prop-legacy-conflict", "prop-generic-label"}


def test_application_scope_rows_include_source_title(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    assert len(review.application_scope_rows) == 3
    row = next(r for r in review.application_scope_rows if r.proposition_id == "prop-legacy-conflict")
    assert row.fields["source_title"] == "Diffuse Pollution Regulations 2018"
    assert row.fields["territorial_application"] == ["England"]


def test_cross_reference_rows_include_targets_and_text(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    assert len(review.cross_reference_rows) == 1
    assert review.cross_reference_rows[0].fields["explicit_targets"] == ["regulation 3"]
    assert "regulation 3" in review.cross_reference_rows[0].fields["proposition_text"]


def test_semantic_comparison_buckets_are_hints_only(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    assert len(review.semantic_comparison_buckets) == 1
    bucket = review.semantic_comparison_buckets[0]
    assert bucket.semantic_comparison_key == "uk:these-regulations:apply-to"
    assert bucket.size == 2
    member_ids = {m["proposition_id"] for m in bucket.members}
    assert member_ids == {"prop-legacy-conflict", "prop-scope-b"}


def test_compliance_without_clear_actor(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    assert len(review.compliance_without_clear_actor) == 1
    assert review.compliance_without_clear_actor[0].proposition_id == "prop-compliance-weak"


def test_longest_and_generic_label_sections(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    assert review.longest_labels[0].proposition_id == "prop-long-label"
    assert review.longest_labels[0].fields["label_length"] > 50
    generic_ids = {r.proposition_id for r in review.shortest_generic_labels}
    assert "prop-generic-label" in generic_ids


def test_markdown_contains_sections_and_hint_disclaimer(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    md = render_normalised_proposition_review_md(review)
    assert "## 1. Unknown classifications" in md
    assert "## 5. Semantic comparison buckets (review hints)" in md
    assert "not treated as automatic" in md.lower()
    assert "prop-legacy-conflict" in md


def test_write_artifacts_deterministic(tmp_path: Path, fixture_propositions: list[dict]) -> None:
    (tmp_path / "propositions.json").write_text(
        json.dumps(fixture_propositions, indent=2) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "sources.json").write_text(
        (FIXTURE_DIR / "sources.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # Minimal fixture rows omit export-only fields; pass pre-normalised dicts explicitly.
    review = build_review_from_export_dir(tmp_path, propositions=fixture_propositions)
    md_path, json_path = write_normalised_proposition_review(tmp_path, review, write_json=True)
    assert md_path.name == REVIEW_MD_FILENAME
    assert json_path is not None and json_path.name == REVIEW_JSON_FILENAME

    md_again, _ = write_normalised_proposition_review(tmp_path, review, write_json=False)
    assert md_path.read_text(encoding="utf-8") == md_again.read_text(encoding="utf-8")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["proposition_count"] == len(fixture_propositions)
    assert payload["counts"]["application_scope_rows"] == 3


def test_to_dict_sort_keys_stable(
    fixture_propositions: list[dict],
    fixture_sources: dict[str, dict],
) -> None:
    review = build_normalised_proposition_review(
        fixture_propositions,
        export_dir=FIXTURE_DIR,
        sources_by_id=fixture_sources,
    )
    text = json.dumps(review.to_dict(), sort_keys=True)
    assert '"legacy_category_conflicts"' in text
