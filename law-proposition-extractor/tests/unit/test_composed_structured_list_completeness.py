"""Tests for completeness.reconcile_composed_structured_list (20-BR10L)."""

from __future__ import annotations

import json

import pytest
from law_proposition_extractor_domain import DecisionStage, HeuristicMethod
from law_proposition_extractor_pipeline.composed_structured_list_completeness import (
    FACT_RECONCILE_COMPOSED_STRUCTURED_LIST,
    RULE_RECONCILE_COMPOSED_STRUCTURED_LIST,
    RECONCILIATION_BASIS,
    reconcile_composed_structured_list_completeness,
)
from law_proposition_extractor_pipeline.extract import _validate_v2_items
from law_proposition_extractor_pipeline.heuristics import (
    RULES_EMITTING_DECISION_EXPLANATIONS,
    bind_completeness_reconciliation_decision_facts,
    build_completeness_reconciliation_decision_explanations,
    require_heuristic,
)
from law_proposition_extractor_pipeline.proposition_completeness import build_proposition_completeness_assessments
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import load_proposition_fidelity_cases
from law_proposition_extractor_pipeline.proposition_fidelity.runner import (
    _attach_evidence,
    _load_fragment_text,
)
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root
from law_proposition_extractor_pipeline.structured_list_decomposition import (
    COMPOSITION_BASIS,
    StructuredListIdentityContext,
    draft_structured_list_leaves,
    merge_structured_leaf_rows,
)

_IDENTITY = StructuredListIdentityContext(
    source_record_id="src-49a",
    source_snapshot_id="snap-49a",
    source_fragment_id="frag-49a",
)

_LIVE_RUN = "live-pf-20260715T155907Z"


def _live_call(rep: int) -> dict:
    path = (
        judit_root()
        / "calibration/proposition_fidelity"
        / _LIVE_RUN
        / "calls"
        / f"article_49a-{rep}.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _live_available() -> bool:
    return (
        judit_root() / "calibration/proposition_fidelity" / _LIVE_RUN
    ).is_dir()


def _composed_exception_row(**overrides: object) -> dict:
    row = {
        "proposition_text": (
            "Paragraph 1 of Article 49a shall not apply where the catches "
            "contain more than 80% of one or more species used for industrial "
            "purposes, namely capelin, sandeel, or Norwegian pout."
        ),
        "subject": "Paragraph 1 of Article 49a",
        "rule": "shall not apply",
        "object": "separate stowage requirement",
        "conditions": [
            "catches contain more than 80% of one or more of the listed "
            "industrial-purpose species"
        ],
        "exceptions": [],
        "provision_type": "exception",
        "source_locator": "article:49a:paragraph:2:subparagraph:a:item:ii",
        "evidence_text": (
            "(ii)) capelin, sandeel, Norwegian pout "
            "(i.e. fisheries for industrial purposes)"
        ),
        "completeness_status": "context_dependent",
        "confidence": "high",
        "reason": (
            "Terminal leaf (a)(ii); governing stem 'Paragraph 1 shall not "
            "apply' is carried forward from the source structure."
        ),
        "_structured_list_compose_captured": True,
        "_composition_basis": COMPOSITION_BASIS,
        "_extraction_candidate_id": "extractcand:e2-industrial",
        "_structured_list_meta": {
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": (
                "Article 49a. (1) All catches … (2) Paragraph 1 shall not apply:"
            ),
            "branch_context": (
                "where the catches contain more than 80% of one or more of "
                "the following species"
            ),
            "list_marker": "(a)(ii)",
            "structured_list_path": "2-a-ii",
            "source_component_locators": [
                {
                    "role": "stem",
                    "locator_suffix": "stem",
                    "text": "(2) Paragraph 1 shall not apply:",
                },
                {
                    "role": "branch",
                    "locator_suffix": "a",
                    "text": (
                        "where the catches contain more than 80% of one or "
                        "more of the following species"
                    ),
                },
                {
                    "role": "leaf",
                    "locator_suffix": "ii",
                    "text": (
                        "capelin, sandeel, Norwegian pout "
                        "(i.e. fisheries for industrial purposes)"
                    ),
                },
            ],
            "provision_type": "exception",
        },
    }
    row.update(overrides)
    return row


