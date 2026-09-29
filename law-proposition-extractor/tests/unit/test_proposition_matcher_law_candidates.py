"""Unit tests for Proposition Matcher law candidate export."""

from __future__ import annotations

from law_proposition_extractor_pipeline.proposition_matcher_law_candidates import (
    _candidate_dedupe_key,
    _normalize_locator_for_dedupe,
    build_proposition_matcher_law_candidates,
    canonical_provision_path,
    preferred_locator_label,
)
from law_proposition_extractor_pipeline.effective_law import (
    attach_effective_law_artifacts,
    build_effective_law_statements,
    build_proposition_relationships,
)

SOURCE = "lex-test-source-001"
SOURCE_B = "lex-test-source-002"


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
    label: str = "",
    source_fragment_id: str = "frag-test-001",
    territorial_application: list[str] | None = None,
    extent: list[str] | None = None,
) -> dict:
    row: dict = {
        "id": prop_id,
        "source_record_id": SOURCE,
        "source_snapshot_id": "snap-test-v1",
        "source_fragment_id": source_fragment_id,
        "fragment_locator": fragment_locator,
        "proposition_text": proposition_text,
        "label": label,
        "legal_effect_type": legal_effect_type,
        "proposition_tier": proposition_tier,
        "is_compliance_relevant": is_compliance_relevant,
        "explicit_cross_reference_targets": explicit_cross_reference_targets or [],
        "cross_reference_targets": [],
        "extraction_debug_meta": extraction_debug_meta or {},
        "notes": "",
        "extraction_trace_id": "trace-test-001",
        "jurisdiction": "UK",
        "source_jurisdiction": "UK",
        "territorial_application": list(territorial_application or []),
        "extent": list(extent if extent is not None else []),
    }
    return row


def _law_bundle(props: list[dict], *, run_id: str = "run-test") -> dict:
    rel = build_proposition_relationships(props, run_id=run_id)
    return build_effective_law_statements(props, run_id=run_id, relationships=rel)


def _candidates_for_props(props: list[dict], **kwargs) -> dict:
    law = _law_bundle(props)
    return build_proposition_matcher_law_candidates(
        effective_law_statements=law,
        propositions=props,
        **kwargs,
    )


def test_standalone_guidance_candidate_ready() -> None:
    props = [
        _prop(
            prop_id="prop:obligation-1",
            proposition_text="An occupier must not cause pollution.",
            fragment_locator="regulation 2(1)",
            extraction_debug_meta={"completeness_status": "complete"},
            label="Pollution prohibition",
        )
    ]
    payload = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "title": "Test Regulations 2015",
                    "citation": "SI 2015/1234",
                }
            ]
        },
    )
    assert payload["candidate_count"] == 1
    cand = payload["candidates"][0]
    assert cand["candidate_status"] == "ready"
    assert cand["risk_flags"] == []
    assert cand["match_role"] == "primary_law_candidate"
    assert cand["presentation"]["title"] == "Pollution prohibition"
    assert "SI 2015/1234" in cand["evidence"]["citations"]
    assert SOURCE in cand["evidence"]["source_record_ids"]
    assert "frag-test-001" in cand["evidence"]["source_fragment_ids"]
    assert cand["matching_text"].startswith("Title: Pollution prohibition\nLaw:")
    assert "SI 2015/1234, regulation:2:paragraph:1" in cand["matching_text"]
    assert cand["presentation"]["locator_label"] == "regulation:2:paragraph:1"
    assert "\n" not in cand["normalized_matching_text"]
    assert cand["normalized_matching_text"].startswith(
        "title: pollution prohibition law: an occupier must not cause pollution."
    )
    assert "prop:" not in cand["matching_text"]
    assert payload["altitude_summary"]["chapeau_suppressed_count"] == 0


def test_partially_resolved_guidance_usable_with_context() -> None:
    host = _prop(
        prop_id="prop:host",
        proposition_text="Factor A and factor B must be considered.",
        fragment_locator="regulation 4(2)",
    )
    xref = _prop(
        prop_id="prop:xref-resolved",
        proposition_text="The factors under regulation 4(2) apply here.",
        fragment_locator="regulation 9(3)",
        legal_effect_type="cross_reference",
        proposition_tier="relationship_reference",
        is_compliance_relevant=False,
        explicit_cross_reference_targets=["regulation 4(2)"],
    )
    props = [host, xref]
    law = _law_bundle(props)
    host_stmt = next(s for s in law["statements"] if s["source_proposition_ids"] == ["prop:host"])
    assert host_stmt["presentation_role"] == "guidance_matching_candidate"
    assert host_stmt["standalone_status"] == "partially_resolved"
    assert host_stmt["warnings"] == []

    cand = _candidates_for_props(props)["candidates"][0]
    assert cand["source_proposition_ids"] == ["prop:host"]
    assert cand["candidate_status"] == "usable_with_context"
    assert "partially_resolved" in cand["risk_flags"]
    assert "Law:" in cand["matching_text"]
    assert "regulation:4:paragraph:2" in cand["matching_text"]
    assert cand["presentation"]["locator_label"] == "regulation:4:paragraph:2"


