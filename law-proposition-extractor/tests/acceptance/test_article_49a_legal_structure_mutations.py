"""Mutation tests: Article 49a acceptance contract catches known regressions."""

from __future__ import annotations

import copy
import json

import pytest

from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    assert_article_49a_legal_structure,
    identify_article_49a_propositions,
    run_article_49a_acceptance_pipeline,
)


@pytest.fixture(scope="module")
def baseline(tmp_path_factory: pytest.TempPathFactory) -> dict:
    work = tmp_path_factory.mktemp("article-49a-acceptance-baseline")
    result = run_article_49a_acceptance_pipeline(work_dir=work)
    return {
        "bundle": result.bundle,
        "roles": result.proposition_ids,
    }


def _bundle(baseline: dict) -> dict:
    return copy.deepcopy(baseline["bundle"])


def test_mutation_duplicate_2_a_i(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    props = bundle["propositions"]
    donor = next(p for p in props if p["id"] == roles["E1"])
    dup = copy.deepcopy(donor)
    dup["id"] = "prop:deadbeefdeadbeef"
    props.append(dup)
    with pytest.raises(AssertionError, match=r"Expected 6 Article 49a propositions|path 2-a-i|paragraph-2"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_missing_2_a_ii(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    bundle["propositions"] = [p for p in bundle["propositions"] if p["id"] != roles["E2"]]
    with pytest.raises(AssertionError, match=r"path 2-a-ii|found 0"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_selected_subparagraph_a(baseline: dict) -> None:
    bundle = _bundle(baseline)
    jobs = bundle["proposition_extraction_jobs"]
    for job in jobs:
        if job.get("fragment_locator") == "article:49a:paragraph:2:subparagraph:a":
            job["selected_for_extraction"] = True
            job["skip_reason"] = None
            job["selection_reason"] = "focus_term"
    with pytest.raises(AssertionError, match=r"subparagraph \(a\).*selected for extraction"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_paragraph_2_group_four_members(baseline: dict) -> None:
    bundle = _bundle(baseline)
    groups = bundle["legal_rule_groups"]["groups"]
    for group in groups:
        if group.get("canonical_locator") == "article:49a:paragraph:2":
            group["member_proposition_ids"] = list(group["member_proposition_ids"]) + [
                "prop:extra0000000000"
            ]
            group["member_count"] = 4
    with pytest.raises(AssertionError, match=r"paragraph-2 group size = 3"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_missing_exception_to(baseline: dict) -> None:
    bundle = _bundle(baseline)
    rels = bundle["legal_rule_relationships"]["relationships"]
    bundle["legal_rule_relationships"]["relationships"] = [
        r for r in rels if r.get("relationship_type") != "exception_to"
    ] + [r for r in rels if r.get("relationship_type") == "exception_to"][:-1]
    with pytest.raises(AssertionError, match=r"3 exception_to"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_article_14_as_exception_target(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    for stmt in bundle["effective_law_statements"]["statements"]:
        if roles["E3"] in (stmt.get("source_proposition_ids") or []):
            stmt["required_context"].append(
                {
                    "kind": "exception_target",
                    "locator": "article:14",
                    "resolution_status": "resolved",
                    "proposition_ids": [],
                }
            )
    with pytest.raises(AssertionError, match=r"Article 14 incorrectly typed as exception_target"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_article_49a_parented_to_article_1(baseline: dict) -> None:
    bundle = _bundle(baseline)
    frags = bundle["source_fragments"]
    art1 = next(f for f in frags if f.get("locator") == "article:1")
    for frag in frags:
        if frag.get("locator") == "article:49a":
            frag["parent_fragment_id"] = art1["id"]
    with pytest.raises(AssertionError, match=r"parented to 'article:1'|parent = title:iv"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_article_1_effect_leaks_to_49a(baseline: dict) -> None:
    bundle = _bundle(baseline)
    effects = bundle["source_legal_effects"]["effects"]
    art1 = next(e for e in effects if e.get("annotation_id") == "c000001")
    links = bundle["source_legal_effects"]["effect_links"]
    links.append(
        {
            "id": "sourceeffectlink:leak",
            "effect_id": art1["id"],
            "affected_locator": "article:49a:paragraph:1",
            "source_fragment_id": "frag-leak",
            "linkage_status": "linked",
        }
    )
    with pytest.raises(AssertionError, match=r"Article 1 effect unexpectedly became relevant"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_retrieval_as_legal_as_of(baseline: dict) -> None:
    bundle = _bundle(baseline)
    snap = bundle["source_snapshots"][0]
    snap["resolved_as_of_date"] = snap["retrieved_at"]
    snap["requested_as_of_date"] = snap["retrieved_at"]
    with pytest.raises(AssertionError, match=r"requested_as_of_date=null|resolved_as_of_date=null"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_outstanding_unknown_as_none(baseline: dict) -> None:
    bundle = _bundle(baseline)
    bundle["source_legal_effects"]["outstanding_effects_status"] = "none"
    with pytest.raises(AssertionError, match=r"outstanding-effect status presented as none|Unexpected outstanding"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_missing_parent_suppression_explanation(baseline: dict) -> None:
    bundle = _bundle(baseline)
    decisions = bundle["decision_explanations"]["decisions"]
    kept = []
    for d in decisions:
        parent_loc = next(
            (
                str(e.get("value") or "")
                for e in (d.get("evidence") or [])
                if isinstance(e, dict)
                and e.get("kind") == "source_locator"
                and e.get("label") == "Parent locator"
            ),
            None,
        )
        if d.get("rule_id") == "selection.prefer_required_children" and parent_loc == "article:49a":
            continue
        kept.append(d)
    bundle["decision_explanations"]["decisions"] = kept
    with pytest.raises(
        AssertionError,
        match=r"prefer_required_children|article:49a.*explanation|exactly one explanation",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_parent_suppression_wrong_rule_id(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        parent_loc = next(
            (
                str(e.get("value") or "")
                for e in (d.get("evidence") or [])
                if isinstance(e, dict)
                and e.get("kind") == "source_locator"
                and e.get("label") == "Parent locator"
            ),
            None,
        )
        if d.get("rule_id") == "selection.prefer_required_children" and parent_loc == "article:49a":
            d["rule_id"] = "selection.focus_term_match"
    with pytest.raises(
        AssertionError,
        match=r"prefer_required_children|exactly one explanation",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_subparagraph_a_missing_preferred_ancestor(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") != "selection.prefer_required_ancestor":
            continue
        d["evidence"] = [
            e
            for e in (d.get("evidence") or [])
            if not (
                isinstance(e, dict)
                and e.get("kind") == "source_locator"
                and e.get("label") == "Preferred ancestor locator"
            )
        ]
    with pytest.raises(
        AssertionError,
        match=r"preferred ancestor locator|paragraph 2\(a\)",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_required_paragraph_labelled_focus(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        loc = next(
            (
                str(e.get("value") or "")
                for e in (d.get("evidence") or [])
                if isinstance(e, dict) and e.get("kind") == "source_locator"
            ),
            "",
        )
        if loc == "article:49a:paragraph:1" and d.get("rule_id") == "selection.required_locator":
            d["rule_id"] = "selection.focus_term_match"
    with pytest.raises(
        AssertionError,
        match=r"required_locator|exactly one explanation|focus_term",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_rule_version_not_in_registry(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") == "selection.required_locator":
            d["rule_version"] = "999"
    with pytest.raises(AssertionError, match=r"rule_version|registry version"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_llm_method_on_deterministic_frontier(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") == "selection.prefer_required_children":
            d["method"] = "llm"
    with pytest.raises(AssertionError, match=r"incorrectly claims LLM method"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_missing_e2_composition_explanation(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    kept = []
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "structured_list.compose_terminal_leaf"
            and d.get("subject_id") == roles["E2"]
        ):
            continue
        kept.append(d)
    bundle["decision_explanations"]["decisions"] = kept
    with pytest.raises(
        AssertionError,
        match=r"compose explanation for path '2-a-ii'|E2 \(2-a-ii\)",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_e2_composition_missing_branch(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "structured_list.compose_terminal_leaf"
            and d.get("subject_id") == roles["E2"]
        ):
            d["evidence"] = [
                e
                for e in (d.get("evidence") or [])
                if not (
                    isinstance(e, dict)
                    and str(e.get("kind") or "").startswith("component_branch")
                )
            ]
    with pytest.raises(
        AssertionError,
        match=r"stem, branch \(a\), and terminal leaf|branch \(a\)",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_e2_composition_marked_llm(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "structured_list.compose_terminal_leaf"
            and d.get("subject_id") == roles["E2"]
        ):
            d["method"] = "llm"
    with pytest.raises(
        AssertionError,
        match=r"deterministic method for structured-list composition",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_compose_path_mismatch(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "structured_list.compose_terminal_leaf"
            and d.get("subject_id") == roles["E2"]
        ):
            meta = d.setdefault("metadata", {})
            meta["structured_list_path"] = "2-a-i"
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "structured_list_path":
                    e["value"] = "2-a-i"
    with pytest.raises(
        AssertionError,
        match=r"compose explanation for path '2-a-ii'|path 2-a-ii",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_e2_classified_as_obligation(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "classification.derive_legal_effect"
            and d.get("subject_id") == roles["E2"]
        ):
            d["outcome"] = "classified_as_obligation"
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "legal_effect_type":
                    e["value"] = "obligation"
    with pytest.raises(
        AssertionError,
        match=r"E2.*classification outcome.*derogation|classified_as_derogation",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_e2_missing_classification_explanation(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    bundle["decision_explanations"]["decisions"] = [
        d
        for d in bundle["decision_explanations"]["decisions"]
        if not (
            d.get("rule_id") == "classification.derive_legal_effect"
            and d.get("subject_id") == roles["E2"]
        )
    ]
    with pytest.raises(
        AssertionError,
        match=r"classification explanation for E2",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_classification_marked_llm(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "classification.derive_legal_effect"
            and d.get("subject_id") == roles["E2"]
        ):
            d["method"] = "llm"
    with pytest.raises(
        AssertionError,
        match=r"incorrectly marked method=llm|deterministic classification method",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_e1_missing_exception_inference_explanation(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    rel = next(
        r
        for r in bundle["legal_rule_relationships"]["relationships"]
        if r.get("source_id") == roles["E1"] and r.get("relationship_type") == "exception_to"
    )
    rel_id = rel["id"]
    bundle["decision_explanations"]["decisions"] = [
        d
        for d in bundle["decision_explanations"]["decisions"]
        if not (
            d.get("rule_id") == "relationship.infer_exception_to"
            and d.get("subject_id") == rel_id
        )
    ]
    with pytest.raises(
        AssertionError,
        match=r"infer_exception_to explanation for E1",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_exception_explanation_targets_article_14(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    rel = next(
        r
        for r in bundle["legal_rule_relationships"]["relationships"]
        if r.get("source_id") == roles["E3"] and r.get("relationship_type") == "exception_to"
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "relationship.infer_exception_to"
            and d.get("subject_id") == rel["id"]
        ):
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "canonical_target_locator":
                    e["value"] = "article:14"
    with pytest.raises(
        AssertionError,
        match=r"Article 14|canonical target",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_exception_canonical_disagrees_with_relationship(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    rel = next(
        r
        for r in bundle["legal_rule_relationships"]["relationships"]
        if r.get("source_id") == roles["E2"] and r.get("relationship_type") == "exception_to"
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "relationship.infer_exception_to"
            and d.get("subject_id") == rel["id"]
        ):
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "canonical_target_locator":
                    e["value"] = "article:49a:paragraph:99"
    with pytest.raises(
        AssertionError,
        match=r"canonical target.*article:49a:paragraph:1",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_e2_targets_proposition_not_group(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    rel = next(
        r
        for r in bundle["legal_rule_relationships"]["relationships"]
        if r.get("source_id") == roles["E2"] and r.get("relationship_type") == "exception_to"
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "relationship.prefer_group_target"
            and d.get("subject_id") == rel["id"]
        ):
            d["outcome"] = "targeted_unique_proposition"
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "target_kind":
                    e["value"] = "proposition"
                if isinstance(e, dict) and e.get("kind") == "target_id":
                    e["value"] = roles["P1"]
    with pytest.raises(
        AssertionError,
        match=r"targeted_legal_rule_group|group target",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_p3_says_exception_to(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    rel = next(
        r
        for r in bundle["legal_rule_relationships"]["relationships"]
        if r.get("source_id") == roles["P3"] and r.get("relationship_type") == "triggered_by"
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("subject_id") == rel["id"] and d.get("rule_id") == "relationship.infer_triggered_by":
            d["rule_id"] = "relationship.infer_exception_to"
            d["outcome"] = "inferred_exception_to"
    with pytest.raises(
        AssertionError,
        match=r"infer_triggered_by explanation for P3",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_group_target_omits_members(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    rel = next(
        r
        for r in bundle["legal_rule_relationships"]["relationships"]
        if r.get("source_id") == roles["E1"] and r.get("relationship_type") == "exception_to"
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "relationship.prefer_group_target"
            and d.get("subject_id") == rel["id"]
        ):
            d["evidence"] = [
                e
                for e in (d.get("evidence") or [])
                if not (
                    isinstance(e, dict)
                    and e.get("kind") == "group_member_proposition_id"
                )
            ]
    with pytest.raises(
        AssertionError,
        match=r"group members",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_diagnostic_claims_successful_relationship(baseline: dict) -> None:
    bundle = _bundle(baseline)
    # Inject a diagnostic explanation that falsely claims success.
    bundle["decision_explanations"]["decisions"].append(
        {
            "id": "decision:fakeunresolved000000000000001",
            "stage": "relationship",
            "decision_type": "diagnose",
            "subject_kind": "legal_rule_relationship",
            "subject_id": "relcand:fake",
            "outcome": "inferred_exception_to",
            "method": "deterministic",
            "rule_id": "relationship.inference_unresolved",
            "rule_version": "1",
            "summary": "Incorrectly claims a relationship.",
            "inputs": [],
            "evidence": [
                {"kind": "inference_succeeded", "label": "Relationship claimed", "value": "true"}
            ],
            "diagnostics": [],
            "metadata": {"relationship_claimed": True},
        }
    )
    # Acceptance does not scan every unresolved row on the happy path; assert via
    # unit-level invariant that unresolved metadata must not claim success.
    from law_proposition_extractor_pipeline.heuristics.relationship_explanations import (
        build_relationship_decision_explanations,
    )

    expl = build_relationship_decision_explanations(
        [
            {
                "fact_kind": "inference_unresolved",
                "candidate_id": "relcand:fake2",
                "source_proposition_id": "prop:x",
                "relationship_type": "exception_to",
                "cue_text": "x",
                "reference_text": "y",
                "diagnostic_code": "typed_relationship_target_ambiguous",
            }
        ]
    )[0]
    assert expl.metadata.get("relationship_claimed") is False
    assert expl.outcome != "inferred_exception_to"


def test_mutation_paragraph1_group_explanation_missing_p2(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    g1 = next(
        g
        for g in bundle["legal_rule_groups"]["groups"]
        if g.get("canonical_locator") == "article:49a:paragraph:1"
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "grouping.create_shared_fragment_rule_group"
            and d.get("subject_id") == g1["id"]
        ):
            meta = d.setdefault("metadata", {})
            meta["member_proposition_ids"] = [roles["P1"]]
            d["evidence"] = [
                e
                for e in (d.get("evidence") or [])
                if not (
                    isinstance(e, dict)
                    and e.get("kind") == "member_proposition_id"
                    and e.get("value") == roles["P2"]
                )
            ]
    with pytest.raises(
        AssertionError,
        match=r"group members|member order|P1,P2|paragraph-1",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_paragraph2_group_explanation_duplicate_member(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    g2 = next(
        g
        for g in bundle["legal_rule_groups"]["groups"]
        if g.get("canonical_locator") == "article:49a:paragraph:2"
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "grouping.create_shared_fragment_rule_group"
            and d.get("subject_id") == g2["id"]
        ):
            meta = d.setdefault("metadata", {})
            members = list(meta.get("member_proposition_ids") or [])
            members.append(roles["E1"])
            meta["member_proposition_ids"] = members
    with pytest.raises(
        AssertionError,
        match=r"paragraph-2|member order|E1,E2,E3",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_p1_missing_e2_applicable_exception_explanation(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["P1"] in (s.get("source_proposition_ids") or [])
    )
    bundle["decision_explanations"]["decisions"] = [
        d
        for d in bundle["decision_explanations"]["decisions"]
        if not (
            d.get("rule_id") == "effective_law.attach_applicable_exception"
            and d.get("subject_id") == stmt["id"]
            and any(
                isinstance(e, dict)
                and e.get("kind") == "context_proposition_id"
                and e.get("value") == roles["E2"]
                for e in (d.get("evidence") or [])
            )
        )
    ]
    with pytest.raises(
        AssertionError,
        match=r"applicable_exception|exactly 6|P1 ← E2|P1.*E2",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_e2_missing_p1_exception_target_explanation(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["E2"] in (s.get("source_proposition_ids") or [])
    )
    bundle["decision_explanations"]["decisions"] = [
        d
        for d in bundle["decision_explanations"]["decisions"]
        if not (
            d.get("rule_id") == "effective_law.attach_exception_target"
            and d.get("subject_id") == stmt["id"]
            and any(
                isinstance(e, dict)
                and e.get("kind") == "context_proposition_id"
                and e.get("value") == roles["P1"]
                for e in (d.get("evidence") or [])
            )
        )
    ]
    with pytest.raises(
        AssertionError,
        match=r"exception_target|exactly 6|E2 ← P1|E2.*P1",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_p3_missing_e3_trigger_condition_explanation(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["P3"] in (s.get("source_proposition_ids") or [])
    )
    bundle["decision_explanations"]["decisions"] = [
        d
        for d in bundle["decision_explanations"]["decisions"]
        if not (
            d.get("rule_id") == "effective_law.attach_trigger_condition"
            and d.get("subject_id") == stmt["id"]
            and any(
                isinstance(e, dict)
                and e.get("kind") == "context_proposition_id"
                and e.get("value") == roles["E3"]
                for e in (d.get("evidence") or [])
            )
        )
    ]
    with pytest.raises(
        AssertionError,
        match=r"trigger_condition|exactly 3|P3 ← E3|P3.*E3",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_trigger_explanation_marked_bidirectional(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["P3"] in (s.get("source_proposition_ids") or [])
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "effective_law.attach_trigger_condition"
            and d.get("subject_id") == stmt["id"]
        ):
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "expansion_direction":
                    e["value"] = "bidirectional"
            meta = d.setdefault("metadata", {})
            meta["expansion_direction"] = "bidirectional"
    with pytest.raises(
        AssertionError,
        match=r"expansion_direction=source_only",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_context_explanation_wrong_relationship(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    e1_rel = next(
        r
        for r in bundle["legal_rule_relationships"]["relationships"]
        if r.get("source_id") == roles["E1"] and r.get("relationship_type") == "exception_to"
    )
    e2_rel = next(
        r
        for r in bundle["legal_rule_relationships"]["relationships"]
        if r.get("source_id") == roles["E2"] and r.get("relationship_type") == "exception_to"
    )
    stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["P1"] in (s.get("source_proposition_ids") or [])
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "effective_law.attach_applicable_exception"
            and d.get("subject_id") == stmt["id"]
            and any(
                isinstance(e, dict)
                and e.get("kind") == "context_proposition_id"
                and e.get("value") == roles["E1"]
                for e in (d.get("evidence") or [])
            )
        ):
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "legal_rule_relationship_id":
                    e["value"] = e2_rel["id"]
                    e["id"] = e2_rel["id"]
            meta = d.setdefault("metadata", {})
            meta["legal_rule_relationship_id"] = e2_rel["id"]
            assert e1_rel["id"] != e2_rel["id"]
    with pytest.raises(
        AssertionError,
        match=r"wrong relationship|exactly one.*P1 ← E1",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_context_claims_direct_instead_of_group_inheritance(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["P2"] in (s.get("source_proposition_ids") or [])
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "effective_law.attach_applicable_exception"
            and d.get("subject_id") == stmt["id"]
        ):
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "inherited_via_group":
                    e["value"] = "false"
            meta = d.setdefault("metadata", {})
            meta["inherited_via_group"] = False
    with pytest.raises(
        AssertionError,
        match=r"inherited_via_group=true",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_article_14_incorrectly_suppressed(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["E3"] in (s.get("source_proposition_ids") or [])
    )
    bundle["decision_explanations"]["decisions"].append(
        {
            "id": "decision:fakearticle14suppress00000001",
            "stage": "effective_law",
            "decision_type": "suppress",
            "subject_kind": "effective_law_statement",
            "subject_id": stmt["id"],
            "outcome": "generic_locator_context_suppressed",
            "method": "deterministic",
            "rule_id": "effective_law.prefer_typed_context_over_generic_locator",
            "rule_version": "1",
            "summary": "Incorrectly suppresses Article 14.",
            "inputs": [],
            "evidence": [
                {
                    "kind": "generic_locator",
                    "label": "Generic locator candidate",
                    "value": "article 14",
                },
                {
                    "kind": "typed_relationship_id",
                    "label": "Typed relationship",
                    "value": "legalrel:fake",
                },
            ],
            "diagnostics": [],
            "metadata": {
                "generic_locator": "article 14",
                "receiving_proposition_id": roles["E3"],
            },
        }
    )
    with pytest.raises(
        AssertionError,
        match=r"Article 14 incorrectly suppressed|must not have a typed-context suppression",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_generic_paragraph1_retained_alongside_typed(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    for stmt in bundle["effective_law_statements"]["statements"]:
        if roles["E1"] not in (stmt.get("source_proposition_ids") or []):
            continue
        stmt.setdefault("required_context", []).append(
            {
                "kind": "referenced_locator",
                "locator": "paragraph 1",
                "resolution_status": "resolved",
                "proposition_ids": [roles["P1"], roles["P2"]],
            }
        )
    with pytest.raises(
        AssertionError,
        match=r"Generic paragraph-1 locator context retained",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_context_explanation_wrong_statement(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    p1_stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["P1"] in (s.get("source_proposition_ids") or [])
    )
    p2_stmt = next(
        s
        for s in bundle["effective_law_statements"]["statements"]
        if roles["P2"] in (s.get("source_proposition_ids") or [])
    )
    for d in bundle["decision_explanations"]["decisions"]:
        if (
            d.get("rule_id") == "effective_law.attach_applicable_exception"
            and d.get("subject_id") == p1_stmt["id"]
            and any(
                isinstance(e, dict)
                and e.get("kind") == "context_proposition_id"
                and e.get("value") == roles["E2"]
                for e in (d.get("evidence") or [])
            )
        ):
            d["subject_id"] = p2_stmt["id"]
            for e in d.get("evidence") or []:
                if isinstance(e, dict) and e.get("kind") == "effective_law_statement_id":
                    e["value"] = p2_stmt["id"]
                    e["id"] = p2_stmt["id"]
            meta = d.setdefault("metadata", {})
            meta["effective_law_statement_id"] = p2_stmt["id"]
    with pytest.raises(
        AssertionError,
        match=r"exactly one.*P1 ← E2|wrong",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_grouping_explanation_for_paragraph_3(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    bundle["decision_explanations"]["decisions"].append(
        {
            "id": "decision:fakep3group000000000000000001",
            "stage": "grouping",
            "decision_type": "group",
            "subject_kind": "legal_rule_group",
            "subject_id": "rulegrp:fakep3",
            "outcome": "group_created",
            "method": "deterministic",
            "rule_id": "grouping.create_shared_fragment_rule_group",
            "rule_version": "1",
            "summary": "Incorrectly groups paragraph 3.",
            "inputs": [],
            "evidence": [
                {
                    "kind": "canonical_locator",
                    "label": "Source locator",
                    "value": "article:49a:paragraph:3",
                },
                {
                    "kind": "member_proposition_id",
                    "label": "Group member",
                    "value": roles["P3"],
                    "id": roles["P3"],
                },
            ],
            "diagnostics": [],
            "metadata": {
                "canonical_locator": "article:49a:paragraph:3",
                "member_proposition_ids": [roles["P3"]],
            },
        }
    )
    with pytest.raises(
        AssertionError,
        match=r"paragraph-3 group-construction explanation",
    ):
        assert_article_49a_legal_structure(bundle)


def test_identify_roles_stable_without_live_ids(baseline: dict) -> None:
    roles = identify_article_49a_propositions(baseline["bundle"])
    assert roles == baseline["roles"]


def test_mutation_manifestation_claims_as_of_equals_retrieval(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") != "provenance.classify_manifestation":
            continue
        for e in d.get("evidence") or []:
            if isinstance(e, dict) and e.get("kind") == "resolved_as_of_date":
                e["value"] = "2026-07-14T21:22:45.133803Z"
        d["summary"] = (
            "Legal as-of equals retrieval date because the snapshot was revised."
        )
    with pytest.raises(
        AssertionError,
        match=r"resolved as-of not recorded|as-of equals retrieval|legal as-of",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_manifestation_claims_applied_all_amendments(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") == "provenance.classify_manifestation":
            d["summary"] = "Law Proposition Extractor applied all amendments up to the source revision date."
    with pytest.raises(
        AssertionError,
        match=r"must not claim Law Proposition Extractor applied all amendments",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_article_level_effect_missing_from_paragraph_2(baseline: dict) -> None:
    bundle = _bundle(baseline)
    effects = bundle["source_legal_effects"]["effects"]
    art = next(e for e in effects if e.get("annotation_id") == "c000004")
    art_id = art["id"]
    bundle["decision_explanations"]["decisions"] = [
        d
        for d in bundle["decision_explanations"]["decisions"]
        if not (
            d.get("rule_id") == "source_effect.inherit_from_structural_ancestor"
            and (d.get("metadata") or {}).get("effect_id") == art_id
        )
    ]
    with pytest.raises(
        AssertionError,
        match=r"Article-level effect inherited on paragraph",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_paragraph1_effect_leaks_to_paragraph2(baseline: dict) -> None:
    bundle = _bundle(baseline)
    effects = bundle["source_legal_effects"]["effects"]
    para1 = next(
        e
        for e in effects
        if e.get("annotation_id") == "key-ae688d7efb8d525f494201f970bc3e75"
    )
    # Find a paragraph-2 statement id from an existing inherit decision.
    p2_stmt = None
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") != "source_effect.inherit_from_structural_ancestor":
            continue
        if (d.get("metadata") or {}).get("descendant_locator", "").startswith(
            "article:49a:paragraph:2"
        ) or "paragraph:2" in json.dumps(d):
            p2_stmt = d.get("subject_id")
            break
    if not p2_stmt:
        stmts = bundle["effective_law_statements"]["statements"]
        p2_stmt = stmts[0]["id"]
    bundle["decision_explanations"]["decisions"].append(
        {
            "id": "decision:fakeleakpara1to2aaaaaaaaaaaa",
            "stage": "source_effect",
            "decision_type": "link",
            "subject_kind": "effective_law_statement",
            "subject_id": p2_stmt,
            "outcome": "source_effect_relevant",
            "method": "deterministic",
            "rule_id": "source_effect.link_exact_fragment",
            "rule_version": "1",
            "summary": "Leaked paragraph-1 effect onto paragraph 2.",
            "inputs": [],
            "evidence": [{"kind": "effect_id", "value": para1["id"], "id": para1["id"]}],
            "diagnostics": [],
            "metadata": {
                "effect_id": para1["id"],
                "relevance_basis": "exact_fragment",
            },
        }
    )
    with pytest.raises(AssertionError, match=r"leaked to sibling"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_article1_effect_leaks_into_49a(baseline: dict) -> None:
    bundle = _bundle(baseline)
    effects = bundle["source_legal_effects"]["effects"]
    art1 = next(e for e in effects if e.get("annotation_id") == "c000001")
    stmt_id = None
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") == "source_effect.inherit_from_structural_ancestor":
            stmt_id = d.get("subject_id")
            break
    assert stmt_id
    # Remove exclusions and add a false relevant decision.
    bundle["decision_explanations"]["decisions"] = [
        d
        for d in bundle["decision_explanations"]["decisions"]
        if d.get("rule_id") != "source_effect.exclude_unrelated_fragment"
    ]
    bundle["decision_explanations"]["decisions"].append(
        {
            "id": "decision:fakeart1leak49aaaaaaaaaaaaaaa",
            "stage": "source_effect",
            "decision_type": "inherit",
            "subject_kind": "effective_law_statement",
            "subject_id": stmt_id,
            "outcome": "source_effect_relevant",
            "method": "deterministic",
            "rule_id": "source_effect.inherit_from_structural_ancestor",
            "rule_version": "1",
            "summary": "Article 1 incorrectly inherited onto Article 49a.",
            "inputs": [],
            "evidence": [{"kind": "effect_id", "value": art1["id"], "id": art1["id"]}],
            "diagnostics": [],
            "metadata": {
                "effect_id": art1["id"],
                "relevance_basis": "structural_ancestor",
            },
        }
    )
    with pytest.raises(
        AssertionError,
        match=r"Article 1 effect must not appear as relevant",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_exact_marked_inherited(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") != "source_effect.link_exact_fragment":
            continue
        d["rule_id"] = "source_effect.inherit_from_structural_ancestor"
        d["decision_type"] = "inherit"
        meta = d.setdefault("metadata", {})
        meta["relevance_basis"] = "structural_ancestor"
    with pytest.raises(
        AssertionError,
        match=r"exact-fragment effect on paragraph",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_inherited_missing_ancestor_path(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") != "source_effect.inherit_from_structural_ancestor":
            continue
        meta = d.setdefault("metadata", {})
        meta.pop("ancestor_locator", None)
        d["evidence"] = [
            e
            for e in (d.get("evidence") or [])
            if not (
                isinstance(e, dict)
                and e.get("kind")
                in {"ancestor_locator", "validated_parent_path", "ancestor_fragment_id"}
            )
        ]
    with pytest.raises(AssertionError, match=r"missing ancestor path"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_outstanding_unknown_as_none(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") == "source_effect.classify_outstanding_status":
            d["outcome"] = "source_reports_none"
            meta = d.setdefault("metadata", {})
            meta["outstanding_effects_status"] = "source_reports_none"
    with pytest.raises(AssertionError, match=r"displayed as none|outstanding"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_not_matched_as_nonexistent(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") == "source_effect.assess_independent_consumption":
            d["summary"] = "The affecting instrument does not exist."
    with pytest.raises(
        AssertionError,
        match=r"instrument nonexistent|does not exist",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_consumed_claims_verified(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for d in bundle["decision_explanations"]["decisions"]:
        if d.get("rule_id") != "source_effect.assess_independent_consumption":
            continue
        d["outcome"] = "consumed_in_current_run"
        d["summary"] = (
            "Independently consumed and Law Proposition Extractor verified the amendment was correctly applied."
        )
        meta = d.setdefault("metadata", {})
        meta["independent_consumption_status"] = "consumed_in_current_run"
        # Keep subject aligned with an effect that acceptance checks.
        break
    # Also flip the effect status so outcome mismatch isn't the first failure.
    for e in bundle["source_legal_effects"]["effects"]:
        if e.get("annotation_id") in {
            "c000004",
            "key-ae688d7efb8d525f494201f970bc3e75",
            "key-cd016a627475b52260f225a4d4ac7ed7",
            "key-c36fcfcb069fb8c51fce93fbce7ea03b",
        }:
            e["independent_consumption_status"] = "consumed_in_current_run"
    with pytest.raises(
        AssertionError,
        match=r"consumed_in_current_run|must not claim amendment verified",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_duplicate_relevance_decision(baseline: dict) -> None:
    bundle = _bundle(baseline)
    sample = next(
        d
        for d in bundle["decision_explanations"]["decisions"]
        if d.get("rule_id") == "source_effect.link_exact_fragment"
    )
    dup = json.loads(json.dumps(sample))
    dup["id"] = "decision:fakeduplicaterelevance00000001"
    bundle["decision_explanations"]["decisions"].append(dup)
    with pytest.raises(AssertionError, match=r"Duplicated source-effect relevance"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_heading_discarded_from_article_49a(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for frag in bundle["source_fragments"]:
        if frag.get("locator") == "article:49a":
            frag.pop("structural_heading", None)
    with pytest.raises(AssertionError, match=r"legislative heading|structural_heading was discarded"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_heading_copied_into_paragraph_operative_text(baseline: dict) -> None:
    bundle = _bundle(baseline)
    heading = (
        "Separate stowage of catches below the minimum conservation reference sizes"
    )
    for frag in bundle["source_fragments"]:
        if frag.get("locator") == "article:49a":
            frag["fragment_text"] = f"{heading}. {frag.get('fragment_text')}"
    with pytest.raises(AssertionError, match=r"copied into operative fragment_text"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_heading_emitted_as_seventh_proposition(baseline: dict) -> None:
    bundle = _bundle(baseline)
    roles = baseline["roles"]
    donor = next(p for p in bundle["propositions"] if p["id"] == roles["P1"])
    extra = copy.deepcopy(donor)
    extra["id"] = "prop:headingasproposition00"
    extra["proposition_text"] = (
        "Separate stowage of catches below the minimum conservation reference sizes"
    )
    extra["fragment_locator"] = "article:49a"
    bundle["propositions"].append(extra)
    with pytest.raises(AssertionError, match=r"Expected 6 Article 49a propositions"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_article_1_heading_inherited_by_49a(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for frag in bundle["source_fragments"]:
        if frag.get("locator") == "article:49a:paragraph:3":
            # Force inheritance check to see Article 1 heading on the path by
            # planting it as a direct heading on the paragraph (leak signal).
            frag["structural_heading"] = {
                "kind": "article",
                "text": "Subject matter",
                "owner_locator": "article:1",
            }
    with pytest.raises(AssertionError, match=r"Article 1/14 heading incorrectly inherited"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_title_iv_number_replaced_by_descriptive_title(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for frag in bundle["source_fragments"]:
        if frag.get("locator") == "title:iv":
            frag["fragment_text"] = "CONTROL OF FISHERIES"
            frag["number_label"] = "CONTROL OF FISHERIES"
    with pytest.raises(
        AssertionError,
        match=r"number_label = 'TITLE IV'|replaced by its descriptive title",
    ):
        assert_article_49a_legal_structure(bundle)


def test_mutation_heading_missing_from_extraction_job(baseline: dict) -> None:
    bundle = _bundle(baseline)
    for job in bundle["proposition_extraction_jobs"]:
        if job.get("fragment_locator") == "article:49a:paragraph:3":
            job.pop("structural_heading_contexts", None)
    with pytest.raises(AssertionError, match=r"structural heading context|field missing"):
        assert_article_49a_legal_structure(bundle)


def test_mutation_old_bundle_without_heading_fields_loads(baseline: dict) -> None:
    """Absent heading fields must remain parseable (compat); acceptance may still fail."""
    from law_proposition_extractor_domain import SourceFragment

    bundle = _bundle(baseline)
    for frag in bundle["source_fragments"]:
        frag.pop("structural_heading", None)
        frag.pop("number_label", None)
    # Round-trip must not crash.
    for frag in bundle["source_fragments"]:
        SourceFragment.model_validate(frag)
    with pytest.raises(AssertionError, match=r"structural_heading was discarded"):
        assert_article_49a_legal_structure(bundle)
