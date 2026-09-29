"""Load shared regression fixtures for proposition normalisation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import (
    Proposition,
    apply_post_extraction_classification,
    apply_proposition_label_enrichment,
    apply_relationship_keys,
    attach_extraction_meta,
)
from law_proposition_extractor_pipeline.proposition_classification_pass import apply_post_extraction_classification_pass
from law_proposition_extractor_pipeline.proposition_jurisdiction_pass import apply_post_extraction_jurisdiction_pass

FIXTURES_DIR = Path(__file__).resolve().parent
DEFAULT_FIXTURE_SLUG = "agricultural_land_england_territorial_application"


def load_regression_fixture(slug: str = DEFAULT_FIXTURE_SLUG) -> dict[str, Any]:
    path = FIXTURES_DIR / f"{slug}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def proposition_record_from_fixture(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a Proposition.model_validate payload from fixture raw extraction + record ids."""
    fixture = data if data is not None else load_regression_fixture()
    record: dict[str, Any] = dict(fixture["proposition_record"])
    raw: dict[str, Any] = dict(fixture["raw_extraction"])
    for key, value in raw.items():
        if key not in record:
            record[key] = value
    meta = fixture.get("extraction_meta") or {}
    if meta:
        record["notes"] = attach_extraction_meta(str(record.get("notes") or ""), meta)
    return record


def normalize_proposition_from_fixture(data: dict[str, Any] | None = None) -> Proposition:
    """Apply post-extraction passes in pipeline order (classification → jurisdiction → labels → keys)."""
    prop = Proposition.model_validate(proposition_record_from_fixture(data))
    apply_post_extraction_classification_pass([prop])
    apply_post_extraction_jurisdiction_pass([prop])
    apply_proposition_label_enrichment(prop)
    apply_relationship_keys(prop)
    return prop