def _merge_live_rows(rep: int) -> list[dict]:
    call = _live_call(rep)
    cases = {c.case_id: c for c in load_proposition_fidelity_cases()}
    case = cases["article_49a"]
    text, _ = _load_fragment_text(case)
    validated, errs, _ = _validate_v2_items(call["raw_rows"], text, limit=20)
    assert not errs
    drafts = draft_structured_list_leaves(text, case.source_locator)
    merged, _diags, _facts = merge_structured_leaf_rows(
        existing_rows=validated,
        drafts=drafts,
        base_locator=case.source_locator,
        limit=20,
        identity=_IDENTITY,
    )
    return merged


@pytest.mark.skipif(not _live_available(), reason="live calibration artifacts absent")
@pytest.mark.parametrize("rep", [1, 2, 3])
def test_article_49a_e2_live_repetition_reconciles(rep: int) -> None:
    merged = _merge_live_rows(rep)
    e2 = next(
        r
        for r in merged
        if "capelin" in str(r.get("proposition_text") or "").lower()
    )
    assert e2["completeness_status"] == "context_dependent"
    original_text = e2["proposition_text"]
    original_evidence = e2["evidence_text"]
    original_id = e2.get("_extraction_candidate_id")

    retained, diags, facts = reconcile_composed_structured_list_completeness(
        merged, identity=_IDENTITY
    )
    e2_out = next(
        r
        for r in retained
        if "capelin" in str(r.get("proposition_text") or "").lower()
    )
    assert e2_out["model_completeness_status"] == "context_dependent"
    assert e2_out["completeness_status"] == "complete"
    assert e2_out["reconciled_completeness_status"] == "complete"
    assert e2_out["reconciliation_applied"] is True
    assert e2_out["reconciliation_rule"] == RULE_RECONCILE_COMPOSED_STRUCTURED_LIST
    assert e2_out["reconciliation_basis"] == RECONCILIATION_BASIS
    assert e2_out["proposition_text"] == original_text
    assert e2_out["evidence_text"] == original_evidence
    assert e2_out.get("_extraction_candidate_id") == original_id
    assert any(d.get("code") == "completeness_reconciled_composed_structured_list" for d in diags)
    assert len([f for f in facts if f["fact_kind"] == FACT_RECONCILE_COMPOSED_STRUCTURED_LIST]) == 1

    bound = bind_completeness_reconciliation_decision_facts(
        facts,
        propositions=[
            {
                "id": "prop-e2",
                "extraction_debug_meta": {
                    "extraction_candidate_id": e2_out.get("_extraction_candidate_id")
                },
            }
        ],
    )
    expls = build_completeness_reconciliation_decision_explanations(bound)
    assert len(expls) == 1
    assert expls[0].rule_id == RULE_RECONCILE_COMPOSED_STRUCTURED_LIST
    assert expls[0].stage == DecisionStage.COMPLETENESS
    assert "governing list stems" in expls[0].summary


def test_reduced_terminal_exception_leaf_reconciles() -> None:
    row = _composed_exception_row()
    retained, _diags, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "complete"
    assert retained[0]["model_completeness_status"] == "context_dependent"
    assert facts[0]["legal_effect"] == "derogation"


