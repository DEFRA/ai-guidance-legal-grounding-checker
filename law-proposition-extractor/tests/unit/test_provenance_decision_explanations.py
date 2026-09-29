"""Unit tests for provenance / source-effect DecisionExplanation emission."""

from __future__ import annotations

from datetime import date
from xml.etree import ElementTree

from law_proposition_extractor_domain import (
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    SourceManifestationBasis,
    SourceManifestationType,
)
from law_proposition_extractor_pipeline.heuristics.explainability_coverage import (
    RULES_EMITTING_DECISION_EXPLANATIONS,
    emits_decision_explanation,
)
from law_proposition_extractor_pipeline.heuristics.provenance_attach import (
    build_provenance_and_source_effect_explanations,
    collect_provenance_and_source_effect_facts,
)
from law_proposition_extractor_pipeline.heuristics.provenance_explanations import (
    build_provenance_decision_explanations,
    manifestation_facts_from_snapshot,
)
from law_proposition_extractor_pipeline.heuristics.registry import (
    RULE_ASSESS_INDEPENDENT_CONSUMPTION,
    RULE_CLASSIFY_MANIFESTATION,
    RULE_CLASSIFY_OUTSTANDING_STATUS,
    RULE_EXCLUDE_UNRELATED_FRAGMENT,
    RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR,
    RULE_LINK_EXACT_FRAGMENT,
    RULE_PARSE_AUTHORITY_ANNOTATION,
    RULE_PRESERVE_AS_OF_UNKNOWN,
    list_heuristics,
    require_heuristic,
)
from law_proposition_extractor_pipeline.heuristics.source_effect_explanations import (
    build_source_effect_decision_explanations,
    collect_parse_and_outstanding_facts,
)
from law_proposition_extractor_pipeline.source_effect_relevance import capture_source_effect_relevance_facts
from law_proposition_extractor_pipeline.sources.legislation_manifestation import resolve_manifestation_provenance


def test_new_provenance_rules_registered_and_emitting() -> None:
    for rule_id in (
        RULE_CLASSIFY_MANIFESTATION,
        RULE_PRESERVE_AS_OF_UNKNOWN,
        RULE_PARSE_AUTHORITY_ANNOTATION,
        RULE_LINK_EXACT_FRAGMENT,
        RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR,
        RULE_EXCLUDE_UNRELATED_FRAGMENT,
        RULE_CLASSIFY_OUTSTANDING_STATUS,
        RULE_ASSESS_INDEPENDENT_CONSUMPTION,
    ):
        h = require_heuristic(rule_id)
        assert h.version == "1"
        assert emits_decision_explanation(rule_id)
        assert rule_id in RULES_EMITTING_DECISION_EXPLANATIONS
    assert not list(
        set(
            {
                RULE_CLASSIFY_MANIFESTATION,
                RULE_PRESERVE_AS_OF_UNKNOWN,
                RULE_PARSE_AUTHORITY_ANNOTATION,
                RULE_LINK_EXACT_FRAGMENT,
                RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR,
                RULE_EXCLUDE_UNRELATED_FRAGMENT,
                RULE_CLASSIFY_OUTSTANDING_STATUS,
                RULE_ASSESS_INDEPENDENT_CONSUMPTION,
            }
        )
        - {h.rule_id for h in list_heuristics()}
    )


def test_revised_source_metadata_emits_manifestation_decision() -> None:
    xml = """<?xml version="1.0"?>
    <Legislation DocumentURI="http://www.legislation.gov.uk/eur/2009/1224">
      <Metadata>
        <DocumentStatus Value="revised"/>
        <valid>2025-02-27</valid>
      </Metadata>
    </Legislation>
    """
    root = ElementTree.fromstring(xml)
    prov = resolve_manifestation_provenance(
        requested_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
        resolved_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
        xml_root=root,
    )
    assert prov.manifestation_type == SourceManifestationType.REVISED
    assert prov.manifestation_basis == SourceManifestationBasis.SOURCE_METADATA
    assert prov.resolved_as_of_date is None
    facts = prov.as_decision_facts(source_snapshot_id="snap-1")
    facts[0]["retrieved_at"] = "2026-07-14T12:00:00Z"
    explanations = build_provenance_decision_explanations(facts)
    classify = [e for e in explanations if e.rule_id == RULE_CLASSIFY_MANIFESTATION]
    assert len(classify) == 1
    assert classify[0].outcome == "classified_as_revised"
    assert classify[0].stage == DecisionStage.PROVENANCE
    assert classify[0].subject_kind == DecisionSubjectKind.SOURCE_SNAPSHOT
    assert "applied all amendments" not in classify[0].summary.lower()
    as_of = [e for e in explanations if e.rule_id == RULE_PRESERVE_AS_OF_UNKNOWN]
    assert len(as_of) == 1
    assert as_of[0].outcome == "legal_as_of_not_established"