def test_partially_resolved_includes_resolved_context_in_matching_text() -> None:
    host = _prop(
        prop_id="prop:host",
        proposition_text=(
            "The occupier must maintain a record calculated in accordance with regulation 4(3)."
        ),
        fragment_locator="regulation 33(1)",
        explicit_cross_reference_targets=["regulation 4(3)"],
    )
    incorporated = _prop(
        prop_id="prop:inc",
        proposition_text="The size calculation method is specified.",
        fragment_locator="regulation 4(3)",
        label="Holding size calculation",
    )
    payload = _candidates_for_props([host, incorporated])
    cand = next(c for c in payload["candidates"] if c["source_proposition_ids"] == ["prop:host"])
    assert cand["required_context"]
    assert "Context:" in cand["matching_text"]
    assert "regulation 4(3)" in cand["matching_text"]
    assert "Holding size calculation" in cand["matching_text"]
    assert "prop:" not in cand["matching_text"]


def test_context_dependent_guidance_usable_with_context() -> None:
    props = [
        _prop(
            prop_id="prop:ctx-dep",
            proposition_text="Must comply when factors apply.",
            extraction_debug_meta={"completeness_status": "context_dependent"},
        )
    ]
    cand = _candidates_for_props(props)["candidates"][0]
    assert cand["candidate_status"] == "usable_with_context"
    assert "context_dependent" in cand["risk_flags"]


def test_context_connector_excluded() -> None:
    props = [
        _prop(
            prop_id="prop:xref",
            proposition_text="Factors under regulation 4(2) apply.",
            fragment_locator="regulation 9(3)",
            legal_effect_type="cross_reference",
            proposition_tier="relationship_reference",
            is_compliance_relevant=False,
            explicit_cross_reference_targets=["regulation 4(2)"],
        ),
        _prop(
            prop_id="prop:host-4-2",
            proposition_text="Listed factors.",
            fragment_locator="regulation 4(2)",
        ),
    ]
    payload = _candidates_for_props(props)
    direct_ids = {c["source_proposition_ids"][0] for c in payload["candidates"]}
    assert "prop:xref" not in direct_ids
    assert payload["candidate_count"] == 1
    assert direct_ids == {"prop:host-4-2"}


def test_supporting_definition_excluded() -> None:
    props = [
        _prop(
            prop_id="prop:defn",
            proposition_text='"slurry" means excreta.',
            legal_effect_type="definition",
            proposition_tier="definitional_rule",
            is_compliance_relevant=False,
        )
    ]
    assert _candidates_for_props(props)["candidate_count"] == 0


def test_procedural_context_excluded() -> None:
    props = [
        _prop(
            prop_id="prop:cite",
            proposition_text="These Regulations may be cited as the X Regulations 2015.",
            legal_effect_type="citation",
            proposition_tier="instrument_metadata",
            is_compliance_relevant=False,
        )
    ]
    assert _candidates_for_props(props)["candidate_count"] == 0


def test_fragmentary_excluded_even_if_guidance_role() -> None:
    props = [
        _prop(
            prop_id="prop:frag",
            proposition_text="… incomplete …",
            extraction_debug_meta={"completeness_status": "fragmentary"},
        )
    ]
    law = _law_bundle(props)
    stmt = law["statements"][0]
    assert stmt["standalone_status"] == "fragmentary"
    assert _candidates_for_props(props)["candidate_count"] == 0


def test_fragmentary_definition_excluded_by_presentation_role() -> None:
    props = [
        _prop(
            prop_id="prop:frag-defn",
            proposition_text="Silage effluent means effluent from silage.",
            legal_effect_type="definition",
            proposition_tier="definitional_rule",
            is_compliance_relevant=False,
            extraction_debug_meta={"completeness_status": "fragmentary"},
        ),
        _prop(
            prop_id="prop:frag-guidance",
            proposition_text="Requirements must be satisfied in relation to a fuel oil storage area.",
            extraction_debug_meta={"completeness_status": "fragmentary"},
        ),
    ]
    law = _law_bundle(props)
    fragmentary = [s for s in law["statements"] if s["standalone_status"] == "fragmentary"]
    assert len(fragmentary) == 2
    by_prop = {s["source_proposition_ids"][0]: s for s in fragmentary}
    assert by_prop["prop:frag-defn"]["presentation_role"] == "supporting_definition"
    assert by_prop["prop:frag-guidance"]["presentation_role"] == "guidance_matching_candidate"

    payload = _candidates_for_props(props)
    assert payload["candidate_count"] == 0