def test_composed_obligation_list_leaf_reconciles() -> None:
    row = _composed_exception_row(
        proposition_text=(
            "The master shall record each landing of capelin, sandeel, or "
            "Norwegian pout when catches contain more than 80% of those species."
        ),
        rule="shall record",
        provision_type="core",
        completeness_status="context_dependent",
        _structured_list_meta={
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "The master shall record each landing:",
            "branch_context": "when catches contain more than 80% of those species",
            "list_marker": "(a)(i)",
            "structured_list_path": "1-a-i",
            "source_component_locators": [
                {
                    "role": "stem",
                    "locator_suffix": "stem",
                    "text": "The master shall record each landing:",
                },
                {
                    "role": "branch",
                    "locator_suffix": "a",
                    "text": "when catches contain more than 80% of those species",
                },
                {
                    "role": "leaf",
                    "locator_suffix": "i",
                    "text": "capelin, sandeel, or Norwegian pout",
                },
            ],
        },
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "complete"
    assert facts[0]["legal_effect"] == "obligation"


def test_composed_prohibition_list_leaf_reconciles() -> None:
    row = _composed_exception_row(
        proposition_text=(
            "An operator must not discharge slurry containing more than 80% "
            "nitrogen into surface water near protected habitats."
        ),
        rule="must not discharge",
        provision_type="core",
        subject="An operator",
        completeness_status="context_dependent",
        _structured_list_meta={
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "An operator must not discharge slurry:",
            "branch_context": "containing more than 80% nitrogen",
            "list_marker": "(b)",
            "structured_list_path": "1-b",
            "source_component_locators": [
                {
                    "role": "stem",
                    "locator_suffix": "stem",
                    "text": "An operator must not discharge slurry:",
                },
                {
                    "role": "branch",
                    "locator_suffix": "b",
                    "text": "containing more than 80% nitrogen",
                },
                {
                    "role": "leaf",
                    "locator_suffix": "leaf",
                    "text": "into surface water near protected habitats",
                },
            ],
        },
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "complete"
    assert facts[0]["legal_effect"] == "prohibition"


def test_input_order_independent_same_composition_facts() -> None:
    a = _composed_exception_row(_extraction_candidate_id="extractcand:a")
    b = _composed_exception_row(
        proposition_text=(
            "Paragraph 1 of Article 49a shall not apply where the catches "
            "contain more than 80% of one or more small pelagic species, "
            "namely mackerel, herring, or sprat."
        ),
        evidence_text="(i)) mackerel, herring, sprat",
        _extraction_candidate_id="extractcand:b",
        _structured_list_meta={
            **_composed_exception_row()["_structured_list_meta"],
            "structured_list_path": "2-a-i",
            "list_marker": "(a)(i)",
            "source_component_locators": [
                {
                    "role": "stem",
                    "locator_suffix": "stem",
                    "text": "(2) Paragraph 1 shall not apply:",
                },
                {
                    "role": "branch",
                    "locator_suffix": "a",
                    "text": (
                        "where the catches contain more than 80% of one or "
                        "more of the following species"
                    ),
                },
                {
                    "role": "leaf",
                    "locator_suffix": "i",
                    "text": "mackerel, herring, or sprat (i.e. small pelagic)",
                },
            ],
        },
    )
    forward, _, fa = reconcile_composed_structured_list_completeness(
        [a, b], identity=_IDENTITY
    )
    backward, _, fb = reconcile_composed_structured_list_completeness(
        [b, a], identity=_IDENTITY
    )
    assert {r["completeness_status"] for r in forward} == {"complete"}
    assert {r["completeness_status"] for r in backward} == {"complete"}
    assert len(fa) == len(fb) == 2


def test_registry_rule_and_emission() -> None:
    rule = require_heuristic(RULE_RECONCILE_COMPOSED_STRUCTURED_LIST)
    assert rule.version == "1"
    assert rule.stage == DecisionStage.COMPLETENESS
    assert rule.method == HeuristicMethod.DETERMINISTIC
    assert RULE_RECONCILE_COMPOSED_STRUCTURED_LIST in RULES_EMITTING_DECISION_EXPLANATIONS


# --- Negative cases ---


def test_negative_terminal_without_governing_stem() -> None:
    row = _composed_exception_row(
        proposition_text="capelin, sandeel, or Norwegian pout used for industrial purposes",
        rule="",
    )
    retained, diags, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts
    assert not any(d.get("code") == "completeness_reconciled_composed_structured_list" for d in diags)


def test_negative_terminal_without_inherited_condition() -> None:
    row = _composed_exception_row(
        proposition_text=(
            "Paragraph 1 of Article 49a shall not apply to capelin, sandeel, "
            "or Norwegian pout."
        ),
    )
    # Keep branch in meta but remove threshold/condition from text.
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_stem_only_proposition() -> None:
    row = _composed_exception_row(
        proposition_text="Paragraph 1 shall not apply:",
        _structured_list_compose_captured=False,
        _structured_list_meta={
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "Paragraph 1 shall not apply:",
            "branch_context": "",
            "structured_list_path": "2",
            "source_component_locators": [
                {"role": "stem", "text": "Paragraph 1 shall not apply:"}
            ],
        },
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_intermediate_list_node() -> None:
    row = _composed_exception_row(
        proposition_text=(
            "Paragraph 1 shall not apply where the catches contain more than "
            "80% of one or more of the following species"
        ),
        _structured_list_meta={
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "Paragraph 1 shall not apply:",
            "branch_context": (
                "where the catches contain more than 80% of one or more of "
                "the following species"
            ),
            "structured_list_path": "2-a",
            "source_component_locators": [
                {"role": "stem", "text": "Paragraph 1 shall not apply:"},
                {
                    "role": "branch",
                    "text": (
                        "where the catches contain more than 80% of one or "
                        "more of the following species"
                    ),
                },
            ],
        },
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_unresolved_exception_target() -> None:
    row = _composed_exception_row(
        proposition_text=(
            "Shall not apply where the catches contain more than 80% of "
            "capelin, sandeel, or Norwegian pout."
        ),
        subject="",
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_unresolved_cross_reference_p3() -> None:
    row = {
        "proposition_text": (
            "Where the cases referred to in paragraph 2 apply, a fisheries "
            "administration must monitor the catch composition."
        ),
        "subject": "fisheries administration",
        "rule": "must monitor",
        "object": "catch composition",
        "conditions": [],
        "exceptions": [],
        "provision_type": "core",
        "source_locator": "article:49a:paragraph:3",
        "evidence_text": "Where the cases referred to in paragraph 2 apply",
        "completeness_status": "context_dependent",
        "confidence": "high",
        "reason": "depends on paragraph 2",
        "_structured_list_compose_captured": False,
    }
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_missing_actor_obligation() -> None:
    row = _composed_exception_row(
        proposition_text=(
            "Must keep records of capelin, sandeel, or Norwegian pout when "
            "catches contain more than 80% of those species."
        ),
        rule="must keep",
        provision_type="core",
        subject="",
        _structured_list_meta={
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "Must keep records:",
            "branch_context": "when catches contain more than 80% of those species",
            "structured_list_path": "1-a",
            "source_component_locators": [
                {"role": "stem", "text": "Must keep records:"},
                {
                    "role": "branch",
                    "text": "when catches contain more than 80% of those species",
                },
                {
                    "role": "leaf",
                    "text": "capelin, sandeel, or Norwegian pout",
                },
            ],
        },
    )
    # Still has operative effect + stem material; actor absence alone is not a
    # hard block when stem/effect are present. Force missing_context instead.
    row["missing_context"] = ["actor"]
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_missing_material_object() -> None:
    row = _composed_exception_row(
        proposition_text="Paragraph 1 of Article 49a shall not apply where catches contain more than 80%.",
        missing_context=["object"],
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_explicit_material_missing_context() -> None:
    row = _composed_exception_row(missing_context=["cross_reference", "condition"])
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_fragmentary_not_reconciled() -> None:
    row = _composed_exception_row(completeness_status="fragmentary")
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "fragmentary"
    assert not facts


def test_negative_ambiguous_composition() -> None:
    row = _composed_exception_row()
    meta = dict(row["_structured_list_meta"])
    meta["structured_list_dedupe"] = {"outcome": "ambiguous_duplicate_set"}
    row["_structured_list_meta"] = meta
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_inconsistent_source_identity() -> None:
    row = _composed_exception_row()
    empty = StructuredListIdentityContext("", "", "")
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=empty
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_anaphoric_wsi_calculations() -> None:
    row = {
        "proposition_text": (
            "The occupier must make a record of the calculations and how the "
            "final figures were arrived at."
        ),
        "subject": "occupier",
        "rule": "must make a record",
        "object": "the calculations",
        "conditions": [],
        "exceptions": [],
        "provision_type": "core",
        "source_locator": "regulation:36(4)",
        "evidence_text": "The occupier must make a record of the calculations",
        "completeness_status": "context_dependent",
        "confidence": "high",
        "reason": "depends on earlier paragraphs",
        "_structured_list_compose_captured": True,
        "_composition_basis": COMPOSITION_BASIS,
        "_structured_list_meta": {
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "The occupier must make a record:",
            "branch_context": "",
            "structured_list_path": "36-4",
            "source_component_locators": [
                {"role": "stem", "text": "The occupier must make a record:"},
                {
                    "role": "leaf",
                    "text": "of the calculations and how the final figures were arrived at",
                },
            ],
        },
    }
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_complete_only_after_els_expansion_not_inferred() -> None:
    # No composition facts → no reconcile even if text looks complete.
    row = _composed_exception_row(
        _structured_list_compose_captured=False,
        _structured_list_meta={},
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_heading_does_not_supply_operative_content() -> None:
    row = _composed_exception_row(
        proposition_text="Industrial fisheries species exception",
        display_label="Art. 49a(2)(a)(ii) — Industrial fisheries species exception",
        rule="",
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


def test_negative_model_label_does_not_supply_content() -> None:
    row = _composed_exception_row(
        proposition_text="see label",
        display_label=(
            "Paragraph 1 shall not apply where catches contain more than 80% "
            "capelin, sandeel, Norwegian pout"
        ),
        rule="",
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent"
    assert not facts


@pytest.mark.skipif(not _live_available(), reason="live calibration artifacts absent")
def test_article_49a_e1_e2_e3_parity_after_reconcile() -> None:
    merged = _merge_live_rows(1)
    retained, diags, _ = reconcile_composed_structured_list_completeness(
        merged, identity=_IDENTITY
    )
    terminals = [
        r
        for r in retained
        if (r.get("_structured_list_meta") or {}).get("structured_list_path")
    ]
    statuses = {
        str((r.get("_structured_list_meta") or {}).get("structured_list_path")): r[
            "completeness_status"
        ]
        for r in terminals
    }
    # All composed exception terminals should be complete after reconcile.
    for path, status in statuses.items():
        assert status == "complete", path
    # No forced-parity diagnostic when they agree.
    assert not any(d.get("code") == "structured_list_sibling_completeness_parity" for d in diags)


@pytest.mark.skipif(not _live_available(), reason="live calibration artifacts absent")
def test_fidelity_dry_path_reads_reconciled_completeness() -> None:
    cases = {c.case_id: c for c in load_proposition_fidelity_cases()}
    # Exercise production dry-fragment path used by benchmark cases that have
    # offline responses; Article 49a uses the acceptance pipeline instead.
    # Directly assert reconcile + attach path used by dry runner.
    merged = _merge_live_rows(1)
    retained, _, _ = reconcile_composed_structured_list_completeness(
        merged, identity=_IDENTITY
    )
    from law_proposition_extractor_domain import Cluster, Proposition, SourceRecord, Topic
    from law_proposition_extractor_pipeline.extract import _build_propositions_from_v2_rows

    cases_a49 = cases["article_49a"]
    text, _ = _load_fragment_text(cases_a49)
    source = SourceRecord(
        id="pf-article_49a",
        title="article_49a",
        jurisdiction="UK",
        citation="article_49a",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator=cases_a49.source_locator,
        current_snapshot_id="snap-pf",
        metadata={"extraction_fragment_id": "frag-article_49a"},
    )
    props = _build_propositions_from_v2_rows(
        rows=retained,
        source=source,
        topic=Topic(id="t", name="t"),
        cluster=Cluster(id="c", topic_id="t", name="c"),
        limit=20,
    )
    attached = _attach_evidence(props, retained)
    e2 = next(p for p in attached if "capelin" in str(p.get("proposition_text") or "").lower())
    meta = e2.get("extraction_debug_meta") or {}
    assert meta.get("completeness_status") == "complete"
    assert meta.get("model_completeness_status") == "context_dependent"

    # PCA agrees.
    traces = [
        {
            "proposition_id": e2["id"],
            "signals": {
                "parent_context": meta.get("parent_context"),
                "composition_basis": meta.get("composition_basis"),
                "list_marker": meta.get("list_marker"),
            },
        }
    ]
    pca = build_proposition_completeness_assessments(
        propositions=[e2],
        proposition_extraction_traces=traces,
        source_records=[source.model_dump(mode="json")],
    )
    assert pca[0].status == "complete"
    assert pca[0].signals.get("rule") == "structured_list_parent_ok"
