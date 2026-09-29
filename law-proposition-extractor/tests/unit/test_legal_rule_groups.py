"""Legal rule groups for multi-proposition structural source fragments."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import LegalRuleGroup
from law_proposition_extractor_pipeline.effective_law import attach_effective_law_artifacts
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.legal_rule_groups import (
    build_legal_rule_groups,
    group_for_canonical_locator,
    group_for_source_fragment,
    groups_by_source_fragment_id,
    legal_rule_group_id,
)
from law_proposition_extractor_pipeline.linting import load_exported_bundle

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)

SOURCE = "src-control-regulation-demo"
SNAPSHOT = "snap-src-control-regulation-demo-v1"
OTHER_SOURCE = "src-other-regulation-demo"
OTHER_SNAPSHOT = "snap-src-other-regulation-demo-v1"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _fragments_from_fixture(payload: dict) -> list[dict]:
    rows: list[dict] = []
    source_id = str(payload["source_record_id"])
    snapshot_id = str(payload["source_snapshot_id"])
    for item in payload["fragments"]:
        rows.append(
            {
                "id": item["id"],
                "source_record_id": source_id,
                "source_snapshot_id": snapshot_id,
                "locator": item["locator"],
                "fragment_text": item["fragment_text"],
                "parent_fragment_id": item.get("parent_fragment_id"),
                "order_index": item.get("order_index"),
                "fragment_type": item.get("fragment_type"),
                "fragment_hash": f"hash-{item['id']}",
            }
        )
    other = payload.get("other_instrument") or {}
    other_source = str(other.get("source_record_id") or "")
    other_snapshot = str(other.get("source_snapshot_id") or "")
    for item in other.get("fragments") or []:
        rows.append(
            {
                "id": item["id"],
                "source_record_id": other_source,
                "source_snapshot_id": other_snapshot,
                "locator": item["locator"],
                "fragment_text": item["fragment_text"],
                "parent_fragment_id": item.get("parent_fragment_id"),
                "order_index": item.get("order_index"),
                "fragment_type": item.get("fragment_type"),
                "fragment_hash": f"hash-{item['id']}",
            }
        )
    return rows


def _prop_from_row(row: dict, *, source_record_id: str, source_snapshot_id: str) -> dict:
    return {
        "id": row["id"],
        "source_record_id": source_record_id,
        "source_snapshot_id": source_snapshot_id,
        "source_fragment_id": row["source_fragment_id"],
        "fragment_locator": row["fragment_locator"],
        "source_order": row.get("source_order"),
        "proposition_text": row["proposition_text"],
        "legal_effect_type": row.get("legal_effect_type") or "obligation",
        "proposition_tier": "substantive_rule",
        "topic_id": "topic-demo",
        "jurisdiction": "UK",
        "legal_subject": "operator",
        "action": "comply",
        "explicit_cross_reference_targets": list(row.get("explicit_cross_reference_targets") or []),
    }


def _exported_propositions(payload: dict) -> list[dict]:
    props = [
        _prop_from_row(row, source_record_id=SOURCE, source_snapshot_id=SNAPSHOT)
        for row in payload["exported_propositions"]
    ]
    other = payload.get("other_instrument") or {}
    other_source = str(other.get("source_record_id") or OTHER_SOURCE)
    other_snapshot = str(other.get("source_snapshot_id") or OTHER_SNAPSHOT)
    props.extend(
        _prop_from_row(row, source_record_id=other_source, source_snapshot_id=other_snapshot)
        for row in other.get("exported_propositions") or []
    )
    return props


def _suppressed_propositions(payload: dict) -> list[dict]:
    return [
        _prop_from_row(row, source_record_id=SOURCE, source_snapshot_id=SNAPSHOT)
        for row in payload.get("suppressed_propositions") or []
    ]


def test_article_49a_paragraph_1_and_2_groups_no_paragraph_3_or_parent() -> None:
    payload = _load_fixture()
    result = build_legal_rule_groups(
        _exported_propositions(payload),
        run_id="run-49a",
        source_fragments=_fragments_from_fixture(payload),
    )
    groups = result["groups"]
    by_locator = {(g["source_record_id"], g["canonical_locator"]): g for g in groups}

    p1 = by_locator[(SOURCE, "article:49a:paragraph:1")]
    assert p1["source_fragment_id"] == "frag-demo-49a-p1"
    assert p1["group_basis"] == "shared_source_fragment"
    assert p1["member_proposition_ids"] == [
        "prop-demo-49a-p1-separate",
        "prop-demo-49a-p1-no-mixing",
    ]
    assert p1["member_count"] == 2
    assert p1["id"] == legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p1",
        canonical_locator="article:49a:paragraph:1",
    )
    assert p1["id"].startswith("rulegrp:")

    p2 = by_locator[(SOURCE, "article:49a:paragraph:2")]
    assert p2["source_fragment_id"] == "frag-demo-49a-p2"
    assert set(p2["member_proposition_ids"]) == {
        "prop-demo-49a-p2-pelagic",
        "prop-demo-49a-p2-industrial",
        "prop-demo-49a-p2-small-vessels",
    }
    assert p2["member_proposition_ids"] == [
        "prop-demo-49a-p2-pelagic",
        "prop-demo-49a-p2-industrial",
        "prop-demo-49a-p2-small-vessels",
    ]

    assert (SOURCE, "article:49a:paragraph:3") not in by_locator
    assert (SOURCE, "article:49a") not in by_locator
    assert not any(g["source_fragment_id"] == "frag-demo-49a" for g in groups)

    other = by_locator[(OTHER_SOURCE, "article:49a:paragraph:1")]
    assert other["source_fragment_id"] == "frag-other-49a-p1"
    assert other["member_proposition_ids"] == [
        "prop-other-49a-p1-a",
        "prop-other-49a-p1-b",
    ]
    assert other["id"] != p1["id"]


def test_suppressed_parent_propositions_not_grouped() -> None:
    payload = _load_fixture()
    exported = _exported_propositions(payload)
    suppressed = _suppressed_propositions(payload)
    # Only exported rows are passed (as in real export); suppressed must not appear.
    result = build_legal_rule_groups(
        exported,
        run_id="run-49a",
        source_fragments=_fragments_from_fixture(payload),
    )
    member_ids = {pid for g in result["groups"] for pid in g["member_proposition_ids"]}
    for row in suppressed:
        assert row["id"] not in member_ids
    assert not any(g["canonical_locator"] == "article:49a" for g in result["groups"])

    # Even if suppressed rows are mistakenly present alone, export filtering is the gate;
    # including them with exported rows would create a parent group — prove export path excludes them.
    with_suppressed = build_legal_rule_groups(
        exported + suppressed,
        run_id="run-49a",
        source_fragments=_fragments_from_fixture(payload),
    )
    assert any(g["source_fragment_id"] == "frag-demo-49a" for g in with_suppressed["groups"])


def test_different_fragments_not_grouped_by_similar_locator_or_text() -> None:
    props = [
        {
            "id": "prop-a",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "source_fragment_id": "frag-a",
            "fragment_locator": "article:49a:paragraph:1",
            "source_order": 0,
            "proposition_text": "Keep catches identifiable.",
        },
        {
            "id": "prop-b",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "source_fragment_id": "frag-b",
            "fragment_locator": "article:49a:paragraph:1",
            "source_order": 1,
            "proposition_text": "Keep catches identifiable.",
        },
    ]
    fragments = [
        {
            "id": "frag-a",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "locator": "article:49a:paragraph:1",
            "fragment_type": "article",
        },
        {
            "id": "frag-b",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "locator": "article:49a:paragraph:1",
            "fragment_type": "article",
        },
    ]
    result = build_legal_rule_groups(props, run_id="run-x", source_fragments=fragments)
    assert result["groups"] == []


def test_different_source_record_or_snapshot_cannot_share_group() -> None:
    props = [
        {
            "id": "prop-a",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "source_fragment_id": "frag-shared-name",
            "fragment_locator": "article:1:paragraph:1",
            "source_order": 0,
            "proposition_text": "A",
        },
        {
            "id": "prop-b",
            "source_record_id": OTHER_SOURCE,
            "source_snapshot_id": OTHER_SNAPSHOT,
            "source_fragment_id": "frag-shared-name",
            "fragment_locator": "article:1:paragraph:1",
            "source_order": 1,
            "proposition_text": "B",
        },
        {
            "id": "prop-c",
            "source_record_id": SOURCE,
            "source_snapshot_id": "snap-other",
            "source_fragment_id": "frag-demo-49a-p1",
            "fragment_locator": "article:49a:paragraph:1",
            "source_order": 0,
            "proposition_text": "C",
        },
        {
            "id": "prop-d",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "source_fragment_id": "frag-demo-49a-p1",
            "fragment_locator": "article:49a:paragraph:1",
            "source_order": 1,
            "proposition_text": "D",
        },
    ]
    result = build_legal_rule_groups(props, run_id="run-x")
    assert result["groups"] == []


def test_group_ids_and_member_order_stable_across_input_order() -> None:
    payload = _load_fixture()
    props = _exported_propositions(payload)
    fragments = _fragments_from_fixture(payload)
    first = build_legal_rule_groups(props, run_id="run-stable", source_fragments=fragments)
    second = build_legal_rule_groups(
        list(reversed(props)),
        run_id="run-stable",
        source_fragments=fragments,
    )
    assert first["groups"] == second["groups"]
    p1 = group_for_canonical_locator(
        first,
        source_record_id=SOURCE,
        source_snapshot_id=SNAPSHOT,
        canonical_locator="article:49a:paragraph:1",
    )
    assert p1 is not None
    assert p1["member_proposition_ids"] == [
        "prop-demo-49a-p1-separate",
        "prop-demo-49a-p1-no-mixing",
    ]


def test_lookup_helpers_are_source_scoped() -> None:
    payload = _load_fixture()
    result = build_legal_rule_groups(
        _exported_propositions(payload),
        run_id="run-49a",
        source_fragments=_fragments_from_fixture(payload),
    )
    by_frag = groups_by_source_fragment_id(result)
    assert len(by_frag["frag-demo-49a-p1"]) == 1

    demo = group_for_source_fragment(
        result,
        source_record_id=SOURCE,
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p1",
    )
    assert demo is not None
    assert demo["member_count"] == 2

    assert (
        group_for_source_fragment(
            result,
            source_record_id=OTHER_SOURCE,
            source_snapshot_id=OTHER_SNAPSHOT,
            source_fragment_id="frag-demo-49a-p1",
        )
        is None
    )

    demo_loc = group_for_canonical_locator(
        result,
        source_record_id=SOURCE,
        source_snapshot_id=SNAPSHOT,
        canonical_locator="article:49a:paragraph:1",
    )
    other_loc = group_for_canonical_locator(
        result,
        source_record_id=OTHER_SOURCE,
        source_snapshot_id=OTHER_SNAPSHOT,
        canonical_locator="article:49a:paragraph:1",
    )
    assert demo_loc is not None and other_loc is not None
    assert demo_loc["id"] != other_loc["id"]
    assert (
        group_for_canonical_locator(
            result,
            source_record_id=SOURCE,
            source_snapshot_id="snap-wrong",
            canonical_locator="article:49a:paragraph:1",
        )
        is None
    )


def test_serialization_round_trip_preserves_membership() -> None:
    payload = _load_fixture()
    result = build_legal_rule_groups(
        _exported_propositions(payload),
        run_id="run-49a",
        source_fragments=_fragments_from_fixture(payload),
    )
    models = [LegalRuleGroup.model_validate(row) for row in result["groups"]]
    dumped = [m.model_dump() for m in models]
    reloaded = [LegalRuleGroup.model_validate(row) for row in dumped]
    assert [m.model_dump() for m in reloaded] == dumped
    p1 = next(m for m in reloaded if m.canonical_locator == "article:49a:paragraph:1" and m.source_record_id == SOURCE)
    assert p1.source_fragment_id == "frag-demo-49a-p1"
    assert p1.member_proposition_ids == [
        "prop-demo-49a-p1-separate",
        "prop-demo-49a-p1-no-mixing",
    ]
    assert p1.parent_fragment_id == "frag-demo-49a"


def test_attach_and_export_writes_artifact(tmp_path: Path) -> None:
    payload = _load_fixture()
    props = _exported_propositions(payload)
    fragments = _fragments_from_fixture(payload)
    bundle = {
        "run": {"id": "run-lrg-001", "workflow_mode": "divergence"},
        "topic": {"id": "topic-demo", "name": "Demo", "description": "", "subject_tags": []},
        "clusters": [],
        "narrative": {"title": "Demo", "summary": "", "sections": []},
        "source_records": [],
        "source_snapshots": [],
        "source_fragments": fragments,
        "source_parse_traces": [],
        "source_fetch_metadata": [],
        "source_fetch_attempts": [],
        "source_target_links": [],
        "source_inventory": {},
        "source_categorisation_rationales": [],
        "propositions": props,
        "proposition_extraction_traces": [],
        "proposition_extraction_jobs": [],
        "divergence_assessments": [],
        "divergence_observations": [],
        "divergence_findings": [],
        "run_artifacts": [],
        "legal_scopes": [],
        "proposition_scope_links": [],
        "scope_inventory": {},
        "scope_review_candidates": [],
        "proposition_completeness_assessments": [],
        "workflow_mode": "divergence",
        "has_divergence_outputs": False,
    }
    attach_effective_law_artifacts(bundle)
    assert "legal_rule_groups" in bundle
    assert len(bundle["legal_rule_groups"]["groups"]) >= 2

    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    artifact_path = tmp_path / "legal_rule_groups.json"
    assert artifact_path.exists()
    written = json.loads(artifact_path.read_text(encoding="utf-8"))
    p1 = group_for_canonical_locator(
        written,
        source_record_id=SOURCE,
        source_snapshot_id=SNAPSHOT,
        canonical_locator="article:49a:paragraph:1",
    )
    assert p1 is not None
    assert p1["member_proposition_ids"] == [
        "prop-demo-49a-p1-separate",
        "prop-demo-49a-p1-no-mixing",
    ]


def test_old_bundle_without_legal_rule_groups_loads(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text('{"id":"run-old-lrg"}', encoding="utf-8")
    for name in (
        "sources.json",
        "source_snapshots.json",
        "source_fragments.json",
        "source_parse_traces.json",
        "source_fetch_metadata.json",
        "source_fetch_attempts.json",
        "source_target_links.json",
        "source_categorisation_rationales.json",
        "propositions.json",
        "proposition_extraction_traces.json",
        "proposition_extraction_jobs.json",
        "divergence_observations.json",
        "divergence_assessments.json",
        "divergence_findings.json",
        "run_artifacts.json",
        "legal_scopes.json",
        "proposition_scope_links.json",
        "scope_review_candidates.json",
    ):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    (tmp_path / "source_inventory.json").write_text("{}", encoding="utf-8")
    (tmp_path / "scope_inventory.json").write_text("{}", encoding="utf-8")

    loaded = load_exported_bundle(tmp_path)
    assert loaded.get("legal_rule_groups") is None
    assert loaded["run"]["id"] == "run-old-lrg"
