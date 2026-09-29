"""Tests for export proposition identity uniqueness helpers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from law_proposition_extractor_pipeline.fresh_extraction_verification import (
    build_fresh_extraction_verification,
    verification_exit_code,
)
from law_proposition_extractor_pipeline.proposition_export_uniqueness import (
    find_duplicate_proposition_ids,
    reconstruct_staging_proposition_id,
)
from law_proposition_extractor_domain import Proposition
from law_proposition_extractor_pipeline.runner import _opaque_machine_proposition_id
from law_proposition_extractor_pipeline.suspicious_proposition_review import build_suspicious_proposition_review


def _sample_proposition(**overrides: object) -> Proposition:
    base = dict(
        id="prop-demo-src-001",
        topic_id="topic-movement",
        source_record_id="lex-a",
        source_snapshot_id="snap-1",
        source_fragment_id=None,
        fragment_locator="regulation 1",
        jurisdiction="UK",
        proposition_text="Same text.",
        legal_subject="occupier",
        action="must ensure",
        notes="unit",
    )
    base.update(overrides)
    return Proposition.model_validate(base)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "fresh_extraction_verification"
OK_EXPORT = FIXTURE_ROOT / "minimal_ok"


def _row(**kwargs: object) -> dict:
    base = {
        "id": "prop:aaa",
        "source_record_id": "lex-a",
        "source_fragment_id": "frag-a-1",
        "fragment_locator": "regulation 1",
        "proposition_key": "lex-a:frag-a-1:p001",
        "proposition_text": "Text one.",
        "proposition_tier": "substantive_rule",
        "legal_effect_type": "obligation",
    }
    base.update(kwargs)
    return base


def test_find_duplicate_proposition_ids() -> None:
    rows = [_row(id="prop:dup"), _row(id="prop:dup", source_fragment_id="frag-a-2")]
    dups = find_duplicate_proposition_ids(rows)
    assert len(dups) == 1
    assert dups[0]["id"] == "prop:dup"
    assert dups[0]["count"] == 2


def test_different_fragments_get_different_opaque_ids() -> None:
    a = _sample_proposition(
        id="prop-staging-a-001",
        source_fragment_id="frag-a-1",
        fragment_locator="regulation 1",
        proposition_text="Same text.",
    )
    b = _sample_proposition(
        id="prop-staging-b-001",
        source_fragment_id="frag-a-2",
        fragment_locator="regulation 1",
        proposition_text="Same text.",
    )
    assert _opaque_machine_proposition_id(a, "001") != _opaque_machine_proposition_id(b, "001")


def test_duplicate_ids_fail_fresh_verification(tmp_path: Path) -> None:
    dest = tmp_path / "dup"
    shutil.copytree(OK_EXPORT, dest)
    rows = json.loads((dest / "propositions.json").read_text(encoding="utf-8"))
    rows.append(dict(rows[0]))
    rows[-1]["id"] = rows[0]["id"]
    (dest / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    report = build_fresh_extraction_verification(dest)
    assert report.hard_failure is True
    assert any(f.check_id == "duplicate_proposition_id" for f in report.findings)
    assert verification_exit_code(report) == 1


def test_suspicious_review_flags_duplicate_ids_as_error() -> None:
    rows = [_row(id="prop:dup"), _row(id="prop:dup", source_fragment_id="frag-a-2")]
    review = build_suspicious_proposition_review(rows, export_dir="/tmp")
    assert review.summary["duplicates_are_blocker"] is True
    assert review.summary["duplicate_proposition_id_groups"] == 1
    assert any(
        f.duplicate_classification == "duplicate_proposition_id" and f.severity == "error"
        for f in review.findings
    )


def test_reconstruct_staging_id_uses_fragment() -> None:
    staging = reconstruct_staging_proposition_id(_row())
    assert "frag-a-1" in staging
