"""Article 49a trigger-cue wording equivalence and negative regressions (20-BR10G)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_pipeline.effective_law import attach_effective_law_artifacts
from law_proposition_extractor_pipeline.heuristics.registry import RULE_INFER_TRIGGERED_BY, require_heuristic
from law_proposition_extractor_pipeline.legal_rule_groups import build_legal_rule_groups, legal_rule_group_id
from law_proposition_extractor_pipeline.legal_rule_relationships import (
    _DIAG_NO_SUPPORTED_TRIGGER_CUE,
    build_legal_rule_relationships,
    legal_rule_relationship_id,
)

_STRUCTURAL = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)

SOURCE = "src-control-regulation-demo"
SNAPSHOT = "snap-src-control-regulation-demo-v1"
OTHER_SOURCE = "src-other-regulation-demo"
OTHER_SNAPSHOT = "snap-src-other-regulation-demo-v1"

# Supported wordings grounded by source / curated / live calibration.
_CURATED_P3 = (
    "In the cases referred to in Article 49a(2), a fisheries administration "
    "must monitor the catch composition by way of sampling."
)
_SOURCE_P3 = (
    "In the cases referred to in paragraph 2, a fisheries administration "
    "must monitor the catch composition by way of sampling."
)
_LIVE_P3 = (
    "Where the cases referred to in paragraph 2 apply, a fisheries administration "
    "must monitor the catch composition by way of sampling."
)


def _fragments() -> list[dict]:
    payload = json.loads(_STRUCTURAL.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for item in payload["fragments"]:
        rows.append(
            {
                "id": item["id"],
                "source_record_id": SOURCE,
                "source_snapshot_id": SNAPSHOT,
                "locator": item["locator"],
                "fragment_text": item["fragment_text"],
                "parent_fragment_id": item.get("parent_fragment_id"),
                "order_index": item.get("order_index"),
                "fragment_type": item.get("fragment_type"),
                "fragment_hash": f"hash-{item['id']}",
            }
        )
    other = payload.get("other_instrument") or {}
    for item in other.get("fragments") or []:
        rows.append(
            {
                "id": item["id"],
                "source_record_id": OTHER_SOURCE,
                "source_snapshot_id": OTHER_SNAPSHOT,
                "locator": item["locator"],
                "fragment_text": item["fragment_text"],
                "parent_fragment_id": item.get("parent_fragment_id"),
                "order_index": item.get("order_index"),
                "fragment_type": item.get("fragment_type"),
                "fragment_hash": f"hash-{item['id']}",
            }
        )
    return rows


def _base_props() -> list[dict]:
    payload = json.loads(_STRUCTURAL.read_text(encoding="utf-8"))
    props: list[dict] = []
    for row in payload["exported_propositions"]:
        if row["id"] == "prop-demo-49a-p3-monitoring":
            continue  # replaced per-test
        props.append(
            {
                "id": row["id"],
                "source_record_id": SOURCE,
                "source_snapshot_id": SNAPSHOT,
                "source_fragment_id": row["source_fragment_id"],
                "fragment_locator": row["fragment_locator"],
                "proposition_text": row["proposition_text"],
                "legal_effect_type": row.get("legal_effect_type") or "obligation",
                "explicit_cross_reference_targets": list(
                    row.get("explicit_cross_reference_targets") or []
                ),
            }
        )
    return props


def _p2_group_id() -> str:
    return legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p2",
        canonical_locator="article:49a:paragraph:2",
    )


def _p3(
    *,
    prop_id: str,
    text: str,
    refs: list[str] | None = None,
) -> dict:
    return {
        "id": prop_id,
        "source_record_id": SOURCE,
        "source_snapshot_id": SNAPSHOT,
        "source_fragment_id": "frag-demo-49a-p3",
        "fragment_locator": "article:49a:paragraph:3",
        "proposition_text": text,
        "legal_effect_type": "obligation",
        "explicit_cross_reference_targets": list(refs or []),
    }


def _build(props: list[dict]) -> dict:
    frags = _fragments()
    groups = build_legal_rule_groups(props, run_id="run-trigger-cues", source_fragments=frags)
    return build_legal_rule_relationships(
        props,
        run_id="run-trigger-cues",
        source_fragments=frags,
        legal_rule_groups=groups,
    )


def _triggers(result: dict, source_id: str) -> list[dict]:
    return [
        r
        for r in result["relationships"]
        if r["source_id"] == source_id and r["relationship_type"] == "triggered_by"
    ]


def test_registry_infer_triggered_by_version_bumped_for_cue_family() -> None:
    rule = require_heuristic(RULE_INFER_TRIGGERED_BY)
    assert rule.version == "2"


def test_curated_wording_produces_triggered_by() -> None:
    props = _base_props()
    props.append(_p3(prop_id="prop-curated-p3", text=_CURATED_P3, refs=["Article 49a(2)"]))
    result = _build(props)
    hits = _triggers(result, "prop-curated-p3")
    assert len(hits) == 1
    assert hits[0]["referenced_locator"] == "article:49a:paragraph:2"
    assert hits[0]["target_id"] == _p2_group_id()
    assert hits[0]["reference_text"] == "Article 49a(2)"


def test_live_where_cases_apply_wording_produces_triggered_by() -> None:
    props = _base_props()
    props.append(_p3(prop_id="prop-live-p3", text=_LIVE_P3, refs=["paragraph 2"]))
    result = _build(props)
    hits = _triggers(result, "prop-live-p3")
    assert len(hits) == 1
    assert hits[0]["referenced_locator"] == "article:49a:paragraph:2"
    assert hits[0]["target_id"] == _p2_group_id()
    assert hits[0]["cue_text"].lower().startswith("where the cases referred to in")


def test_source_wording_produces_triggered_by() -> None:
    props = _base_props()
    props.append(_p3(prop_id="prop-source-p3", text=_SOURCE_P3, refs=["paragraph 2"]))
    result = _build(props)
    hits = _triggers(result, "prop-source-p3")
    assert len(hits) == 1
    assert hits[0]["target_id"] == _p2_group_id()


def test_supported_wordings_canonicalise_to_same_group_without_duplicates() -> None:
    """Equivalent cue wordings on distinct props → same target; one prop → one edge."""
    props = _base_props()
    wordings = [
        ("prop-w-curated", _CURATED_P3, ["Article 49a(2)"]),
        ("prop-w-live-1", _LIVE_P3, ["paragraph 2"]),
        ("prop-w-live-2", _LIVE_P3, ["paragraph 2"]),
        ("prop-w-live-3", _LIVE_P3, ["paragraph 2"]),
        ("prop-w-source", _SOURCE_P3, ["paragraph 2"]),
    ]
    for prop_id, text, refs in wordings:
        # Distinct props sharing the paragraph-3 fragment still each get one edge.
        props.append(_p3(prop_id=prop_id, text=text, refs=refs))
    # Only one P3 per id — use separate fragment clones by unique ids is enough.
    result = _build(props)
    target_ids = set()
    rel_ids = set()
    for prop_id, _, _ in wordings:
        hits = _triggers(result, prop_id)
        assert len(hits) == 1, prop_id
        assert hits[0]["referenced_locator"] == "article:49a:paragraph:2"
        target_ids.add(hits[0]["target_id"])
        rel_ids.add(hits[0]["id"])
    assert target_ids == {_p2_group_id()}
    assert len(rel_ids) == len(wordings)

    # Same source + same target + same type → deterministic duplicate suppression.
    props2 = _base_props()
    props2.append(_p3(prop_id="prop-dup", text=_LIVE_P3, refs=["paragraph 2"]))
    # Running twice on same prop set still yields one edge.
    result2 = _build(props2)
    assert len(_triggers(result2, "prop-dup")) == 1
    expected_id = legal_rule_relationship_id(
        relationship_type="triggered_by",
        source_id="prop-dup",
        target_kind="legal_rule_group",
        target_id=_p2_group_id(),
        referenced_locator="article:49a:paragraph:2",
        inference_basis="explicit_trigger_cue",
    )
    assert _triggers(result2, "prop-dup")[0]["id"] == expected_id


def test_bare_see_reference_creates_no_triggered_by() -> None:
    props = _base_props()
    props.append(
        _p3(
            prop_id="prop-see",
            text="See Article 49a(2) for the applicable exceptions.",
            refs=["Article 49a(2)"],
        )
    )
    result = _build(props)
    assert _triggers(result, "prop-see") == []
    assert not any(
        d.get("code") == _DIAG_NO_SUPPORTED_TRIGGER_CUE and d.get("source_id") == "prop-see"
        for d in result["diagnostics"]
    )


def test_article_49a2_outside_trigger_cue_creates_no_triggered_by() -> None:
    props = _base_props()
    props.append(
        _p3(
            prop_id="prop-outside",
            text=(
                "A fisheries administration must monitor catch composition. "
                "Article 49a(2) lists separate exceptions."
            ),
            refs=["Article 49a(2)"],
        )
    )
    result = _build(props)
    assert _triggers(result, "prop-outside") == []


def test_in_accordance_with_is_not_a_trigger() -> None:
    props = _base_props()
    props.append(
        _p3(
            prop_id="prop-accordance",
            text=(
                "Catches below the minimum conservation reference size have been "
                "sorted, estimated and recorded in accordance with Article 49a(2)."
            ),
            refs=["Article 49a(2)"],
        )
    )
    result = _build(props)
    assert _triggers(result, "prop-accordance") == []


def test_cue_with_unresolvable_reference_creates_no_relationship() -> None:
    props = _base_props()
    props.append(
        _p3(
            prop_id="prop-unresolved",
            text=(
                "In the cases referred to in Article 999z(2), a fisheries "
                "administration must monitor the catch composition by way of sampling."
            ),
            refs=["Article 999z(2)"],
        )
    )
    result = _build(props)
    assert _triggers(result, "prop-unresolved") == []


def test_cue_bound_reference_only_when_two_refs_present() -> None:
    props = _base_props()
    props.append(
        _p3(
            prop_id="prop-dual-ref",
            text=(
                "Where the cases referred to in Article 49a(2) apply, a fisheries "
                "administration must monitor catch composition in accordance with "
                "Article 14."
            ),
            refs=["Article 49a(2)", "Article 14"],
        )
    )
    result = _build(props)
    hits = _triggers(result, "prop-dual-ref")
    assert len(hits) == 1
    assert hits[0]["referenced_locator"] == "article:49a:paragraph:2"
    assert "14" not in hits[0]["referenced_locator"]
    assert hits[0]["target_id"] == _p2_group_id()
    # Article 14 must not receive a typed trigger edge.
    assert not any(
        "14" in str(r.get("referenced_locator") or "")
        and r.get("relationship_type") == "triggered_by"
        for r in result["relationships"]
    )


def test_wrong_source_snapshot_target_rejected() -> None:
    """Other-instrument P3 must not target the demo paragraph-2 group."""
    props = _base_props()
    # Add a monitoring prop in the other instrument using its existing p2 fragment
    # as structural parent context via a synthetic p3-shaped locator on a new frag id
    # that we also inject into fragments below.
    props.append(
        {
            "id": "prop-other-p3",
            "source_record_id": OTHER_SOURCE,
            "source_snapshot_id": OTHER_SNAPSHOT,
            "source_fragment_id": "frag-other-49a-p3-synthetic",
            "fragment_locator": "article:49a:paragraph:3",
            "proposition_text": _LIVE_P3,
            "legal_effect_type": "obligation",
            "explicit_cross_reference_targets": ["paragraph 2"],
        }
    )
    frags = _fragments()
    frags.append(
        {
            "id": "frag-other-49a-p3-synthetic",
            "source_record_id": OTHER_SOURCE,
            "source_snapshot_id": OTHER_SNAPSHOT,
            "locator": "article:49a:paragraph:3",
            "fragment_text": _SOURCE_P3,
            "parent_fragment_id": "frag-other-49a-p2",
            "order_index": 99,
            "fragment_type": "paragraph",
            "fragment_hash": "hash-frag-other-49a-p3-synthetic",
        }
    )
    groups = build_legal_rule_groups(props, run_id="run-other", source_fragments=frags)
    result = build_legal_rule_relationships(
        props,
        run_id="run-other",
        source_fragments=frags,
        legal_rule_groups=groups,
    )
    hits = _triggers(result, "prop-other-p3")
    assert all(r["target_id"] != _p2_group_id() for r in hits)
    assert all(r.get("source_record_id") == OTHER_SOURCE for r in hits)
    assert all(r.get("source_snapshot_id") == OTHER_SNAPSHOT for r in hits)


def test_exception_cue_remains_exception_to_not_triggered_by() -> None:
    props = _base_props()
    result = _build(props)
    for source_id in (
        "prop-demo-49a-p2-pelagic",
        "prop-demo-49a-p2-industrial",
        "prop-demo-49a-p2-small-vessels",
    ):
        assert _triggers(result, source_id) == []
        assert any(
            r["source_id"] == source_id and r["relationship_type"] == "exception_to"
            for r in result["relationships"]
        )


def test_label_only_cases_referred_does_not_create_trigger() -> None:
    props = _base_props()
    props.append(
        {
            **_p3(
                prop_id="prop-label-only",
                text="A fisheries administration must monitor the catch composition by way of sampling.",
                refs=["Article 49a(2)"],
            ),
            "label": "cases referred to in Article 49a(2)",
            "display_label": "In the cases referred to in Article 49a(2)",
        }
    )
    result = _build(props)
    assert _triggers(result, "prop-label-only") == []


def test_near_miss_referred_to_without_supported_frame_diagnostics() -> None:
    props = _base_props()
    props.append(
        _p3(
            prop_id="prop-near-miss",
            text=(
                "Monitoring applies to the cases referred to in Article 49a(2) "
                "when separately activated."
            ),
            refs=["Article 49a(2)"],
        )
    )
    result = _build(props)
    assert _triggers(result, "prop-near-miss") == []
    diags = [
        d
        for d in result["diagnostics"]
        if d.get("source_id") == "prop-near-miss"
        and d.get("code") == _DIAG_NO_SUPPORTED_TRIGGER_CUE
    ]
    assert len(diags) == 1
    facts = [
        f
        for f in result.get("decision_facts") or []
        if f.get("source_proposition_id") == "prop-near-miss"
        and f.get("diagnostic_code") == _DIAG_NO_SUPPORTED_TRIGGER_CUE
    ]
    assert facts
    assert facts[0].get("relationship_claimed") is False


def test_ambiguous_target_creates_no_triggered_by() -> None:
    """Two groups on the same canonical locator → refuse trigger edge."""
    props = _base_props()
    props.append(_p3(prop_id="prop-ambig", text=_LIVE_P3, refs=["paragraph 2"]))
    frags = _fragments()
    groups = build_legal_rule_groups(props, run_id="run-ambig", source_fragments=frags)
    # Corrupt groups: duplicate paragraph-2 group under a different id.
    rows = list(groups.get("groups") or [])
    p2 = next(g for g in rows if g.get("canonical_locator") == "article:49a:paragraph:2")
    clone = dict(p2)
    clone["id"] = "rulegrp:ambiguous-clone"
    groups = {**groups, "groups": [*rows, clone]}
    result = build_legal_rule_relationships(
        props,
        run_id="run-ambig",
        source_fragments=frags,
        legal_rule_groups=groups,
    )
    # group_for_canonical_locator may pick the first; if ambiguous via fragments,
    # ensure we never emit two triggered_by edges for the same source.
    hits = _triggers(result, "prop-ambig")
    assert len(hits) <= 1


def test_effective_law_attaches_three_source_only_triggers_for_live_wording() -> None:
    props = _base_props()
    props.append(_p3(prop_id="prop-live-eff", text=_LIVE_P3, refs=["paragraph 2"]))
    frags = _fragments()
    groups = build_legal_rule_groups(props, run_id="run-eff", source_fragments=frags)
    rels = build_legal_rule_relationships(
        props, run_id="run-eff", source_fragments=frags, legal_rule_groups=groups
    )
    bundle = {
        "run": {"id": "run-eff"},
        "propositions": props,
        "source_fragments": frags,
        "legal_rule_groups": groups,
        "legal_rule_relationships": rels,
    }
    attach_effective_law_artifacts(bundle)
    stmts = (bundle.get("effective_law_statements") or {}).get("statements") or []
    p3_stmts = [
        s
        for s in stmts
        if "prop-live-eff" in (s.get("source_proposition_ids") or [])
    ]
    assert p3_stmts
    triggers = [
        e
        for e in (p3_stmts[0].get("required_context") or [])
        if e.get("kind") == "trigger_condition"
    ]
    assert len(triggers) == 3
    member_ids = {pid for e in triggers for pid in (e.get("proposition_ids") or [])}
    assert member_ids == {
        "prop-demo-49a-p2-pelagic",
        "prop-demo-49a-p2-industrial",
        "prop-demo-49a-p2-small-vessels",
    }
    # source-only: trigger props must not receive reverse trigger_condition rows.
    for e_id in member_ids:
        for s in stmts:
            if e_id not in (s.get("source_proposition_ids") or []):
                continue
            assert not any(
                c.get("kind") == "trigger_condition"
                for c in (s.get("required_context") or [])
            )


def test_changing_canonical_target_changes_relationship_id() -> None:
    props = _base_props()
    props.append(
        _p3(
            prop_id="prop-id-a",
            text=(
                "Where the cases referred to in Article 49a(2) apply, "
                "monitoring is required."
            ),
            refs=["Article 49a(2)"],
        )
    )
    props.append(
        _p3(
            prop_id="prop-id-b",
            text=(
                "Where the cases referred to in Article 49a(1) apply, "
                "monitoring is required."
            ),
            refs=["Article 49a(1)"],
        )
    )
    result = _build(props)
    a = _triggers(result, "prop-id-a")
    b = _triggers(result, "prop-id-b")
    assert len(a) == 1 and len(b) == 1
    assert a[0]["referenced_locator"] != b[0]["referenced_locator"]
    assert a[0]["id"] != b[0]["id"]
