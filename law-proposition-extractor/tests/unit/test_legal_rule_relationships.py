"""Typed legal relationships (exception_to / triggered_by)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import LegalRuleRelationship
from law_proposition_extractor_pipeline.effective_law import attach_effective_law_artifacts
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.legal_rule_groups import build_legal_rule_groups, legal_rule_group_id
from law_proposition_extractor_pipeline.legal_rule_relationships import (
    build_legal_rule_relationships,
    legal_rule_relationship_id,
)
from law_proposition_extractor_pipeline.linting import load_exported_bundle, lint_bundle

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


def _build_payload(*, shuffle: bool = False) -> tuple[list[dict], list[dict], dict]:
    payload = _load_fixture()
    props = _exported_propositions(payload)
    frags = _fragments_from_fixture(payload)
    if shuffle:
        props = list(reversed(props))
        frags = list(reversed(frags))
    groups = build_legal_rule_groups(props, run_id="run-49a", source_fragments=frags)
    return props, frags, groups


def test_article_49a_exception_to_and_triggered_by() -> None:
    props, frags, groups = _build_payload()
    result = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    rels = result["relationships"]

    p1_group_id = legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p1",
        canonical_locator="article:49a:paragraph:1",
    )
    p2_group_id = legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p2",
        canonical_locator="article:49a:paragraph:2",
    )

    pelagic = next(r for r in rels if r["source_id"] == "prop-demo-49a-p2-pelagic")
    assert pelagic["relationship_type"] == "exception_to"
    assert pelagic["source_kind"] == "proposition"
    assert pelagic["target_kind"] == "legal_rule_group"
    assert pelagic["target_id"] == p1_group_id
    assert pelagic["referenced_locator"] == "article:49a:paragraph:1"
    assert pelagic["resolution_basis"] == "structural_relative"
    assert pelagic["inference_basis"] == "explicit_exception_cue"
    assert pelagic["id"].startswith("legalrel:")

    industrial = next(r for r in rels if r["source_id"] == "prop-demo-49a-p2-industrial")
    assert industrial["relationship_type"] == "exception_to"
    assert industrial["target_id"] == p1_group_id
    assert industrial["referenced_locator"] == "article:49a:paragraph:1"

    small = next(r for r in rels if r["source_id"] == "prop-demo-49a-p2-small-vessels")
    assert small["relationship_type"] == "exception_to"
    assert small["target_id"] == p1_group_id
    assert small["referenced_locator"] == "article:49a:paragraph:1"

    # Article 14 must not receive exception_to.
    assert not any(
        r["relationship_type"] == "exception_to"
        and (
            "14" in str(r.get("referenced_locator") or "")
            or "14" in str(r.get("target_canonical_locator") or "")
            or "article:14" in str(r.get("target_id") or "")
        )
        for r in rels
    )
    assert not any(
        r["relationship_type"] == "exception_to" and r["target_kind"] == "proposition"
        and "14" in r["target_id"]
        for r in rels
    )

    monitoring = next(r for r in rels if r["source_id"] == "prop-demo-49a-p3-monitoring")
    assert monitoring["relationship_type"] == "triggered_by"
    assert monitoring["target_kind"] == "legal_rule_group"
    assert monitoring["target_id"] == p2_group_id
    assert monitoring["referenced_locator"] == "article:49a:paragraph:2"
    assert monitoring["resolution_basis"] == "structural_relative"
    assert monitoring["inference_basis"] == "explicit_trigger_cue"


def test_unique_proposition_target_when_no_group() -> None:
    props, frags, groups = _build_payload()
    result = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    art30 = next(r for r in result["relationships"] if r["source_id"] == "prop-demo-art30-p2-exception")
    assert art30["target_kind"] == "proposition"
    assert art30["target_id"] == "prop-demo-art30-p1-only"
    assert art30["referenced_locator"] == "article:30:paragraph:1"
    assert art30["resolution_basis"] == "structural_relative"


def test_no_fan_out_when_multiple_props_without_group() -> None:
    props, frags, _groups = _build_payload()
    result = build_legal_rule_relationships(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups={"schema_version": "1", "run_id": "run-49a", "groups": []},
    )
    assert not any(r["source_id"] == "prop-demo-art31-exception" for r in result["relationships"])
    codes = {d["code"] for d in result["diagnostics"] if d.get("source_id") == "prop-demo-art31-exception"}
    assert "typed_relationship_target_group_missing" in codes


def test_generic_cross_reference_without_cue_creates_no_legal_relationship() -> None:
    props, frags, groups = _build_payload()
    result = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    assert not any(r["source_id"] == "prop-demo-article-14-p1" for r in result["relationships"])


def test_unresolved_trigger_or_exception_creates_no_edge() -> None:
    props, frags, groups = _build_payload()
    result = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    assert not any(r["source_id"] == "prop-demo-unresolved-exception" for r in result["relationships"])


def test_same_numbered_paragraphs_elsewhere_not_targeted() -> None:
    props, frags, groups = _build_payload()
    result = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    p1_group_id = legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p1",
        canonical_locator="article:49a:paragraph:1",
    )
    for source_id in (
        "prop-demo-49a-p2-pelagic",
        "prop-demo-49a-p2-industrial",
        "prop-demo-49a-p2-small-vessels",
    ):
        rel = next(r for r in result["relationships"] if r["source_id"] == source_id)
        assert rel["target_id"] == p1_group_id
        assert rel["target_source_fragment_id"] == "frag-demo-49a-p1"
        assert rel["referenced_locator"] != "article:1:paragraph:1"


def test_other_instrument_same_locator_does_not_collide() -> None:
    props, frags, groups = _build_payload()
    result = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    demo = next(r for r in result["relationships"] if r["source_id"] == "prop-demo-49a-p2-pelagic")
    other = next(r for r in result["relationships"] if r["source_id"] == "prop-other-49a-p2-exception")
    assert demo["source_record_id"] == SOURCE
    assert other["source_record_id"] == OTHER_SOURCE
    assert demo["target_id"] != other["target_id"]
    assert demo["target_source_fragment_id"] == "frag-demo-49a-p1"
    assert other["target_source_fragment_id"] == "frag-other-49a-p1"


def test_relationship_ids_and_ordering_deterministic_across_input_order() -> None:
    props_a, frags_a, groups_a = _build_payload(shuffle=False)
    props_b, frags_b, groups_b = _build_payload(shuffle=True)
    a = build_legal_rule_relationships(
        props_a, run_id="run-49a", source_fragments=frags_a, legal_rule_groups=groups_a
    )
    b = build_legal_rule_relationships(
        props_b, run_id="run-49a", source_fragments=frags_b, legal_rule_groups=groups_b
    )
    assert [r["id"] for r in a["relationships"]] == [r["id"] for r in b["relationships"]]
    assert a["relationships"] == b["relationships"]
    ids = [r["id"] for r in a["relationships"]]
    assert ids == sorted(
        ids,
        key=lambda _rid: next(
            (
                (r["relationship_type"], r["source_id"], r["target_kind"], r["target_id"], r["id"])
                for r in a["relationships"]
                if r["id"] == _rid
            ),
        ),
    )


def test_duplicate_processing_paths_do_not_duplicate_relationships() -> None:
    props, frags, groups = _build_payload()
    # Duplicate proposition rows simulate multiple processing paths.
    doubled = props + list(props)
    result = build_legal_rule_relationships(
        doubled, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    ids = [r["id"] for r in result["relationships"]]
    assert len(ids) == len(set(ids))


def test_serialization_round_trip() -> None:
    props, frags, groups = _build_payload()
    result = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    for row in result["relationships"]:
        model = LegalRuleRelationship.model_validate(row)
        dumped = model.model_dump()
        assert dumped["source_kind"] == "proposition"
        assert dumped["target_kind"] in {"proposition", "legal_rule_group"}
        assert dumped["inference_basis"] in {"explicit_exception_cue", "explicit_trigger_cue"}
        assert dumped["resolution_basis"] in {"explicit", "structural_relative", "instrument_wide"}


def test_stable_id_matches_semantic_inputs() -> None:
    props, frags, groups = _build_payload()
    result = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    pelagic = next(r for r in result["relationships"] if r["source_id"] == "prop-demo-49a-p2-pelagic")
    assert pelagic["id"] == legal_rule_relationship_id(
        relationship_type="exception_to",
        source_id="prop-demo-49a-p2-pelagic",
        target_kind="legal_rule_group",
        target_id=pelagic["target_id"],
        referenced_locator="article:49a:paragraph:1",
        inference_basis="explicit_exception_cue",
    )


def test_equivalent_structured_targets_are_not_ambiguous() -> None:
    """``paragraph 1`` + ``Paragraph 1 of Article 49a`` share one canonical key."""
    props = [
        {
            "id": "prop-equiv-targets",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "source_fragment_id": "frag-demo-49a-p2",
            "fragment_locator": "article:49a:paragraph:2",
            "proposition_text": "Paragraph 1 shall not apply in this case.",
            "legal_effect_type": "derogation",
            "explicit_cross_reference_targets": [
                "paragraph 1",
                "Paragraph 1 of Article 49a",
            ],
        }
    ]
    frags = _fragments_from_fixture(_load_fixture())
    groups = build_legal_rule_groups(
        _exported_propositions(_load_fixture()), run_id="run-x", source_fragments=frags
    )
    result = build_legal_rule_relationships(
        props, run_id="run-x", source_fragments=frags, legal_rule_groups=groups
    )
    rel = next(r for r in result["relationships"] if r["source_id"] == "prop-equiv-targets")
    assert rel["relationship_type"] == "exception_to"
    assert rel["referenced_locator"] == "article:49a:paragraph:1"
    assert not any(
        d["code"] == "typed_relationship_reference_not_uniquely_associated"
        and d["source_id"] == "prop-equiv-targets"
        for d in result["diagnostics"]
    )


def test_unparseable_cue_reference_produces_focused_diagnostic() -> None:
    props = [
        {
            "id": "prop-bad-ref-exception",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "source_fragment_id": "frag-demo-49a-p2",
            "fragment_locator": "article:49a:paragraph:2",
            "proposition_text": "Article 9999z shall not apply in this case.",
            "legal_effect_type": "derogation",
            "explicit_cross_reference_targets": ["article 14"],
        }
    ]
    frags = _fragments_from_fixture(_load_fixture())
    groups = build_legal_rule_groups(
        _exported_propositions(_load_fixture()), run_id="run-x", source_fragments=frags
    )
    result = build_legal_rule_relationships(
        props, run_id="run-x", source_fragments=frags, legal_rule_groups=groups
    )
    assert not any(r["source_id"] == "prop-bad-ref-exception" for r in result["relationships"])


def test_unparseable_associated_reference_diagnostic_fields() -> None:
    from law_proposition_extractor_pipeline.legal_rule_relationships import (
        _associate_cue_reference,
        _DIAG_CUE_REF_PARSE_FAILED,
        _DIAG_CUE_REF_NO_MATCHING_TARGET,
    )

    associated, code = _associate_cue_reference("not a locator at all", ["article 14"])
    assert associated is None
    assert code in {_DIAG_CUE_REF_PARSE_FAILED, _DIAG_CUE_REF_NO_MATCHING_TARGET}


def test_export_and_older_bundle_compatibility(tmp_path: Path) -> None:
    payload = _load_fixture()
    props = _exported_propositions(payload)
    frags = _fragments_from_fixture(payload)
    bundle = {
        "run": {"id": "run-lrr-export"},
        "topic": {"id": "topic-demo", "name": "Demo"},
        "clusters": [],
        "narrative": {"title": "n", "summary": "s", "sections": []},
        "propositions": props,
        "source_fragments": frags,
        "source_records": [{"id": SOURCE}, {"id": OTHER_SOURCE}],
        "source_snapshots": [{"id": SNAPSHOT}, {"id": OTHER_SNAPSHOT}],
        "source_parse_traces": [],
        "source_fetch_metadata": [],
        "source_fetch_attempts": [],
        "source_target_links": [],
        "source_inventory": {"rows": []},
        "source_categorisation_rationales": [],
        "proposition_extraction_traces": [],
        "proposition_extraction_jobs": [],
        "proposition_completeness_assessments": [],
        "divergence_assessments": [],
        "divergence_observations": [],
        "divergence_findings": [],
        "run_artifacts": [],
        "legal_scopes": [],
        "proposition_scope_links": [],
        "scope_inventory": {},
        "scope_review_candidates": [],
        "workflow_mode": "demo",
        "has_divergence_outputs": False,
        "stage_traces": [],
    }
    attach_effective_law_artifacts(bundle)
    assert isinstance(bundle.get("legal_rule_relationships"), dict)
    assert bundle["legal_rule_relationships"]["relationships"]

    export_dir = tmp_path / "export"
    export_bundle(bundle=bundle, output_dir=str(export_dir))
    assert (export_dir / "legal_rule_relationships.json").exists()
    loaded = load_exported_bundle(export_dir)
    assert "legal_rule_relationships" in loaded
    assert loaded["legal_rule_relationships"]["relationships"]

    # Older export without the artifact remains loadable.
    (export_dir / "legal_rule_relationships.json").unlink()
    older = load_exported_bundle(export_dir)
    assert "legal_rule_relationships" not in older


def test_lint_surfaces_typed_relationship_diagnostics() -> None:
    bundle = {
        "source_records": [],
        "source_snapshots": [],
        "source_fragments": [],
        "source_parse_traces": [],
        "proposition_extraction_traces": [],
        "propositions": [],
        "source_inventory": {"rows": []},
        "source_fetch_metadata": [],
        "source_fetch_attempts": [],
        "source_target_links": [],
        "source_categorisation_rationales": [],
        "run_artifacts": [],
        "divergence_observations": [],
        "divergence_assessments": [],
        "divergence_findings": [],
        "legal_scopes": [],
        "proposition_scope_links": [],
        "scope_inventory": {},
        "scope_review_candidates": [],
        "legal_rule_relationships": {
            "schema_version": "1",
            "run_id": "run-x",
            "relationships": [],
            "diagnostics": [
                {
                    "code": "typed_relationship_target_ambiguous",
                    "source_id": "prop-x",
                    "relationship_type": "exception_to",
                    "referenced_locator": "article:1:paragraph:1",
                }
            ],
        },
    }
    report = lint_bundle(bundle)
    assert any("typed_relationship_target_ambiguous" in w for w in report["warnings"])
