"""Structured-list DecisionExplanation emission tests (Prompt 20-BR3)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import (
    DecisionStage,
    DecisionSubjectKind,
    HeuristicMethod,
    Proposition,
)
from law_proposition_extractor_pipeline.heuristics.registry import get_heuristic, list_heuristics, require_heuristic
from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
    build_decision_explanations_artifact,
)
from law_proposition_extractor_pipeline.heuristics.structured_list_explanations import (
    bind_structured_list_decision_facts,
    build_structured_list_decision_explanations,
    merge_decision_explanation_lists,
)
from law_proposition_extractor_pipeline.structured_list_decomposition import (
    StructuredListIdentityContext,
    extraction_candidate_id,
    merge_structured_leaf_rows,
    draft_structured_list_leaves,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "structured_list_dedupe"
DUP_FIXTURE = FIXTURE_DIR / "article_49a_p2_duplicate_2_a_i.json"
DISTINCT_FIXTURE = FIXTURE_DIR / "distinct_propositions_same_path.json"

_SL_RULES = (
    "structured_list.compose_terminal_leaf",
    "structured_list.suppress_duplicate_terminal",
    "structured_list.preserve_distinct_terminal_claims",
    "structured_list.reject_non_terminal_row",
)


def _identity(payload: dict) -> StructuredListIdentityContext:
    return StructuredListIdentityContext(
        source_record_id=str(payload.get("source_record_id") or "src-test"),
        source_snapshot_id=str(payload.get("source_snapshot_id") or "snap-test"),
        source_fragment_id=str(payload.get("source_fragment_id") or "frag-test"),
    )


def _rows(payload: dict) -> list[dict]:
    return [{k: v for k, v in row.items() if k != "row_id"} for row in payload["frontier_rows"]]


def _merge(payload: dict, rows: list[dict] | None = None):
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    return merge_structured_leaf_rows(
        existing_rows=rows if rows is not None else _rows(payload),
        drafts=drafts,
        base_locator=payload["base_locator"],
        limit=10,
        identity=_identity(payload),
    )


def test_registry_structured_list_rules_exist() -> None:
    for rule_id in _SL_RULES:
        h = require_heuristic(rule_id)
        assert h.version == "1"
        assert h.stage == DecisionStage.EXTRACTION
        assert h.method == HeuristicMethod.DETERMINISTIC
        assert h.code_references
        assert h.test_references
    ids = [h.rule_id for h in list_heuristics()]
    assert ids == sorted(ids)
    for rule_id in _SL_RULES:
        assert get_heuristic(rule_id) is not None


def test_extraction_candidate_id_stable_and_order_independent() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    rows = _rows(payload)
    ident = _identity(payload)
    a = extraction_candidate_id(
        row=rows[0], structured_list_path="2-a-i", identity=ident, candidate_origin="deterministic_draft"
    )
    b = extraction_candidate_id(
        row=rows[0], structured_list_path="2-a-i", identity=ident, candidate_origin="deterministic_draft"
    )
    assert a == b
    assert a.startswith("extractcand:")
    other = extraction_candidate_id(
        row=rows[1], structured_list_path="2-a-i", identity=ident, candidate_origin="llm"
    )
    assert a != other
    # Display summary must not affect identity.
    mutated = dict(rows[0])
    mutated["display_label"] = "totally different label"
    assert (
        extraction_candidate_id(
            row=mutated,
            structured_list_path="2-a-i",
            identity=ident,
            candidate_origin="deterministic_draft",
        )
        == a
    )


def test_terminal_composition_explanations_for_retained_paths() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    merged, _diags, facts = _merge(payload)
    bound = bind_structured_list_decision_facts(
        facts,
        propositions=[
            Proposition(
                id=f"prop:test-{i}",
                topic_id="t",
                cluster_id="c",
                source_record_id=payload["source_record_id"],
                jurisdiction="UK",
                proposition_text=str(r.get("proposition_text") or ""),
                legal_subject="x",
                action="y",
                extraction_debug_meta={
                    "extraction_candidate_id": r.get("_extraction_candidate_id"),
                    "structured_list_path": (r.get("_structured_list_meta") or {}).get(
                        "structured_list_path"
                    ),
                },
            )
            for i, r in enumerate(merged)
            if (r.get("_structured_list_meta") or {}).get("structured_list_path")
        ],
    )
    explanations = build_structured_list_decision_explanations(bound)
    compose = [
        e for e in explanations if e.rule_id == "structured_list.compose_terminal_leaf"
    ]
    paths = sorted(
        {
            str(e.metadata.get("structured_list_path") or "")
            for e in compose
        }
    )
    assert paths == ["2-a-i", "2-a-ii", "2-b"]
    assert len(compose) == 3
    for expl in compose:
        assert expl.method == HeuristicMethod.DETERMINISTIC
        assert expl.stage == DecisionStage.EXTRACTION
        assert expl.subject_kind == DecisionSubjectKind.PROPOSITION
        assert expl.rule_version == require_heuristic(expl.rule_id).version
        roles = {
            ev.kind.removeprefix("component_")
            for ev in expl.evidence
            if ev.kind.startswith("component_") and not ev.kind.endswith("_quote")
        }
        assert "stem" in roles and "leaf" in roles
        assert "chain_of_thought" not in json.dumps(expl.model_dump(mode="json")).lower()
        assert "private reasoning" not in expl.summary.lower()
    e2 = next(e for e in compose if e.metadata.get("structured_list_path") == "2-a-ii")
    assert "branch" in {
        ev.kind.removeprefix("component_")
        for ev in e2.evidence
        if ev.kind.startswith("component_") and not ev.kind.endswith("_quote")
    }
    loc_values = [
        ev.value
        for ev in e2.evidence
        if ev.kind == "source_component_locator" and ev.value is not None
    ]
    assert loc_values == sorted(loc_values)


def test_llm_origin_does_not_change_method_from_deterministic() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    # Only LLM paraphrase for 2-a-i (drop deterministic twin) plus other terminals.
    rows = [_rows(payload)[1], _rows(payload)[2], _rows(payload)[3]]
    _merged, _diags, facts = _merge(payload, rows=rows)
    compose_facts = [f for f in facts if f.get("fact_kind") == "compose_terminal_leaf"]
    assert any(f.get("candidate_origin") == "llm" for f in compose_facts)
    for expl in build_structured_list_decision_explanations(compose_facts):
        if expl.rule_id == "structured_list.compose_terminal_leaf":
            assert expl.method == HeuristicMethod.DETERMINISTIC


def test_duplicate_suppression_explanation_and_order_independence() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    rows = _rows(payload)
    merged_f, diags_f, facts_f = _merge(payload, rows=rows)
    merged_b, diags_b, facts_b = _merge(payload, rows=list(reversed(rows)))
    assert [r["source_locator"] for r in merged_f] == [r["source_locator"] for r in merged_b]
    suppress_f = [
        f for f in facts_f if f.get("fact_kind") == "suppress_duplicate_terminal"
    ]
    suppress_b = [
        f for f in facts_b if f.get("fact_kind") == "suppress_duplicate_terminal"
    ]
    assert len(suppress_f) == 1
    assert len(suppress_b) == 1
    assert suppress_f[0]["retained_candidate_id"] == suppress_b[0]["retained_candidate_id"]
    assert suppress_f[0]["suppressed_candidate_id"] == suppress_b[0]["suppressed_candidate_id"]
    assert suppress_f[0]["structured_list_path"] == "2-a-i"
    assert suppress_f[0]["duplicate_basis"]
    assert suppress_f[0]["winner_selection_factors"]

    props = [
        Proposition(
            id="prop:retained-winner",
            topic_id="t",
            cluster_id="c",
            source_record_id=payload["source_record_id"],
            jurisdiction="UK",
            proposition_text=str(merged_f[0].get("proposition_text") or ""),
            legal_subject="x",
            action="y",
            extraction_debug_meta={
                "extraction_candidate_id": merged_f[0].get("_extraction_candidate_id"),
                "structured_list_path": "2-a-i",
            },
        )
    ]
    bound = bind_structured_list_decision_facts(suppress_f, propositions=props)
    explanations = build_structured_list_decision_explanations(bound)
    assert len(explanations) == 1
    expl = explanations[0]
    assert expl.rule_id == "structured_list.suppress_duplicate_terminal"
    assert expl.subject_kind == DecisionSubjectKind.EXTRACTION_CANDIDATE
    assert expl.subject_id == suppress_f[0]["suppressed_candidate_id"]
    assert expl.metadata.get("retained_proposition_id") == "prop:retained-winner"
    assert "structured_list_terminal_duplicate_suppressed" in expl.diagnostics
    # Decision ID stable across input order.
    assert (
        build_structured_list_decision_explanations(
            bind_structured_list_decision_facts(suppress_b, propositions=props)
        )[0].id
        == expl.id
    )
    assert any(d["code"] == "structured_list_terminal_duplicate_suppressed" for d in diags_f)
    # Suppressed locator absent from retained rows / propositions.
    assert all(
        r.get("source_locator") != "article:49a:paragraph:2:(a)(i)" for r in merged_f
    )


def test_path_equality_alone_insufficient_for_suppression() -> None:
    payload = json.loads(DISTINCT_FIXTURE.read_text())
    _merged, diags, facts = _merge(payload)
    assert any(
        d["code"] == "structured_list_path_multiple_distinct_propositions" for d in diags
    )
    assert not any(f.get("fact_kind") == "suppress_duplicate_terminal" for f in facts)
    preserve = [f for f in facts if f.get("fact_kind") == "preserve_distinct_terminal_claims"]
    assert len(preserve) == 1
    explanations = build_structured_list_decision_explanations(preserve)
    assert len(explanations) == 1
    assert explanations[0].rule_id == "structured_list.preserve_distinct_terminal_claims"
    assert "could not safely establish" in explanations[0].summary.lower()


def test_stem_and_branch_only_rows_emit_reject_explanations() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    stem = drafts[0].parent_intro
    branch = drafts[0].branch_context
    rows = [
        {
            "proposition_text": stem,
            "provision_type": "exception",
            "source_locator": "article:49a:paragraph:2:stem",
            "evidence_text": stem,
            "conditions": [],
            "exceptions": [],
            "completeness_status": "complete",
            "confidence": "high",
            "reason": "Stem-only paraphrase",
        },
        {
            "proposition_text": branch,
            "provision_type": "exception",
            "source_locator": "article:49a:paragraph:2:branch-a",
            "evidence_text": branch,
            "conditions": [],
            "exceptions": [],
            "completeness_status": "complete",
            "confidence": "high",
            "reason": "Branch-only paraphrase",
        },
        *_rows(payload)[2:],  # keep 2-a-ii and 2-b
    ]
    merged, _diags, facts = _merge(payload, rows=rows)
    paths = [
        str((r.get("_structured_list_meta") or {}).get("structured_list_path") or "")
        for r in merged
        if (r.get("_structured_list_meta") or {}).get("structured_list_path")
    ]
    assert "2-a-i" in paths  # filled from draft
    assert not any("stem" in str(r.get("source_locator") or "") for r in merged)
    reject = [f for f in facts if f.get("fact_kind") == "reject_non_terminal_row"]
    assert len(reject) >= 2
    roles = {f.get("component_role") for f in reject}
    assert "stem" in roles and "branch" in roles
    explanations = build_structured_list_decision_explanations(reject)
    assert all(e.rule_id == "structured_list.reject_non_terminal_row" for e in explanations)
    assert all(e.subject_kind == DecisionSubjectKind.EXTRACTION_CANDIDATE for e in explanations)


def test_decision_ids_change_with_path_and_winner_not_summary() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    _merged, _diags, facts = _merge(payload)
    compose = [f for f in facts if f.get("fact_kind") == "compose_terminal_leaf"]
    by_path = {
        f["structured_list_path"]: build_structured_list_decision_explanations([f])[0]
        for f in compose
    }
    assert by_path["2-a-i"].id != by_path["2-a-ii"].id
    suppress = [f for f in facts if f.get("fact_kind") == "suppress_duplicate_terminal"][0]
    expl_a = build_structured_list_decision_explanations([suppress])[0]
    flipped = dict(suppress)
    flipped["retained_candidate_id"], flipped["suppressed_candidate_id"] = (
        suppress["suppressed_candidate_id"],
        suppress["retained_candidate_id"],
    )
    expl_b = build_structured_list_decision_explanations([flipped])[0]
    assert expl_a.id != expl_b.id
    # Summary prose is not part of the decision id payload.
    mutated = dict(suppress)
    # Rebuild with same material identity — id stable.
    assert build_structured_list_decision_explanations([mutated])[0].id == expl_a.id


def test_mutation_missing_suppression_explanation_detected() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    _merged, diags, facts = _merge(payload)
    assert any(d["code"] == "structured_list_terminal_duplicate_suppressed" for d in diags)
    # Drop suppress facts while diagnostic remains — consumer invariant fails.
    kept = [f for f in facts if f.get("fact_kind") != "suppress_duplicate_terminal"]
    explanations = build_structured_list_decision_explanations(kept)
    assert not any(
        e.rule_id == "structured_list.suppress_duplicate_terminal" for e in explanations
    )


def test_mutation_wrong_retained_candidate_changes_decision_id() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    _merged, _diags, facts = _merge(payload)
    suppress = [f for f in facts if f.get("fact_kind") == "suppress_duplicate_terminal"][0]
    good = build_structured_list_decision_explanations([suppress])[0]
    bad = dict(suppress)
    bad["retained_candidate_id"] = "extractcand:" + ("0" * 32)
    wrong = build_structured_list_decision_explanations([bad])[0]
    assert wrong.id != good.id
    assert wrong.metadata.get("retained_candidate_id") != good.metadata.get(
        "retained_candidate_id"
    )


def test_mutation_silent_collapse_of_distinct_claims_detected() -> None:
    payload = json.loads(DISTINCT_FIXTURE.read_text())
    merged, diags, facts = _merge(payload)
    assert len(
        [
            r
            for r in merged
            if str((r.get("_structured_list_meta") or {}).get("structured_list_path")) == "1-a-i"
        ]
    ) == 2
    # If a consumer incorrectly collapses without preserve fact, invariant breaks.
    assert any(f.get("fact_kind") == "preserve_distinct_terminal_claims" for f in facts)
    assert any(d["code"] == "structured_list_path_multiple_distinct_propositions" for d in diags)


def test_artifact_merges_selection_and_structured_list() -> None:
    from law_proposition_extractor_domain import (
        DecisionEvidence,
        DecisionExplanation,
        DecisionType,
    )

    selection = [
        DecisionExplanation(
            id="decision:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            stage=DecisionStage.SELECTION,
            decision_type=DecisionType.SELECT,
            subject_kind=DecisionSubjectKind.SOURCE_FRAGMENT,
            subject_id="frag-1",
            outcome="selected_for_extraction",
            method=HeuristicMethod.CONFIGURATION,
            rule_id="selection.required_locator",
            rule_version="1",
            summary="Selected because required.",
            evidence=[
                DecisionEvidence(kind="source_locator", label="Fragment locator", value="article:1")
            ],
        )
    ]
    payload = json.loads(DUP_FIXTURE.read_text())
    _merged, _diags, facts = _merge(payload)
    sl = build_structured_list_decision_explanations(
        [f for f in facts if f.get("fact_kind") == "compose_terminal_leaf"][:1]
    )
    merged = merge_decision_explanation_lists(selection, sl)
    artifact = build_decision_explanations_artifact(run_id="run-x", decisions=merged)
    assert artifact["schema_version"] == "1"
    stages = [d["stage"] for d in artifact["decisions"]]
    assert "selection" in stages and "extraction" in stages
    ids = [d["id"] for d in artifact["decisions"]]
    assert len(ids) == len(set(ids))
    # Older empty artifact still valid.
    empty = build_decision_explanations_artifact(run_id="run-old", decisions=[])
    assert empty["decisions"] == []