def test_warnings_or_ambiguous_context_needs_review() -> None:
    hosts = [
        _prop(
            prop_id=f"prop:host-{n}",
            proposition_text=f"Host {n}.",
            fragment_locator="regulation 4",
        )
        for n in (1, 2)
    ]
    xref_host = _prop(
        prop_id="prop:guidance-ambig",
        proposition_text="See regulation 4 for factors.",
        fragment_locator="regulation 9(1)",
        explicit_cross_reference_targets=["regulation 4"],
    )
    props = [*hosts, xref_host]
    cand = _candidates_for_props(props)["candidates"][0]
    assert cand["source_proposition_ids"] == ["prop:guidance-ambig"]
    assert cand["candidate_status"] == "needs_review"
    assert "ambiguous_context" in cand["risk_flags"] or "has_warnings" in cand["risk_flags"]
    assert "ambiguous and may need review" in cand["matching_text"]
    assert "prop:" not in cand["matching_text"]


def test_matching_text_unresolved_context_hint() -> None:
    props = [
        _prop(
            prop_id="prop:host",
            proposition_text="Must update the record required by regulation 36(1)(b) of the old Regulations.",
            fragment_locator="schedule 4, paragraph 1",
            explicit_cross_reference_targets=["regulation 36(1)", "regulation 25b"],
        )
    ]
    cand = _candidates_for_props(props)["candidates"][0]
    assert "unresolved and may need review" in cand["matching_text"]
    assert "prop:" not in cand["matching_text"]


def test_motivating_xref_not_direct_candidate() -> None:
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
        ),
        _prop(
            prop_id="prop:host-reg9-2",
            proposition_text="Host factors scope for regulation 9(2).",
            fragment_locator="regulation 9(2)",
        ),
        _prop(
            prop_id="prop:reg4-2-host",
            proposition_text="Risk factors A and B are listed.",
            fragment_locator="regulation 4(2)",
        ),
    ]
    payload = _candidates_for_props(props)
    direct_prop_ids = {pid for c in payload["candidates"] for pid in c["source_proposition_ids"]}
    assert "prop:8b25ce8a1efdadf0" not in direct_prop_ids

    host_cand = next(
        c for c in payload["candidates"] if c["source_proposition_ids"] == ["prop:host-reg9-2"]
    )
    imported_cand = next(
        c for c in payload["candidates"] if c["source_proposition_ids"] == ["prop:reg4-2-host"]
    )

    assert "prop:8b25ce8a1efdadf0" in host_cand["supporting_proposition_ids"]
    assert "prop:8b25ce8a1efdadf0" in imported_cand["supporting_proposition_ids"]

    for cand in (host_cand, imported_cand):
        for ctx in cand["required_context"]:
            assert "prop:8b25ce8a1efdadf0" not in (ctx.get("proposition_ids") or [])

    host_wiring = host_cand["connector_context"]
    assert len(host_wiring) == 1
    assert host_wiring[0]["kind"] == "incorporates_context_from"
    assert host_wiring[0]["locator"] == "regulation 4(2)"
    assert host_wiring[0]["proposition_ids"] == ["prop:reg4-2-host"]
    assert host_wiring[0]["via_proposition_ids"] == ["prop:8b25ce8a1efdadf0"]

    imported_wiring = imported_cand["connector_context"]
    assert len(imported_wiring) == 1
    assert imported_wiring[0]["kind"] == "incorporated_elsewhere_by"
    assert imported_wiring[0]["locator"] == "regulation 9(3)"
    assert imported_wiring[0]["proposition_ids"] == ["prop:8b25ce8a1efdadf0"]
    assert imported_wiring[0]["target_locator"] == "regulation 9(2)"
    assert imported_wiring[0]["target_proposition_ids"] == ["prop:host-reg9-2"]

    assert "Connector context:" in host_cand["matching_text"]
    assert "incorporates context from regulation 4(2) via regulation 9(3)" in host_cand["matching_text"]
    assert "incorporated elsewhere by regulation 9(3)" in imported_cand["matching_text"]
    assert "prop:" not in host_cand["matching_text"]
    assert "prop:" not in imported_cand["matching_text"]


def test_matching_text_does_not_change_candidate_status_or_count() -> None:
    props = [
        _prop(
            prop_id="prop:ready",
            proposition_text="Must store slurry safely.",
            label="Safe slurry storage",
        ),
        _prop(
            prop_id="prop:host",
            proposition_text="Factor A and factor B must be considered.",
            fragment_locator="regulation 4(2)",
        ),
        _prop(
            prop_id="prop:xref-resolved",
            proposition_text="The factors under regulation 4(2) apply here.",
            fragment_locator="regulation 9(3)",
            legal_effect_type="cross_reference",
            proposition_tier="relationship_reference",
            is_compliance_relevant=False,
            explicit_cross_reference_targets=["regulation 4(2)"],
        ),
        *[
            _prop(
                prop_id=f"prop:host-{n}",
                proposition_text=f"Host {n}.",
                fragment_locator="regulation 4",
            )
            for n in (1, 2)
        ],
        _prop(
            prop_id="prop:guidance-ambig",
            proposition_text="See regulation 4 for factors.",
            fragment_locator="regulation 9(1)",
            explicit_cross_reference_targets=["regulation 4"],
        ),
    ]
    payload = _candidates_for_props(props)
    statuses = {c["source_proposition_ids"][0]: c["candidate_status"] for c in payload["candidates"]}
    assert statuses["prop:ready"] == "ready"
    assert statuses["prop:host"] == "usable_with_context"
    assert statuses["prop:guidance-ambig"] == "needs_review"
    assert all("matching_text" in c for c in payload["candidates"])
    assert payload["candidate_count"] == len(payload["candidates"])