def test_point_in_time_request_explained() -> None:
    prov = resolve_manifestation_provenance(
        requested_url="https://www.legislation.gov.uk/eur/2009/1224/2020-01-31/data.xml",
        resolved_url="https://www.legislation.gov.uk/eur/2009/1224/2020-01-31/data.xml",
        xml_root=None,
    )
    # Request-only PIT without source metadata → unknown resolved type, basis request_url
    assert prov.manifestation_basis == SourceManifestationBasis.REQUEST_URL
    assert prov.requested_manifestation == SourceManifestationType.POINT_IN_TIME
    facts = prov.as_decision_facts(source_snapshot_id="snap-pit")
    explanations = build_provenance_decision_explanations(facts)
    classify = [e for e in explanations if e.rule_id == RULE_CLASSIFY_MANIFESTATION][0]
    assert classify.subject_id == "snap-pit"
    assert classify.metadata.get("requested_as_of_date") == "2020-01-31" or any(
        ev.kind == "requested_as_of_date" and "2020-01-31" in str(ev.value)
        for ev in classify.evidence
    )


def test_unknown_manifestation_truthful() -> None:
    prov = resolve_manifestation_provenance(
        requested_url="https://example.com/not-legislation",
        xml_root=None,
    )
    assert prov.manifestation_type == SourceManifestationType.UNKNOWN
    facts = prov.as_decision_facts(source_snapshot_id="snap-u")
    explanations = build_provenance_decision_explanations(facts)
    assert explanations[0].outcome == "classified_as_unknown"


def test_retrieval_and_revision_not_used_as_as_of() -> None:
    snap = {
        "id": "snap-r",
        "manifestation_type": "revised",
        "manifestation_basis": "source_metadata",
        "requested_as_of_date": None,
        "resolved_as_of_date": None,
        "source_revision_date": "2025-02-27",
        "retrieved_at": "2026-07-14T21:22:45Z",
        "metadata": {},
    }
    facts = manifestation_facts_from_snapshot(snap)
    explanations = build_provenance_decision_explanations(facts)
    classify = [e for e in explanations if e.rule_id == RULE_CLASSIFY_MANIFESTATION][0]
    retrieved = next(ev for ev in classify.evidence if ev.kind == "retrieved_at")
    revision = next(ev for ev in classify.evidence if ev.kind == "source_revision_date")
    as_of = next(ev for ev in classify.evidence if ev.kind == "resolved_as_of_date")
    assert retrieved.value == "2026-07-14T21:22:45Z"
    assert revision.value == "2025-02-27"
    assert as_of.value == "(not recorded)"
    assert retrieved.value != as_of.value


def test_manifestation_outcome_changes_decision_id() -> None:
    base = {
        "fact_kind": "classify_manifestation",
        "source_snapshot_id": "snap-x",
        "manifestation_type": "revised",
        "manifestation_basis": "source_metadata",
        "outcome": "classified_as_revised",
        "winning_evidence_basis": "source_metadata",
        "requested_as_of_date": None,
        "resolved_as_of_date": None,
        "source_revision_date": None,
        "conflicts": [],
        "evidence": [],
    }
    a = build_provenance_decision_explanations([base])[0]
    other = dict(base)
    other["manifestation_type"] = "original"
    other["outcome"] = "classified_as_original"
    b = build_provenance_decision_explanations([other])[0]
    assert a.id != b.id


def test_relevance_exact_and_ancestor_and_sibling_isolation() -> None:
    fragments = [
        {
            "id": "frag-art",
            "locator": "article:49a",
            "parent_fragment_id": None,
            "source_record_id": "src",
            "source_snapshot_id": "snap",
        },
        {
            "id": "frag-p1",
            "locator": "article:49a:paragraph:1",
            "parent_fragment_id": "frag-art",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
        },
        {
            "id": "frag-p2",
            "locator": "article:49a:paragraph:2",
            "parent_fragment_id": "frag-art",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
        },
        {
            "id": "frag-a1",
            "locator": "article:1",
            "parent_fragment_id": None,
            "source_record_id": "src",
            "source_snapshot_id": "snap",
        },
    ]
    effects = [
        {
            "id": "eff-art",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
            "annotation_label": "F2",
            "affected_locator": "article:49a",
            "affected_source_fragment_id": "frag-art",
        },
        {
            "id": "eff-p1",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
            "annotation_label": "F4",
            "affected_locator": "article:49a:paragraph:1",
            "affected_source_fragment_id": "frag-p1",
        },
        {
            "id": "eff-a1",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
            "annotation_label": "F1",
            "affected_locator": "article:1",
            "affected_source_fragment_id": "frag-a1",
        },
    ]
    links = [
        {
            "id": "lnk-art",
            "effect_id": "eff-art",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
            "source_fragment_id": "frag-art",
            "affected_locator": "article:49a",
        },
        {
            "id": "lnk-p1",
            "effect_id": "eff-p1",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
            "source_fragment_id": "frag-p1",
            "affected_locator": "article:49a:paragraph:1",
        },
        {
            "id": "lnk-a1",
            "effect_id": "eff-a1",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
            "source_fragment_id": "frag-a1",
            "affected_locator": "article:1",
        },
    ]
    propositions = [
        {
            "id": "prop-p1",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
            "source_fragment_id": "frag-p1",
            "fragment_locator": "article:49a:paragraph:1",
        },
        {
            "id": "prop-p2",
            "source_record_id": "src",
            "source_snapshot_id": "snap",
            "source_fragment_id": "frag-p2",
            "fragment_locator": "article:49a:paragraph:2",
        },
    ]
    statements = [
        {"id": "stmt-p1", "source_proposition_ids": ["prop-p1"]},
        {"id": "stmt-p2", "source_proposition_ids": ["prop-p2"]},
    ]
    facts = capture_source_effect_relevance_facts(
        statements=statements,
        propositions=propositions,
        fragments=fragments,
        effects=effects,
        effect_links=links,
    )
    explanations = build_source_effect_decision_explanations(facts)

    inherit_p2 = [
        e
        for e in explanations
        if e.rule_id == RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR
        and e.subject_id == "stmt-p2"
        and e.metadata.get("effect_id") == "eff-art"
    ]
    assert len(inherit_p2) == 1
    assert inherit_p2[0].decision_type == DecisionType.INHERIT

    exact_p1 = [
        e
        for e in explanations
        if e.rule_id == RULE_LINK_EXACT_FRAGMENT
        and e.subject_id == "stmt-p1"
        and e.metadata.get("effect_id") == "eff-p1"
    ]
    assert len(exact_p1) == 1

    leak = [
        e
        for e in explanations
        if e.metadata.get("effect_id") == "eff-p1" and e.subject_id == "stmt-p2"
    ]
    assert leak == []

    excluded = [
        e
        for e in explanations
        if e.rule_id == RULE_EXCLUDE_UNRELATED_FRAGMENT
        and e.metadata.get("effect_id") == "eff-a1"
    ]
    assert excluded
    assert "not a structural ancestor" in excluded[0].summary.lower()


