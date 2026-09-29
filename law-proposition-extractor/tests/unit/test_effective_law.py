"""Unit tests for proposition relationships and effective law statement export."""

from __future__ import annotations

from law_proposition_extractor_pipeline.effective_law import (
    attach_effective_law_artifacts,
    build_effective_law_statements,
    build_proposition_relationships,
    classify_presentation_role,
    classify_standalone_status,
    effective_law_payload_digest,
    prune_subsumed_locators,
)

SOURCE = "lex-test-source-001"


def _prop(
    *,
    prop_id: str,
    proposition_text: str,
    fragment_locator: str = "regulation 1",
    legal_effect_type: str = "obligation",
    proposition_tier: str = "substantive_rule",
    is_compliance_relevant: bool = True,
    explicit_cross_reference_targets: list[str] | None = None,
    extraction_debug_meta: dict | None = None,
    notes: str = "",
) -> dict:
    return {
        "id": prop_id,
        "source_record_id": SOURCE,
        "fragment_locator": fragment_locator,
        "proposition_text": proposition_text,
        "legal_effect_type": legal_effect_type,
        "proposition_tier": proposition_tier,
        "is_compliance_relevant": is_compliance_relevant,
        "explicit_cross_reference_targets": explicit_cross_reference_targets or [],
        "cross_reference_targets": [],
        "extraction_debug_meta": extraction_debug_meta or {},
        "notes": notes,
    }