def test_stable_candidate_ids() -> None:
    props = [
        _prop(
            prop_id="prop:stable",
            proposition_text="Must store slurry safely.",
        )
    ]
    law = _law_bundle(props)
    first = build_proposition_matcher_law_candidates(effective_law_statements=law, propositions=props)
    second = build_proposition_matcher_law_candidates(effective_law_statements=law, propositions=props)
    assert [c["id"] for c in first["candidates"]] == [c["id"] for c in second["candidates"]]
    assert all(c["id"].startswith("bcand:") for c in first["candidates"])


def test_wsi_candidate_territory_label_wales() -> None:
    props = [
        _prop(
            prop_id="prop:wales-obligation",
            proposition_text="The walls of any pipes must be impermeable.",
            fragment_locator="schedule 6, paragraph 2",
            label="Impermeability requirement: pipe walls",
        )
    ]
    payload = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "title": "The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021",
                    "citation": "WSI 2021/77",
                    "kind": "wsi",
                }
            ]
        },
    )
    cand = payload["candidates"][0]
    assert cand["territory_labels"] == ["Wales"]
    assert cand["jurisdiction_label"] == "Wales"
    assert cand["jurisdiction"] == "UK"
    assert "Territory: Wales." in cand["matching_text"]
    assert "jurisdiction UK" not in cand["matching_text"]


def test_ssi_candidate_territory_label_scotland() -> None:
    props = [
        _prop(
            prop_id="prop:scotland-obligation",
            proposition_text="A silo with retaining walls must not be overloaded.",
            fragment_locator="schedule 2, paragraph 7(b)",
            label="Silo maximum loading depth restriction",
        )
    ]
    payload = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "title": "The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003",
                    "citation": "SSI 2003/531",
                    "kind": "ssi",
                }
            ]
        },
    )
    cand = payload["candidates"][0]
    assert cand["territory_labels"] == ["Scotland"]
    assert cand["jurisdiction_label"] == "Scotland"
    assert "Territory: Scotland." in cand["matching_text"]


def test_uksi_england_only_candidate_territory_label_england() -> None:
    props = [
        _prop(
            prop_id="prop:england-obligation",
            proposition_text="The occupier must not cause pollution.",
            fragment_locator="regulation 2(1)",
            territorial_application=["England"],
        )
    ]
    payload = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "title": "The Nitrate Pollution Prevention Regulations 2015",
                    "citation": "UKSI 2015/668",
                    "kind": "uksi",
                }
            ]
        },
    )
    cand = payload["candidates"][0]
    assert cand["territory_labels"] == ["England"]
    assert cand["jurisdiction_label"] == "England"
    assert cand["territorial_application"] == ["England"]
    assert "Territory: England." in cand["matching_text"]


def test_uksi_england_from_source_scope_when_obligation_lacks_extent() -> None:
    props = [
        _prop(
            prop_id="prop:england-scope",
            proposition_text="These Regulations apply in relation to England only.",
            fragment_locator="regulation 1(3)",
            legal_effect_type="application_scope",
            proposition_tier="scope_rule",
            is_compliance_relevant=False,
            territorial_application=["England"],
            label="Application to England",
        ),
        _prop(
            prop_id="prop:facts-obligation",
            proposition_text=(
                "An occupier of a holding may, acting on written advice of a FACTS adviser, "
                "spread nitrogen on grass grown for minimum 16% protein content in amounts "
                "exceeding regulation 12 limits, subject to maximum caps."
            ),
            fragment_locator="regulation 13(2)",
            legal_effect_type="permission",
            label="Derogation for high-protein grass: FACTS-advised nitrogen spreading",
            territorial_application=[],
            extent=[],
        ),
    ]
    payload = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "title": "The Nitrate Pollution Prevention Regulations 2015",
                    "citation": "UKSI 2015/668",
                    "kind": "uksi",
                }
            ]
        },
    )
    cand = next(c for c in payload["candidates"] if c["source_proposition_ids"] == ["prop:facts-obligation"])
    assert cand["territory_labels"] == ["England"]
    assert cand["jurisdiction_label"] == "England"
    assert "Territory: England." in cand["matching_text"]


