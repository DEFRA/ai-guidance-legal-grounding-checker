"""Unit tests for effective-law typed-context DecisionExplanation emission."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from law_proposition_extractor_domain import DecisionStage, DecisionSubjectKind, DecisionType
from law_proposition_extractor_pipeline.effective_law import build_effective_law_statements
from law_proposition_extractor_pipeline.heuristics.effective_law_explanations import (
    bind_effective_law_decision_facts,
    build_effective_law_decision_explanations,
)
from law_proposition_extractor_pipeline.heuristics.registry import (
    RULE_ATTACH_APPLICABLE_EXCEPTION,
    RULE_ATTACH_EXCEPTION_TARGET,
    RULE_ATTACH_TRIGGER_CONDITION,
    RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR,
    list_heuristics,
    require_heuristic,
)
from law_proposition_extractor_pipeline.legal_rule_groups import build_legal_rule_groups
from law_proposition_extractor_pipeline.legal_rule_relationships import build_legal_rule_relationships

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)

SOURCE = "src-control-regulation-demo"
SNAPSHOT = "snap-src-control-regulation-demo-v1"

P1 = "prop-demo-49a-p1-separate"
P2 = "prop-demo-49a-p1-no-mixing"
E1 = "prop-demo-49a-p2-pelagic"
E2 = "prop-demo-49a-p2-industrial"
E3 = "prop-demo-49a-p2-small-vessels"
P3 = "prop-demo-49a-p3-monitoring"


def _load() -> tuple[list[dict], list[dict], dict, dict]:
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
                "proposition_tier": "substantive_rule",
                "is_compliance_relevant": True,
                "explicit_cross_reference_targets": list(
                    row.get("explicit_cross_reference_targets") or []
                ),
                "extraction_debug_meta": dict(row.get("extraction_debug_meta") or {}),
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
    groups = build_legal_rule_groups(props, run_id="run-el", source_fragments=frags)
    groups_clean = {k: v for k, v in groups.items() if k != "decision_facts"}
    rels = build_legal_rule_relationships(
        props,
        run_id="run-el",
        source_fragments=frags,
        legal_rule_groups=groups_clean,
    )
    rels_clean = {k: v for k, v in rels.items() if k != "decision_facts"}
    return props, frags, groups_clean, rels_clean


def _build_statements():
    props, frags, groups, rels = _load()
    payload = build_effective_law_statements(
        props,
        run_id="run-el",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=rels,
    )
    return props, frags, groups, rels, payload


def test_registry_effective_law_rules() -> None:
    for rule_id in (
        RULE_ATTACH_APPLICABLE_EXCEPTION,
        RULE_ATTACH_EXCEPTION_TARGET,
        RULE_ATTACH_TRIGGER_CONDITION,
        RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR,
    ):
        rule = require_heuristic(rule_id)
        assert rule.version == "1"
        assert rule.stage == DecisionStage.EFFECTIVE_LAW
    ids = [h.rule_id for h in list_heuristics()]
    assert ids == sorted(ids)


def test_exception_to_expands_to_applicable_and_exception_target() -> None:
    _props, _frags, groups, rels, payload = _build_statements()
    bound = bind_effective_law_decision_facts(
        payload["decision_facts"],
        statements=payload["statements"],
    )
    expls = build_effective_law_decision_explanations(bound)
    applicable = [e for e in expls if e.rule_id == RULE_ATTACH_APPLICABLE_EXCEPTION]
    targets = [e for e in expls if e.rule_id == RULE_ATTACH_EXCEPTION_TARGET]
    # Fixture includes art30/art31 as well; filter to 49a props.
    article_props = {P1, P2, E1, E2, E3, P3}
    applicable_49a = [
        e
        for e in applicable
        if e.metadata.get("receiving_proposition_id") in article_props
        and e.metadata.get("context_proposition_id") in article_props
    ]
    targets_49a = [
        e
        for e in targets
        if e.metadata.get("receiving_proposition_id") in article_props
        and e.metadata.get("context_proposition_id") in article_props
    ]
    assert len(applicable_49a) == 6
    assert len(targets_49a) == 6
    p1_group = next(
        g
        for g in groups["groups"]
        if g.get("canonical_locator") == "article:49a:paragraph:1"
    )
    for expl in applicable_49a:
        assert expl.decision_type == DecisionType.ATTACH
        assert expl.subject_kind == DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT
        assert expl.outcome == "applicable_exception_attached"
        assert expl.metadata["inherited_via_group"] is True
        assert expl.metadata["legal_rule_group_id"] == p1_group["id"]


def test_trigger_condition_source_only() -> None:
    _props, _frags, groups, _rels, payload = _build_statements()
    bound = bind_effective_law_decision_facts(
        payload["decision_facts"],
        statements=payload["statements"],
    )
    expls = build_effective_law_decision_explanations(bound)
    triggers = [
        e
        for e in expls
        if e.rule_id == RULE_ATTACH_TRIGGER_CONDITION
        and e.metadata.get("receiving_proposition_id") == P3
    ]
    assert len(triggers) == 3
    p2_group = next(
        g
        for g in groups["groups"]
        if g.get("canonical_locator") == "article:49a:paragraph:2"
    )
    for expl in triggers:
        assert expl.metadata["expansion_direction"] == "source_only"
        assert expl.metadata["inherited_via_group"] is True
        assert expl.metadata["legal_rule_group_id"] == p2_group["id"]
    reverse = [
        e
        for e in expls
        if e.rule_id == RULE_ATTACH_TRIGGER_CONDITION
        and e.metadata.get("receiving_proposition_id") in {E1, E2, E3}
    ]
    assert reverse == []


def test_direct_proposition_target_does_not_claim_group_inheritance() -> None:
    _props, _frags, _groups, _rels, payload = _build_statements()
    bound = bind_effective_law_decision_facts(
        payload["decision_facts"],
        statements=payload["statements"],
    )
    expls = build_effective_law_decision_explanations(bound)
    art30 = [
        e
        for e in expls
        if e.rule_id == RULE_ATTACH_APPLICABLE_EXCEPTION
        and e.metadata.get("receiving_proposition_id") == "prop-demo-art30-p1-only"
    ]
    assert art30
    assert all(e.metadata.get("inherited_via_group") is False for e in art30)


def test_typed_over_generic_suppresses_paragraph_refs_keeps_article_14() -> None:
    _props, _frags, _groups, _rels, payload = _build_statements()
    bound = bind_effective_law_decision_facts(
        payload["decision_facts"],
        statements=payload["statements"],
    )
    expls = build_effective_law_decision_explanations(bound)
    suppress = [
        e
        for e in expls
        if e.rule_id == RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR
        and e.metadata.get("receiving_proposition_id") in {E1, E2, E3, P3}
    ]
    assert len(suppress) >= 4
    assert all(e.decision_type == DecisionType.SUPPRESS for e in suppress)
    for expl in suppress:
        assert expl.metadata.get("typed_relationship_id")
        assert "14" not in str(expl.metadata.get("generic_locator") or "").lower() or (
            "article" not in str(expl.metadata.get("generic_locator") or "").lower()
        )

    stmt_by = {
        s["source_proposition_ids"][0]: s
        for s in payload["statements"]
        if s.get("source_proposition_ids")
    }
    e3_ctx = stmt_by[E3]["required_context"]
    assert any(
        "14" in str(c.get("locator") or "").lower()
        and c.get("kind") not in {
            "applicable_exception",
            "exception_target",
            "trigger_condition",
        }
        for c in e3_ctx
    )
    for role in (E1, E2, E3):
        for c in stmt_by[role]["required_context"]:
            if c.get("kind") in {
                "applicable_exception",
                "exception_target",
                "trigger_condition",
            }:
                continue
            loc = str(c.get("locator") or "").lower()
            if "paragraph 1" in loc or "paragraph:1" in loc:
                raise AssertionError("duplicate generic paragraph-1 context retained")


def test_duplicate_context_entries_produce_one_explanation() -> None:
    _props, _frags, _groups, _rels, payload = _build_statements()
    bound = bind_effective_law_decision_facts(
        payload["decision_facts"],
        statements=payload["statements"],
    )
    expls = build_effective_law_decision_explanations(bound)
    keys = [
        (
            e.rule_id,
            e.subject_id,
            e.metadata.get("context_kind"),
            e.metadata.get("context_proposition_id"),
            e.metadata.get("legal_rule_relationship_id"),
        )
        for e in expls
        if e.decision_type == DecisionType.ATTACH
    ]
    assert len(keys) == len(set(keys))


def test_changing_context_proposition_changes_decision_id() -> None:
    _props, _frags, _groups, _rels, payload = _build_statements()
    bound = bind_effective_law_decision_facts(
        payload["decision_facts"],
        statements=payload["statements"],
    )
    expls = build_effective_law_decision_explanations(bound)
    p1_apps = [
        e
        for e in expls
        if e.rule_id == RULE_ATTACH_APPLICABLE_EXCEPTION
        and e.metadata.get("receiving_proposition_id") == P1
    ]
    ids = {e.id for e in p1_apps}
    assert len(ids) == len(p1_apps) >= 2


def test_context_explanation_generation_does_not_rerun_builder() -> None:
    _props, _frags, _groups, _rels, payload = _build_statements()
    facts = bind_effective_law_decision_facts(
        payload["decision_facts"],
        statements=payload["statements"],
    )
    with patch(
        "law_proposition_extractor_pipeline.effective_law.build_effective_law_statements",
        side_effect=AssertionError("effective-law must not be rerun"),
    ):
        expls = build_effective_law_decision_explanations(facts)
    assert expls
    assert all(e.stage == DecisionStage.EFFECTIVE_LAW for e in expls)


def test_monkeypatch_builder_after_fact_capture_does_not_break_explanations() -> None:
    _props, _frags, _groups, _rels, payload = _build_statements()
    facts = list(payload["decision_facts"])
    statements = list(payload["statements"])

    def _boom(*_a, **_k):
        raise AssertionError("builder should not be consulted")

    with patch("law_proposition_extractor_pipeline.effective_law.build_effective_law_statements", _boom):
        with patch("law_proposition_extractor_pipeline.legal_rule_groups.build_legal_rule_groups", _boom):
            bound = bind_effective_law_decision_facts(facts, statements=statements)
            expls = build_effective_law_decision_explanations(bound)
    assert any(e.rule_id == RULE_ATTACH_APPLICABLE_EXCEPTION for e in expls)