def test_standalone_obligation_becomes_guidance_matching_candidate() -> None:
    props = [
        _prop(
            prop_id="prop:obligation-1",
            proposition_text="An occupier must not cause pollution.",
            fragment_locator="regulation 2(1)",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    statements = build_effective_law_statements(props, run_id="run-test")["statements"]
    assert len(statements) == 1
    stmt = statements[0]
    assert stmt["presentation_role"] == "guidance_matching_candidate"
    assert stmt["standalone_status"] == "standalone"
    assert stmt["statement_text"] == props[0]["proposition_text"]
    assert stmt["source_proposition_ids"] == ["prop:obligation-1"]


def test_definition_is_supporting_definition_not_primary_guidance() -> None:
    props = [
        _prop(
            prop_id="prop:def-slurry",
            proposition_text='"slurry" means excreta produced by livestock.',
            fragment_locator="regulation 2(1)",
            legal_effect_type="definition",
            proposition_tier="definitional_rule",
            is_compliance_relevant=False,
        )
    ]
    stmt = build_effective_law_statements(props, run_id="run-test")["statements"][0]
    assert stmt["presentation_role"] == "supporting_definition"
    assert stmt["presentation_role"] != "guidance_matching_candidate"


def test_cross_reference_unresolved_target() -> None:
    props = [
        _prop(
            prop_id="prop:xref-unresolved",
            proposition_text="The factors include those in the other instrument.",
            fragment_locator="regulation 5(3)",
            legal_effect_type="cross_reference",
            proposition_tier="relationship_reference",
            is_compliance_relevant=False,
            explicit_cross_reference_targets=["regulation 99"],
        )
    ]
    rel = build_proposition_relationships(props, run_id="run-test")
    stmt = build_effective_law_statements(props, run_id="run-test", relationships=rel)["statements"][0]

    assert stmt["presentation_role"] == "context_connector"
    assert stmt["presentation_role"] != "guidance_matching_candidate"
    assert stmt["standalone_status"] in {"unresolved_reference", "relationship_only", "partially_resolved"}
    assert any("unresolved" in w for w in stmt["warnings"])

    text_edges = [e for e in rel["edges"] if e["type"] == "text_references_locator"]
    assert len(text_edges) >= 1
    assert text_edges[0]["provenance"]["field"] == "explicit_cross_reference_targets"
    assert text_edges[0]["provenance"]["artefact"] == "propositions.json"
    resolve_edges = [e for e in rel["edges"] if e["type"] == "locator_resolves_to"]
    assert resolve_edges == []


def test_cross_reference_single_same_source_target() -> None:
    host = _prop(
        prop_id="prop:host-reg4-2",
        proposition_text="Factor A and factor B must be considered.",
        fragment_locator="regulation 4(2)",
        legal_effect_type="obligation",
        proposition_tier="substantive_rule",
    )
    xref = _prop(
        prop_id="prop:xref-single",
        proposition_text="The factors under regulation 4(2) apply here.",
        fragment_locator="regulation 9(3)",
        legal_effect_type="cross_reference",
        proposition_tier="relationship_reference",
        is_compliance_relevant=False,
        explicit_cross_reference_targets=["regulation 4(2)"],
    )
    props = [host, xref]
    rel = build_proposition_relationships(props, run_id="run-test")
    statements = build_effective_law_statements(props, run_id="run-test", relationships=rel)["statements"]
    by_id = {s["source_proposition_ids"][0]: s for s in statements}

    assert by_id["prop:xref-single"]["presentation_role"] == "context_connector"
    assert by_id["prop:xref-single"]["presentation_role"] != "guidance_matching_candidate"

    resolve_edges = [e for e in rel["edges"] if e["type"] == "locator_resolves_to"]
    assert len(resolve_edges) == 1
    assert resolve_edges[0]["review_status"] == "accepted"
    assert resolve_edges[0]["to"] == "prop:host-reg4-2"
    assert "prop:xref-single" in by_id["prop:host-reg4-2"]["supporting_proposition_ids"]
    assert by_id["prop:host-reg4-2"]["required_context"] == []
    assert by_id["prop:host-reg4-2"]["connector_context"] == []


def test_cross_reference_ambiguous_same_source_targets() -> None:
    hosts = [
        _prop(
            prop_id=f"prop:host-reg4-{n}",
            proposition_text=f"Host rule variant {n}.",
            fragment_locator="regulation 4",
            legal_effect_type="obligation",
        )
        for n in (1, 2)
    ]
    xref = _prop(
        prop_id="prop:xref-ambiguous",
        proposition_text="See regulation 4 for applicable factors.",
        fragment_locator="regulation 9(3)",
        legal_effect_type="cross_reference",
        proposition_tier="relationship_reference",
        is_compliance_relevant=False,
        explicit_cross_reference_targets=["regulation 4"],
    )
    props = [*hosts, xref]
    rel = build_proposition_relationships(props, run_id="run-test")
    stmt = build_effective_law_statements(props, run_id="run-test", relationships=rel)["statements"]
    xref_stmt = next(s for s in stmt if s["source_proposition_ids"] == ["prop:xref-ambiguous"])

    resolve_edges = [e for e in rel["edges"] if e["type"] == "locator_resolves_to"]
    assert len(resolve_edges) == 2
    assert all(e["review_status"] == "ambiguous" for e in resolve_edges)
    assert xref_stmt["presentation_role"] == "context_connector"
    assert any(ctx["resolution_status"] == "ambiguous" for ctx in xref_stmt["required_context"])
    assert any("ambiguous" in w for w in xref_stmt["warnings"])


def test_motivating_regulation_9_3_regulation_4_2_shape() -> None:
    """prop:8b25ce8a1efdadf0-style cross-reference must not be a primary guidance law."""
    props = [
        _prop(
            prop_id="prop:8b25ce8a1efdadf0",
            proposition_text=(
                "The factors to be taken into account under regulation 9(2) include "
                "those specified in regulation 4(2)."
            ),
            fragment_locator="regulation 9(3)",
            legal_effect_type="cross_reference",
            proposition_tier="relationship_reference",
            is_compliance_relevant=False,
            explicit_cross_reference_targets=["regulation 9", "regulation 4"],
            notes="Cross-reference to external regulation; content of regulation 4(2) not provided.",
        ),
        _prop(
            prop_id="prop:host-reg9-2",
            proposition_text="Host factors scope for regulation 9(2).",
            fragment_locator="regulation 9(2)",
            legal_effect_type="obligation",
            proposition_tier="substantive_rule",
        ),
        _prop(
            prop_id="prop:reg4-2-host",
            proposition_text="Risk factors A and B are listed.",
            fragment_locator="regulation 4(2)",
            legal_effect_type="obligation",
            proposition_tier="substantive_rule",
        ),
    ]
    rel = build_proposition_relationships(props, run_id="run-001")
    stmt = build_effective_law_statements(props, run_id="run-001", relationships=rel)["statements"]
    motivating = next(s for s in stmt if s["source_proposition_ids"] == ["prop:8b25ce8a1efdadf0"])

    assert motivating["presentation_role"] == "context_connector"
    assert motivating["presentation_role"] != "guidance_matching_candidate"
    assert motivating["standalone_status"] in {"relationship_only", "partially_resolved"}
    assert motivating["warnings"] == []
    assert classify_presentation_role(props[0]) == "context_connector"

    locators = {ctx["locator"] for ctx in motivating["required_context"]}
    assert locators == {"regulation 9(2)", "regulation 4(2)"}
    assert "regulation 9" not in locators
    assert "regulation 4" not in locators

    by_locator = {ctx["locator"]: ctx for ctx in motivating["required_context"]}
    assert by_locator["regulation 9(2)"]["kind"] == "host_rule"
    assert by_locator["regulation 9(2)"]["resolution_status"] == "resolved"
    assert by_locator["regulation 9(2)"]["proposition_ids"] == ["prop:host-reg9-2"]
    assert by_locator["regulation 4(2)"]["kind"] == "incorporated_factors"
    assert by_locator["regulation 4(2)"]["resolution_status"] == "resolved"
    assert by_locator["regulation 4(2)"]["proposition_ids"] == ["prop:reg4-2-host"]
    assert "prop:8b25ce8a1efdadf0" not in {
        pid for ctx in motivating["required_context"] for pid in ctx["proposition_ids"]
    }

    host_stmt = next(s for s in stmt if s["source_proposition_ids"] == ["prop:host-reg9-2"])
    imported_stmt = next(s for s in stmt if s["source_proposition_ids"] == ["prop:reg4-2-host"])
    assert host_stmt["required_context"] == []
    assert imported_stmt["required_context"] == []
    assert host_stmt["connector_context"][0]["kind"] == "incorporates_context_from"
    assert imported_stmt["connector_context"][0]["kind"] == "incorporated_elsewhere_by"

    text_edges = [e for e in rel["edges"] if e["from"] == "prop:8b25ce8a1efdadf0"]
    assert len(text_edges) >= 2
    assert all(e["provenance"]["artefact"] == "propositions.json" for e in text_edges)
    broad_edges = [e for e in text_edges if e.get("locator_specificity") == "broad"]
    assert broad_edges


def test_prune_subsumed_locators_drops_broad_parent_when_child_resolved() -> None:
    entries = [
        {
            "kind": "referenced_locator",
            "locator": "regulation 4",
            "resolution_status": "ambiguous",
            "proposition_ids": ["prop:a", "prop:b"],
        },
        {
            "kind": "incorporated_factors",
            "locator": "regulation 4(2)",
            "resolution_status": "resolved",
            "proposition_ids": ["prop:host"],
        },
    ]
    pruned = prune_subsumed_locators(entries)
    assert [e["locator"] for e in pruned] == ["regulation 4(2)"]


def test_broad_ambiguous_parent_warning_suppressed_when_child_resolves() -> None:
    host_42 = _prop(
        prop_id="prop:host-4-2",
        proposition_text="Listed factors.",
        fragment_locator="regulation 4(2)",
    )
    xref = _prop(
        prop_id="prop:xref-broad-child",
        proposition_text=(
            "Factors under regulation 4(2) as specified in regulation 4(2) also see regulation 4."
        ),
        fragment_locator="regulation 9(1)",
        legal_effect_type="cross_reference",
        proposition_tier="relationship_reference",
        is_compliance_relevant=False,
        explicit_cross_reference_targets=["regulation 4", "regulation 4(2)"],
    )
    hosts_broad = [
        _prop(
            prop_id=f"prop:host-4-{n}",
            proposition_text=f"Broad host {n}.",
            fragment_locator="regulation 4",
        )
        for n in (1, 2)
    ]
    props = [host_42, *hosts_broad, xref]
    rel = build_proposition_relationships(props, run_id="run-test")
    xref_stmt = next(
        s
        for s in build_effective_law_statements(props, run_id="run-test", relationships=rel)[
            "statements"
        ]
        if s["source_proposition_ids"] == ["prop:xref-broad-child"]
    )
    assert {ctx["locator"] for ctx in xref_stmt["required_context"]} == {"regulation 4(2)"}
    assert xref_stmt["warnings"] == []


def test_bs_reference_classified_as_external_not_unresolved_paragraph() -> None:
    text = (
        "The walls of any pipes must be protected against corrosion in accordance with "
        "paragraph 7 of the code of practice on buildings and structures for agriculture "
        "published by the British Standards Institution and numbered BS 5502: Part 50:1993."
    )
    props = [
        _prop(
            prop_id="prop:bs-corrosion",
            proposition_text=text,
            fragment_locator="schedule 2, paragraph 2",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    stmt = build_effective_law_statements(props, run_id="run-test")["statements"][0]
    assert stmt["standalone_status"] == "standalone"
    assert not any("unresolved locator" in w for w in stmt["warnings"])
    locators = {ctx["locator"] for ctx in stmt["required_context"]}
    assert "paragraph 7" not in locators
    external = [ctx for ctx in stmt["required_context"] if ctx["resolution_status"] == "external_reference"]
    assert len(external) == 1
    assert external[0]["kind"] == "external_standard_reference"
    assert "BS 5502: Part 50:1993" in external[0]["locator"]
    assert "paragraph 7" in external[0]["locator"]


def test_rb209_classified_as_external_guidance() -> None:
    props = [
        _prop(
            prop_id="prop:rb209",
            proposition_text=(
                "The occupier must establish nitrogen availability by reference to the "
                "values given in the Nutrient Management Guide (RB209), or by sampling."
            ),
            fragment_locator="regulation 9(3)",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    stmt = build_effective_law_statements(props, run_id="run-test")["statements"][0]
    guidance = [ctx for ctx in stmt["required_context"] if ctx["kind"] == "external_guidance_reference"]
    assert len(guidance) == 1
    assert guidance[0]["locator"] == "Nutrient Management Guide (RB209)"
    assert guidance[0]["resolution_status"] == "external_reference"


def test_self_resolution_omitted_from_required_context() -> None:
    xref = _prop(
        prop_id="prop:xref-self",
        proposition_text="See regulation 9 for applicable factors under regulation 9(2).",
        fragment_locator="regulation 9(3)",
        legal_effect_type="cross_reference",
        proposition_tier="relationship_reference",
        is_compliance_relevant=False,
        explicit_cross_reference_targets=["regulation 9"],
    )
    host_92 = _prop(
        prop_id="prop:host-9-2",
        proposition_text="Host rule at 9(2).",
        fragment_locator="regulation 9(2)",
    )
    props = [xref, host_92]
    rel = build_proposition_relationships(props, run_id="run-test")
    xref_stmt = next(
        s
        for s in build_effective_law_statements(props, run_id="run-test", relationships=rel)[
            "statements"
        ]
        if s["source_proposition_ids"] == ["prop:xref-self"]
    )
    assert "regulation 9" not in {ctx["locator"] for ctx in xref_stmt["required_context"]}
    assert all(
        pid != "prop:xref-self"
        for ctx in xref_stmt["required_context"]
        for pid in ctx["proposition_ids"]
    )


def test_relationship_edge_ids_are_stable() -> None:
    props = [
        _prop(
            prop_id="prop:stable-xref",
            proposition_text="As set out in regulation 7(1).",
            fragment_locator="regulation 8",
            legal_effect_type="cross_reference",
            proposition_tier="relationship_reference",
            is_compliance_relevant=False,
            explicit_cross_reference_targets=["regulation 7(1)"],
        )
    ]
    first = build_proposition_relationships(props, run_id="run-stable")
    second = build_proposition_relationships(props, run_id="run-stable")
    assert [e["id"] for e in first["edges"]] == [e["id"] for e in second["edges"]]
    assert all(e["id"].startswith("prel:") for e in first["edges"])


def test_attach_effective_law_artifacts_on_bundle() -> None:
    bundle = {
        "run": {"id": "run-001"},
        "propositions": [
            _prop(
                prop_id="prop:bundle-1",
                proposition_text="Must store slurry safely.",
            )
        ],
    }
    attach_effective_law_artifacts(bundle)
    assert "proposition_relationships" in bundle
    assert "effective_law_statements" in bundle
    assert "proposition_matcher_law_candidates" in bundle
    assert "legal_rule_groups" in bundle
    assert "legal_rule_relationships" in bundle
    assert bundle["proposition_relationships"]["schema_version"] == "1"
    assert bundle["effective_law_statements"]["run_id"] == "run-001"
    assert bundle["proposition_matcher_law_candidates"]["run_id"] == "run-001"
    assert bundle["legal_rule_groups"]["run_id"] == "run-001"
    assert bundle["legal_rule_groups"]["groups"] == []
    assert bundle["legal_rule_relationships"]["relationships"] == []
    assert bundle["effective_law_statements"].get("diagnostics") == []
    first_statement = bundle["effective_law_statements"]["statements"][0]
    assert "composition_trace" in first_statement
    assert len(first_statement["composition_trace"]) > 0
    assert first_statement["composition_trace"][0]["role"] == "core_proposition"


def test_effective_law_digest_stable_for_identical_input() -> None:
    props = [
        _prop(
            prop_id="prop:digest",
            proposition_text="An occupier must comply.",
        )
    ]
    a = build_effective_law_statements(props, run_id="run-digest")
    b = build_effective_law_statements(props, run_id="run-digest")
    assert effective_law_payload_digest(a) == effective_law_payload_digest(b)