def test_explicit_extent_england_and_wales_label() -> None:
    props = [
        _prop(
            prop_id="prop:ew-obligation",
            proposition_text="The occupier must take all reasonable precautions.",
            fragment_locator="regulation 4",
            label="Reasonable precautions",
            extent=["England", "Wales"],
        ),
    ]
    payload = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "title": "The Reduction and Prevention of Agricultural Diffuse Pollution (England) Regulations 2018",
                    "citation": "UKSI 2018/151",
                    "kind": "uksi",
                }
            ]
        },
    )
    cand = next(c for c in payload["candidates"] if c["source_proposition_ids"] == ["prop:ew-obligation"])
    assert cand["territory_labels"] == ["England", "Wales"]
    assert cand["jurisdiction_label"] == "England and Wales"
    assert "Territory: England and Wales." in cand["matching_text"]


def test_unknown_territory_safe_fallback_without_jurisdiction_uk_in_matching_text() -> None:
    props = [
        _prop(
            prop_id="prop:unknown-geo",
            proposition_text="Must store slurry safely.",
            extent=[],
            label="Safe slurry storage",
        )
    ]
    props[0].pop("extent", None)
    cand = _candidates_for_props(props)["candidates"][0]
    assert cand["territory_labels"] == []
    assert cand["jurisdiction_label"] == ""
    assert cand["jurisdiction"] == "UK"
    assert "jurisdiction UK" not in cand["matching_text"]
    assert "jurisdiction uk" not in cand["matching_text"].lower()
    assert "Territory:" not in cand["matching_text"]


_BS_CORROSION_TEXT = (
    "The walls of any pipes must be protected against corrosion in accordance with "
    "paragraph 7 of the code of practice on buildings and structures for agriculture "
    "published by the British Standards Institution and numbered BS 5502: Part 50:1993."
)

_BS_CORROSION_PAREN_TEXT = (
    "The base and walls of the slurry storage tank, any effluent tank, channels and "
    "reception pit, and the walls of any pipes must be protected against corrosion in "
    "accordance with paragraph 7.2 of BS 5502 (Part 50: 1993)."
)

_BS_SILO_WALLS_PAREN_TEXT = (
    "Retaining walls of a silo must be capable of withstanding minimum wall loadings "
    "calculated on the assumptions and in the manner indicated by paragraph 15.6.1 to "
    "15.6.3 of BS 5502 (Part 22: 1993)."
)


def test_bs_paren_external_reference_usable_with_context_not_needs_review() -> None:
    props = [
        _prop(
            prop_id="prop:bs-paren-cand",
            proposition_text=_BS_CORROSION_PAREN_TEXT,
            fragment_locator="schedule 2, paragraph 3",
            label="Corrosion protection for slurry storage",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    cand = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "citation": "SSI 2003/531",
                    "title": "The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003",
                    "kind": "ssi",
                }
            ]
        },
    )["candidates"][0]
    assert cand["candidate_status"] in {"ready", "usable_with_context"}
    assert "external_reference" in cand["risk_flags"]
    assert "unresolved_context" not in cand["risk_flags"]
    assert "external standard reference: BS 5502 (Part 50: 1993), paragraph 7.2" in cand["matching_text"]
    assert "paragraph 7 is unresolved" not in cand["matching_text"]


def test_bs_paren_paragraph_range_not_unresolved_internal_context() -> None:
    props = [
        _prop(
            prop_id="prop:bs-silo-walls",
            proposition_text=_BS_SILO_WALLS_PAREN_TEXT,
            fragment_locator="schedule 1, paragraph 7(a)",
            label="Retaining wall strength requirement for silos",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    cand = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "citation": "SSI 2003/531",
                    "title": "The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003",
                    "kind": "ssi",
                }
            ]
        },
    )["candidates"][0]
    assert cand["candidate_status"] in {"ready", "usable_with_context"}
    assert "unresolved_context" not in cand["risk_flags"]
    assert "paragraph 15 is unresolved" not in cand["matching_text"]
    assert "external standard reference: BS 5502 (Part 22: 1993), paragraph 15.6.1 to 15.6.3" in cand[
        "matching_text"
    ]


def test_bs_external_reference_usable_with_context_not_needs_review() -> None:
    props = [
        _prop(
            prop_id="prop:bs-cand",
            proposition_text=_BS_CORROSION_TEXT,
            fragment_locator="schedule 6, paragraph 2",
            label="Impermeability requirement: pipe walls",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    cand = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "citation": "WSI 2021/77",
                    "title": "The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021",
                    "kind": "wsi",
                }
            ]
        },
    )["candidates"][0]
    assert cand["candidate_status"] in {"ready", "usable_with_context"}
    assert "external_reference" in cand["risk_flags"]
    assert "unresolved_context" not in cand["risk_flags"]
    assert "external standard reference: BS 5502: Part 50:1993, paragraph 7" in cand["matching_text"]
    assert "paragraph 7 is unresolved" not in cand["matching_text"]