def test_parse_and_outstanding_from_artifact_no_xml_rerun() -> None:
    artifact = {
        "effects": [
            {
                "id": "eff-1",
                "source_snapshot_id": "snap",
                "annotation_id": "c1",
                "annotation_label": "F1",
                "effect_category": "substitution",
                "affecting_instrument_citation": "S.I. 2019/739",
                "affected_locator": "article:49a",
            }
        ],
        "outstanding_effects_status": "source_reports_present",
        "metadata": {},
    }
    facts = collect_parse_and_outstanding_facts(effects_artifact=artifact)
    explanations = build_source_effect_decision_explanations(facts)
    parse = [e for e in explanations if e.rule_id == RULE_PARSE_AUTHORITY_ANNOTATION]
    assert len(parse) == 1
    assert "not independent legal analysis" in parse[0].summary.lower() or "not" in parse[0].summary.lower()
    outstanding = [e for e in explanations if e.rule_id == RULE_CLASSIFY_OUTSTANDING_STATUS]
    assert outstanding[0].outcome == "source_reports_present"


def test_duplicate_relevance_facts_collapse() -> None:
    facts = [
        {
            "fact_kind": "link_exact_fragment",
            "outcome": "source_effect_relevant",
            "effective_law_statement_id": "stmt",
            "effect_id": "eff",
            "relevance_basis": "exact_fragment",
            "linked_fragment_id": "frag",
            "linked_locator": "article:49a:paragraph:1",
            "source_snapshot_id": "snap",
        },
        {
            "fact_kind": "link_exact_fragment",
            "outcome": "source_effect_relevant",
            "effective_law_statement_id": "stmt",
            "effect_id": "eff",
            "relevance_basis": "exact_fragment",
            "linked_fragment_id": "frag",
            "linked_locator": "article:49a:paragraph:1",
            "source_snapshot_id": "snap",
        },
    ]
    explanations = build_source_effect_decision_explanations(facts)
    assert len(explanations) == 1


def test_bundle_attach_projects_without_rerunning_manifestation_parser() -> None:
    bundle = {
        "run": {"id": "run-t"},
        "source_snapshots": [
            {
                "id": "snap",
                "manifestation_type": "revised",
                "manifestation_basis": "source_metadata",
                "requested_as_of_date": None,
                "resolved_as_of_date": None,
                "source_revision_date": date(2025, 2, 27),
                "retrieved_at": "2026-07-14T00:00:00Z",
                "metadata": {},
            }
        ],
        "source_legal_effects": {
            "effects": [],
            "effect_links": [],
            "outstanding_effects_status": "source_status_unknown",
            "metadata": {},
        },
        "propositions": [],
        "source_fragments": [],
        "effective_law_statements": {"statements": []},
        "decision_explanations": {"schema_version": "1", "run_id": "run-t", "decisions": []},
    }
    facts = collect_provenance_and_source_effect_facts(bundle)
    # Must not require XML; projection from snapshot fields only.
    assert any(f.get("fact_kind") == "classify_manifestation" for f in facts)
    explanations = build_provenance_and_source_effect_explanations(facts)
    assert any(e.rule_id == RULE_CLASSIFY_MANIFESTATION for e in explanations)
