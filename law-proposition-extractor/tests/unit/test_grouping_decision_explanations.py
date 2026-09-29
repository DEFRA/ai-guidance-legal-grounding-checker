"""Unit tests for legal-rule grouping DecisionExplanation emission."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from law_proposition_extractor_domain import DecisionStage, DecisionSubjectKind, DecisionType
from law_proposition_extractor_pipeline.heuristics.grouping_explanations import (
    build_grouping_decision_explanations,
)
from law_proposition_extractor_pipeline.heuristics.registry import (
    RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP,
    list_heuristics,
    require_heuristic,
)
from law_proposition_extractor_pipeline.legal_rule_groups import build_legal_rule_groups

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)

SOURCE = "src-control-regulation-demo"
SNAPSHOT = "snap-src-control-regulation-demo-v1"


def _load() -> tuple[list[dict], list[dict]]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    props = []
    for row in payload["exported_propositions"]:
        props.append(
            {
                "id": row["id"],
                "source_record_id": SOURCE,
                "source_snapshot_id": SNAPSHOT,
                "source_fragment_id": row["source_fragment_id"],
                "fragment_locator": row["fragment_locator"],
                "source_order": row.get("source_order"),
                "proposition_text": row["proposition_text"],
                "legal_effect_type": row.get("legal_effect_type") or "obligation",
            }
        )
    frags = []
    for item in payload["fragments"]:
        frags.append(
            {
                "id": item["id"],
                "source_record_id": SOURCE,
                "source_snapshot_id": SNAPSHOT,
                "locator": item["locator"],
                "fragment_text": item["fragment_text"],
                "parent_fragment_id": item.get("parent_fragment_id"),
                "order_index": item.get("order_index"),
                "fragment_type": item.get("fragment_type"),
                "fragment_hash": "hash-" + item["id"],
            }
        )
    return props, frags


def test_registry_grouping_rule() -> None:
    rule = require_heuristic(RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP)
    assert rule.version == "1"
    assert rule.stage == DecisionStage.GROUPING
    ids = [h.rule_id for h in list_heuristics()]
    assert ids == sorted(ids)
    assert RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP in ids


def test_shared_fragment_two_members_creates_one_group_explanation() -> None:
    props, frags = _load()
    p1_props = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:1")
    ]
    assert len(p1_props) == 2
    result = build_legal_rule_groups(p1_props, run_id="run-g", source_fragments=frags)
    expls = build_grouping_decision_explanations(result["decision_facts"])
    assert len(expls) == 1
    expl = expls[0]
    assert expl.rule_id == RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP
    assert expl.outcome == "group_created"
    assert expl.decision_type == DecisionType.GROUP
    assert expl.subject_kind == DecisionSubjectKind.LEGAL_RULE_GROUP
    assert expl.subject_id == result["groups"][0]["id"]
    assert set(expl.metadata["member_proposition_ids"]) == {p["id"] for p in p1_props}


def test_shared_fragment_three_members_creates_one_group_explanation() -> None:
    props, frags = _load()
    p2_props = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:2")
    ]
    assert len(p2_props) == 3
    result = build_legal_rule_groups(p2_props, run_id="run-g", source_fragments=frags)
    expls = build_grouping_decision_explanations(result["decision_facts"])
    assert len(expls) == 1
    assert expls[0].metadata["member_count"] == 3


def test_single_proposition_creates_no_group() -> None:
    props, frags = _load()
    p3 = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:3")
    ]
    assert len(p3) == 1
    result = build_legal_rule_groups(p3, run_id="run-g", source_fragments=frags)
    assert result["groups"] == []
    assert result["decision_facts"] == []
    assert build_grouping_decision_explanations(result["decision_facts"]) == []


def test_different_fragments_do_not_group() -> None:
    props, frags = _load()
    mixed = [
        next(p for p in props if p["id"] == "prop-demo-49a-p1-separate"),
        next(p for p in props if p["id"] == "prop-demo-49a-p3-monitoring"),
    ]
    result = build_legal_rule_groups(mixed, run_id="run-g", source_fragments=frags)
    assert result["groups"] == []
    assert result["decision_facts"] == []


def test_different_snapshots_do_not_group() -> None:
    props, frags = _load()
    p1 = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:1")
    ]
    altered = [dict(p1[0]), dict(p1[1])]
    altered[1]["source_snapshot_id"] = "snap-other"
    result = build_legal_rule_groups(altered, run_id="run-g", source_fragments=frags)
    assert result["groups"] == []


def test_different_source_records_do_not_group() -> None:
    props, frags = _load()
    p1 = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:1")
    ]
    altered = [dict(p1[0]), dict(p1[1])]
    altered[1]["source_record_id"] = "src-other"
    result = build_legal_rule_groups(altered, run_id="run-g", source_fragments=frags)
    assert result["groups"] == []


def test_member_ordering_deterministic_and_id_stable() -> None:
    props, frags = _load()
    p1 = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:1")
    ]
    a = build_legal_rule_groups(p1, run_id="run-g", source_fragments=frags)
    b = build_legal_rule_groups(list(reversed(p1)), run_id="run-g", source_fragments=frags)
    assert a["groups"][0]["member_proposition_ids"] == b["groups"][0]["member_proposition_ids"]
    ea = build_grouping_decision_explanations(a["decision_facts"])
    eb = build_grouping_decision_explanations(b["decision_facts"])
    assert ea[0].id == eb[0].id


def test_changing_membership_changes_decision_id() -> None:
    props, frags = _load()
    p2 = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:2")
    ]
    full = build_legal_rule_groups(p2, run_id="run-g", source_fragments=frags)
    subset = build_legal_rule_groups(p2[:2], run_id="run-g", source_fragments=frags)
    full_id = build_grouping_decision_explanations(full["decision_facts"])[0].id
    subset_id = build_grouping_decision_explanations(subset["decision_facts"])[0].id
    assert full_id != subset_id


def test_group_explanation_generation_does_not_call_builder() -> None:
    props, frags = _load()
    result = build_legal_rule_groups(props, run_id="run-g", source_fragments=frags)
    facts = result["decision_facts"]
    with patch(
        "law_proposition_extractor_pipeline.legal_rule_groups.build_legal_rule_groups",
        side_effect=AssertionError("grouping must not be rerun"),
    ):
        expls = build_grouping_decision_explanations(facts)
    assert expls
    assert all(e.stage == DecisionStage.GROUPING for e in expls)