def test_rb209_external_guidance_matching_text() -> None:
    props = [
        _prop(
            prop_id="prop:rb209-cand",
            proposition_text=(
                "The occupier must establish nitrogen availability by reference to the "
                "values given in the Nutrient Management Guide (RB209), or by sampling."
            ),
            fragment_locator="regulation 9(3)",
            label="Organic manure nitrogen availability",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    cand = _candidates_for_props(props)["candidates"][0]
    assert "external guidance reference: Nutrient Management Guide (RB209)" in cand["matching_text"]
    assert "external_reference" in cand["risk_flags"]
    assert cand["candidate_status"] in {"ready", "usable_with_context"}


def test_malformed_external_reference_may_need_review() -> None:
    props = [
        _prop(
            prop_id="prop:bad-bs",
            proposition_text="Must comply with BS 5502: Part in accordance with industry practice.",
            fragment_locator="schedule 1, paragraph 1",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    cand = _candidates_for_props(props)["candidates"][0]
    assert cand["candidate_status"] == "needs_review"
    assert "malformed_external_reference" in cand["risk_flags"]


def test_territory_labels_do_not_change_candidate_status_or_count() -> None:
    props = [
        _prop(
            prop_id="prop:wales-ready",
            proposition_text="No person may spread manufactured nitrogen fertiliser on grassland.",
            fragment_locator="regulation 22(1)(a)",
            label="Closed period prohibition",
        ),
        _prop(
            prop_id="prop:host",
            proposition_text="Factor A and factor B must be considered.",
            fragment_locator="regulation 4(2)",
        ),
        _prop(
            prop_id="prop:xref-resolved",
            proposition_text="The factors under regulation 4(2) apply here.",
            fragment_locator="regulation 9(3)",
            legal_effect_type="cross_reference",
            proposition_tier="relationship_reference",
            is_compliance_relevant=False,
            explicit_cross_reference_targets=["regulation 4(2)"],
        ),
    ]
    payload = _candidates_for_props(
        props,
        source_inventory={
            "rows": [
                {
                    "source_record_id": SOURCE,
                    "citation": "WSI 2021/77",
                    "title": "The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021",
                    "kind": "wsi",
                }
            ]
        },
    )
    statuses = {c["source_proposition_ids"][0]: c["candidate_status"] for c in payload["candidates"]}
    assert statuses["prop:wales-ready"] == "ready"
    assert statuses["prop:host"] == "usable_with_context"
    assert payload["candidate_count"] == 2


def test_normalize_locator_for_dedupe_schedule_casing() -> None:
    assert _normalize_locator_for_dedupe("Schedule 5, paragraph 3(a)") == _normalize_locator_for_dedupe(
        "schedule 5, paragraph 3(a)"
    )


def test_same_source_same_locator_and_statement_soft_duplicate_group() -> None:
    text = (
        "The effluent tank must have a capacity of at least 45 litres "
        "for each square metre of the area it serves."
    )
    props = [
        _prop(
            prop_id="prop:dup-a",
            proposition_text=text,
            fragment_locator="Schedule 5, paragraph 3(a)",
            source_fragment_id="frag-dup-a",
            label="Effluent tank capacity",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
        _prop(
            prop_id="prop:dup-b",
            proposition_text=text,
            fragment_locator="schedule 5, paragraph 3(a)",
            source_fragment_id="frag-dup-b",
            label="Effluent tank capacity",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
    ]
    payload = _candidates_for_props(props)
    assert payload["candidate_count"] == 2
    assert payload["duplicate_summary"]["same_source_duplicate_groups"] == 1
    assert payload["duplicate_summary"]["same_source_duplicate_candidates"] == 2
    canonical = [c for c in payload["candidates"] if c["dedupe"]["is_canonical"]]
    non_canonical = [c for c in payload["candidates"] if not c["dedupe"]["is_canonical"]]
    assert len(canonical) == 1
    assert len(non_canonical) == 1
    assert non_canonical[0]["dedupe"]["canonical_candidate_id"] == canonical[0]["id"]
    assert canonical[0]["dedupe"]["duplicate_group_id"] == non_canonical[0]["dedupe"]["duplicate_group_id"]
    assert canonical[0]["dedupe"]["duplicate_count"] == 2
    assert canonical[0]["dedupe"]["dedupe_key"] == non_canonical[0]["dedupe"]["dedupe_key"]


def test_same_statement_different_source_not_duplicate_group() -> None:
    text = "The walls of any pipes must be impermeable."
    props = [
        _prop(
            prop_id="prop:src-a",
            proposition_text=text,
            fragment_locator="schedule 6, paragraph 2",
            source_fragment_id="frag-a",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
        {
            **_prop(
                prop_id="prop:src-b",
                proposition_text=text,
                fragment_locator="schedule 6, paragraph 2",
                source_fragment_id="frag-b",
                extraction_debug_meta={"completeness_status": "complete"},
            ),
            "source_record_id": SOURCE_B,
        },
    ]
    payload = _candidates_for_props(props)
    assert payload["candidate_count"] == 2
    assert payload["duplicate_summary"]["same_source_duplicate_groups"] == 0
    keys = [_candidate_dedupe_key(c) for c in payload["candidates"]]
    assert len(keys) == 2 and all(keys)
    assert keys[0] != keys[1]


def test_same_source_different_locator_not_duplicate_group() -> None:
    props = [
        _prop(
            prop_id="prop:loc-a",
            proposition_text="The effluent tank must have sufficient capacity.",
            fragment_locator="Schedule 5, paragraph 3(a)",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
        _prop(
            prop_id="prop:loc-b",
            proposition_text="The effluent tank must have sufficient capacity.",
            fragment_locator="Schedule 5, paragraph 3(b)",
            source_fragment_id="frag-loc-b",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
    ]
    payload = _candidates_for_props(props)
    assert payload["duplicate_summary"]["same_source_duplicate_groups"] == 0
    assert all(c["dedupe"]["duplicate_count"] == 1 for c in payload["candidates"])


def test_duplicate_metadata_and_canonical_id_stable_across_runs() -> None:
    text = "Storage must meet the minimum capacity requirement."
    props = [
        _prop(
            prop_id="prop:stable-a",
            proposition_text=text,
            fragment_locator="Schedule 5, paragraph 3(a)",
            source_fragment_id="frag-sa",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
        _prop(
            prop_id="prop:stable-b",
            proposition_text=text,
            fragment_locator="schedule 5, paragraph 3(a)",
            source_fragment_id="frag-sb",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
    ]
    law = _law_bundle(props)
    first = build_proposition_matcher_law_candidates(effective_law_statements=law, propositions=props)
    second = build_proposition_matcher_law_candidates(effective_law_statements=law, propositions=props)
    first_canonical = next(c for c in first["candidates"] if c["dedupe"]["is_canonical"])
    second_canonical = next(c for c in second["candidates"] if c["dedupe"]["is_canonical"])
    assert first_canonical["id"] == second_canonical["id"]
    assert first_canonical["dedupe"]["duplicate_group_id"] == second_canonical["dedupe"]["duplicate_group_id"]


def test_canonical_prefers_ready_over_needs_review_in_duplicate_group() -> None:
    text = "The tank must meet capacity requirements."
    props = [
        _prop(
            prop_id="prop:ready-dup",
            proposition_text=text,
            fragment_locator="Schedule 5, paragraph 3(a)",
            source_fragment_id="frag-ready",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
        _prop(
            prop_id="prop:review-dup",
            proposition_text=text,
            fragment_locator="schedule 5, paragraph 3(a)",
            source_fragment_id="frag-review",
            explicit_cross_reference_targets=["regulation 99"],
            extraction_debug_meta={"completeness_status": "complete"},
        ),
    ]
    payload = _candidates_for_props(props)
    canonical = next(c for c in payload["candidates"] if c["dedupe"]["is_canonical"])
    assert canonical["source_proposition_ids"] == ["prop:ready-dup"]
    assert canonical["candidate_status"] == "ready"


def test_soft_dedupe_preserves_candidate_count() -> None:
    text = "The effluent tank must have a capacity of at least 45 litres."
    props = [
        _prop(
            prop_id=f"prop:count-{n}",
            proposition_text=text,
            fragment_locator="Schedule 5, paragraph 3(a)" if n == 0 else "schedule 5, paragraph 3(a)",
            source_fragment_id=f"frag-count-{n}",
            extraction_debug_meta={"completeness_status": "complete"},
        )
        for n in range(2)
    ]
    payload = _candidates_for_props(props)
    assert payload["candidate_count"] == len(payload["candidates"]) == 2


def test_attach_effective_law_artifacts_includes_beatrice_candidates() -> None:
    bundle = {
        "run": {"id": "run-001"},
        "propositions": [
            _prop(
                prop_id="prop:bundle-1",
                proposition_text="Must store slurry safely.",
            )
        ],
        "source_inventory": {"rows": [{"source_record_id": SOURCE, "title": "Test Regs"}]},
    }
    attach_effective_law_artifacts(bundle)
    assert "proposition_matcher_law_candidates" in bundle
    assert bundle["proposition_matcher_law_candidates"]["schema_version"] == "1"
    assert bundle["proposition_matcher_law_candidates"]["candidate_count"] >= 1


def test_canonical_provision_path_unifies_ssafo_format_variants() -> None:
    cases = [
        ("regulation:5:paragraph:1(a)", "regulation:5:1:a"),
        ("regulation:5:paragraph:1:subparagraph:a", "regulation:5:1:a"),
        ("regulation:5:paragraph:1:list:1-a", "regulation:5:1:a"),
        ("regulation:6:paragraph:1:(c)(i)", "regulation:6:1:c:i"),
        ("regulation:6:paragraph:1:subparagraph:c:item:i", "regulation:6:1:c:i"),
        ("regulation:7:paragraph:5:list:5-b", "regulation:7:5:b"),
        ("schedule:3:paragraph:2:list:2-b-ii", "schedule:3:2:b:ii"),
        ("schedule:3:paragraph:2(b)(i)-(ii)", "schedule:3:2:b:i-ii"),
        ("Schedule 5, paragraph 3(a)", "schedule:5:3:a"),
        ("regulation 22(1)(a)", "regulation:22:1:a"),
    ]
    for locator, expected in cases:
        assert canonical_provision_path(locator) == expected, locator
    assert preferred_locator_label("regulation:5:1:a") == (
        "regulation:5:paragraph:1:subparagraph:a"
    )
    assert preferred_locator_label("regulation:6:1:c:i") == (
        "regulation:6:paragraph:1:subparagraph:c:item:i"
    )
    assert _normalize_locator_for_dedupe("regulation:5:paragraph:1(a)") == (
        _normalize_locator_for_dedupe("regulation:5:paragraph:1:subparagraph:a")
    )


def test_exported_locator_label_uses_preferred_display_form() -> None:
    props = [
        _prop(
            prop_id="prop:oil-a",
            proposition_text="Fuel oil on farms must be stored in a fuel storage tank.",
            fragment_locator="regulation:5:paragraph:1(a)",
            label="Fuel oil storage",
            extraction_debug_meta={"completeness_status": "complete"},
        )
    ]
    cand = _candidates_for_props(props)["candidates"][0]
    assert cand["presentation"]["locator_label"] == (
        "regulation:5:paragraph:1:subparagraph:a"
    )


def test_chapeau_limb_altitude_collapse_keeps_limb_only() -> None:
    props = [
        _prop(
            prop_id="prop:chapeau",
            proposition_text=(
                "Subject to paragraph (2), a person who has custody or control of fuel oil "
                "on a farm must ensure that it is stored in a fuel storage tank within a "
                "storage area or facility that satisfies the requirements of Schedule 3."
            ),
            fragment_locator="regulation:5:paragraph:1(a)",
            label="Fuel oil chapeau",
            source_fragment_id="frag-chapeau",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
        _prop(
            prop_id="prop:limb",
            proposition_text=(
                "Fuel oil on farms must be stored in a fuel storage tank within a storage "
                "area or facility that satisfies the requirements of Schedule 3."
            ),
            fragment_locator="regulation:5:paragraph:1:subparagraph:a",
            label="Fuel oil limb",
            source_fragment_id="frag-limb",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
    ]
    payload = _candidates_for_props(props)
    assert payload["candidate_count"] == 1
    assert payload["altitude_summary"]["chapeau_suppressed_count"] == 1
    assert payload["altitude_summary"]["groups_collapsed"] == 1
    cand = payload["candidates"][0]
    assert cand["source_proposition_ids"] == ["prop:limb"]
    assert "Fuel oil on farms must be stored" in cand["statement_text"]
    assert cand["presentation"]["locator_label"] == (
        "regulation:5:paragraph:1:subparagraph:a"
    )
    chapeaus = [c for c in cand["required_context"] if c.get("kind") == "chapeau"]
    assert len(chapeaus) == 1
    assert "Subject to paragraph" in chapeaus[0]["statement_text"]
    assert "chapeau" in cand["matching_text"].lower()


def test_list_form_suppressed_when_structured_sibling_exists() -> None:
    props = [
        _prop(
            prop_id="prop:list-form",
            proposition_text=(
                "Subject to paragraph (2), a person who has custody or control of fuel oil "
                "on a farm must ensure that it is stored— in drums within such a storage area; or"
            ),
            fragment_locator="regulation:5:paragraph:1:list:1-b",
            label="Fuel oil list",
            source_fragment_id="frag-list",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
        _prop(
            prop_id="prop:structured",
            proposition_text="Fuel oil on farms may be stored in drums within a designated storage area.",
            fragment_locator="regulation:5:paragraph:1:subparagraph:b",
            label="Fuel oil structured",
            source_fragment_id="frag-structured",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
    ]
    payload = _candidates_for_props(props)
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["source_proposition_ids"] == ["prop:structured"]
    assert payload["altitude_summary"]["chapeau_suppressed_count"] == 1


def test_different_provisions_do_not_collapse() -> None:
    props = [
        _prop(
            prop_id="prop:a",
            proposition_text="Fuel oil on farms must be stored in a fuel storage tank.",
            fragment_locator="regulation:5:paragraph:1:subparagraph:a",
            source_fragment_id="frag-a",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
        _prop(
            prop_id="prop:b",
            proposition_text="Fuel oil on farms may be stored in drums within a designated storage area.",
            fragment_locator="regulation:5:paragraph:1:subparagraph:b",
            source_fragment_id="frag-b",
            extraction_debug_meta={"completeness_status": "complete"},
        ),
    ]
    payload = _candidates_for_props(props)
    assert payload["candidate_count"] == 2
    assert payload["altitude_summary"]["chapeau_suppressed_count"] == 0
    assert payload["duplicate_summary"]["same_source_duplicate_groups"] == 0
