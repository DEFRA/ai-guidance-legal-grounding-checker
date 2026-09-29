"""Unit tests for typed relationship DecisionExplanation emission."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import DecisionStage, DecisionSubjectKind, DecisionType, HeuristicMethod
from law_proposition_extractor_pipeline.heuristics.registry import (
    RULE_INFER_EXCEPTION_TO,
    RULE_INFER_TRIGGERED_BY,
    RULE_INFERENCE_UNRESOLVED,
    RULE_PREFER_GROUP_TARGET,
    get_heuristic,
    list_heuristics,
    require_heuristic,
)
from law_proposition_extractor_pipeline.heuristics.relationship_explanations import (
    build_relationship_decision_explanations,
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


def _load() -> tuple[list[dict], list[dict], dict]:
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
                "proposition_text": row["proposition_text"],
                "legal_effect_type": row.get("legal_effect_type") or "obligation",
                "explicit_cross_reference_targets": list(
                    row.get("explicit_cross_reference_targets") or []
                ),
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
                "fragment_hash": f"hash-{item['id']}",
            }
        )
    groups = build_legal_rule_groups(props, run_id="run-rel-expl", source_fragments=frags)
    return props, frags, groups


def test_registry_relationship_rules() -> None:
    for rule_id in (
        RULE_INFER_EXCEPTION_TO,
        RULE_INFER_TRIGGERED_BY,
        RULE_PREFER_GROUP_TARGET,
        RULE_INFERENCE_UNRESOLVED,
    ):
        rule = require_heuristic(rule_id)
        if rule_id == RULE_INFER_TRIGGERED_BY:
            assert rule.version == "2"
        else:
            assert rule.version == "1"
        assert rule.stage == DecisionStage.RELATIONSHIP
        assert get_heuristic(rule_id) is not None
    ids = [h.rule_id for h in list_heuristics()]
    assert ids == sorted(ids)


def test_exception_and_trigger_emit_inference_and_group_target() -> None:
    props, frags, groups = _load()
    result = build_legal_rule_relationships(
        props,
        run_id="run-rel-expl",
        source_fragments=frags,
        legal_rule_groups=groups,
    )
    facts = result["decision_facts"]
    explanations = build_relationship_decision_explanations(facts)
    article_49a_prop_ids = {
        p["id"] for p in props if "49a" in str(p.get("fragment_locator") or "")
    }
    infer_exception = [
        e
        for e in explanations
        if e.rule_id == RULE_INFER_EXCEPTION_TO
        and str((e.metadata or {}).get("source_proposition_id") or "") in article_49a_prop_ids
    ]
    infer_trigger = [
        e
        for e in explanations
        if e.rule_id == RULE_INFER_TRIGGERED_BY
        and str((e.metadata or {}).get("source_proposition_id") or "") in article_49a_prop_ids
    ]
    prefer = [
        e
        for e in explanations
        if e.rule_id == RULE_PREFER_GROUP_TARGET
        and e.subject_id
        in {x.subject_id for x in infer_exception} | {x.subject_id for x in infer_trigger}
    ]
    assert len(infer_exception) == 3
    assert len(infer_trigger) == 1
    assert len(prefer) == 4
    for expl in infer_exception:
        assert expl.stage == DecisionStage.RELATIONSHIP
        assert expl.decision_type == DecisionType.INFER
        assert expl.subject_kind == DecisionSubjectKind.LEGAL_RULE_RELATIONSHIP
        assert expl.outcome == "inferred_exception_to"
        assert expl.method == HeuristicMethod.DETERMINISTIC
        canon = next(e.value for e in expl.evidence if e.kind == "canonical_target_locator")
        assert canon == "article:49a:paragraph:1"
        assert next(e.value for e in expl.evidence if e.kind == "cue_text")
        assert next(e.value for e in expl.evidence if e.kind == "cue_bound_reference")
        assert next(e.value for e in expl.evidence if e.kind == "resolution_basis")
    trigger = infer_trigger[0]
    assert trigger.outcome == "inferred_triggered_by"
    assert (
        next(e.value for e in trigger.evidence if e.kind == "canonical_target_locator")
        == "article:49a:paragraph:2"
    )
    for expl in prefer:
        assert expl.decision_type == DecisionType.TARGET
        assert expl.outcome == "targeted_legal_rule_group"
        members = [
            e.value for e in expl.evidence if e.kind == "group_member_proposition_id"
        ]
        assert members == sorted(members)
        assert members


def test_article_14_not_selected_as_exception_target() -> None:
    props, frags, groups = _load()
    result = build_legal_rule_relationships(
        props,
        run_id="run-rel-expl",
        source_fragments=frags,
        legal_rule_groups=groups,
    )
    explanations = build_relationship_decision_explanations(result["decision_facts"])
    for expl in explanations:
        if expl.rule_id != RULE_INFER_EXCEPTION_TO:
            continue
        canon = next(
            (e.value for e in expl.evidence if e.kind == "canonical_target_locator"),
            "",
        )
        assert "article:14" not in canon
        assert not canon.endswith(":14")
    # E3-shaped small-vessel exception should retain Article 14 as unselected ordinary.
    e3 = next(
        p
        for p in props
        if "Article 14" in (p.get("proposition_text") or "")
        or any("14" in str(t) for t in (p.get("explicit_cross_reference_targets") or []))
    )
    e3_rel = next(
        r
        for r in result["relationships"]
        if r["source_id"] == e3["id"] and r["relationship_type"] == "exception_to"
    )
    e3_expl = next(e for e in explanations if e.subject_id == e3_rel["id"])
    unselected = [
        e.value for e in e3_expl.evidence if e.kind == "unselected_ordinary_reference"
    ]
    assert any("14" in u for u in unselected)
    reasons = [
        e.value
        for e in e3_expl.evidence
        if e.kind == "unselected_ordinary_reference_reason"
    ]
    assert "outside_typed_relationship_cue" in reasons


def test_generic_reference_without_typed_cue_emits_no_typed_explanation() -> None:
    props = [
        {
            "id": "prop:ordinary0000001",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "source_fragment_id": "frag-x",
            "fragment_locator": "article:10",
            "proposition_text": "Operators shall comply in accordance with Article 14.",
            "legal_effect_type": "obligation",
            "explicit_cross_reference_targets": ["Article 14"],
        }
    ]
    frags = [
        {
            "id": "frag-x",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "locator": "article:10",
            "fragment_text": props[0]["proposition_text"],
            "fragment_hash": "hash-x",
        }
    ]
    result = build_legal_rule_relationships(
        props, run_id="run-ordinary", source_fragments=frags, legal_rule_groups={"groups": []}
    )
    assert result["relationships"] == []
    assert result["decision_facts"] == []
    assert build_relationship_decision_explanations([]) == []


def test_equivalent_reference_forms_do_not_duplicate_explanations() -> None:
    props, frags, groups = _load()
    a = build_legal_rule_relationships(
        props, run_id="run-a", source_fragments=frags, legal_rule_groups=groups
    )
    b = build_legal_rule_relationships(
        list(reversed(props)),
        run_id="run-b",
        source_fragments=list(reversed(frags)),
        legal_rule_groups=groups,
    )
    ids_a = sorted(
        e.id for e in build_relationship_decision_explanations(a["decision_facts"])
    )
    ids_b = sorted(
        e.id for e in build_relationship_decision_explanations(b["decision_facts"])
    )
    assert ids_a == ids_b
    assert len(ids_a) == len(set(ids_a))


def test_failed_inference_emits_diagnostic_without_claiming_relationship() -> None:
    facts = [
        {
            "fact_kind": "inference_unresolved",
            "candidate_id": "relcand:abc",
            "source_proposition_id": "prop:x",
            "relationship_type": "exception_to",
            "cue_text": "Paragraph 9 shall not apply",
            "reference_text": "Paragraph 9",
            "canonical_target_locator": "",
            "diagnostic_code": "typed_relationship_cue_reference_parse_failed",
            "detail": "cue-captured reference could not be parsed to a canonical locator",
            "relationship_claimed": False,
        }
    ]
    expls = build_relationship_decision_explanations(facts)
    assert len(expls) == 1
    expl = expls[0]
    assert expl.rule_id == RULE_INFERENCE_UNRESOLVED
    assert expl.decision_type == DecisionType.DIAGNOSE
    assert expl.outcome == "cue_reference_parse_failed"
    assert expl.metadata.get("relationship_claimed") is False
    claimed = next(e.value for e in expl.evidence if e.kind == "inference_succeeded")
    assert claimed == "false"


def test_target_selection_not_rerun_from_facts_alone() -> None:
    facts = [
        {
            "fact_kind": "prefer_group_target",
            "relationship_id": "legalrel:deadbeef",
            "target_kind": "legal_rule_group",
            "target_id": "legalgroup:1",
            "canonical_target_locator": "article:49a:paragraph:1",
            "source_record_id": SOURCE,
            "source_snapshot_id": SNAPSHOT,
            "member_proposition_ids": ["prop:a", "prop:b"],
            "selection_basis": "unique_legal_rule_group",
        }
    ]
    expl = build_relationship_decision_explanations(facts)[0]
    assert expl.outcome == "targeted_legal_rule_group"
    members = [
        e.value for e in expl.evidence if e.kind == "group_member_proposition_id"
    ]
    assert members == ["prop:a", "prop:b"]
