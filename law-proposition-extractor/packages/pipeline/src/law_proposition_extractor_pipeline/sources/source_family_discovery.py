"""Discover related legal instruments for a registry-backed source (fixture-driven in tests)."""

from __future__ import annotations

from typing import Any, Callable

from law_proposition_extractor_domain.source_family import SourceFamilyCandidate


def _norm_asid(value: str) -> str:
    return value.strip().strip("/").lower()


def _build_uk_retained() -> SourceFamilyCandidate:
    return SourceFamilyCandidate(
        id="sfc-2016-429-uk-retained",
        candidate_source_id="uksi/example/eu-exit",
        title="Retained assimilated provisions (conceptual grouping)",
        citation="UK retained EU-derived rules (conceptual grouping)",
        source_role="retained_version",
        relationship_to_target="contextual",
        inclusion_status="required_for_scope",
        confidence="medium",
        reason="Domestic assimilated regime may supersede literal EU text interpretation",
        evidence=["Fixture: juxtapose with EU base where UK applicability holds"],
        metadata={
            "fixture": True,
            "jurisdiction_hint": "UK",
            "equine_law_discovery": {"family": "ahl_core", "lineage": "retained_baseline_uk"},
        },
    )


def _eli_reg_impl(year: int, seq: int) -> str:
    return f"http://data.europa.eu/eli/reg_impl/{year}/{seq}/oj"


def _eli_reg_del(year: int, seq: int) -> str:
    return f"http://data.europa.eu/eli/reg_del/{year}/{seq}/oj"


def _eur_lex_uri(celex: str) -> str:
    safe = celex.strip()
    return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{safe}"


def _equine_law_discovery_extension(
    *,
    target_citation: str = "Regulation (EU) 2016/429",
) -> list[SourceFamilyCandidate]:
    """Concrete EU/UK-aligned candidates around equine passports, AHL detail acts, movement — discovery only."""

    eur_evidence = (
        "Public EUR-Lex CELEX locator; consolidate before treating revision letters as operative alone."
    )
    uk_evidence = "legislation.gov.uk retained EU routing where published (/eur/year/seq); verify assimilated headings."

    return [
        SourceFamilyCandidate(
            id="sfc-2015-262-eu-implementing",
            candidate_source_id="eur/2015/262",
            target_citation=target_citation,
            title=(
                "Commission Implementing Regulation (EU) 2015/262 (rules pursuant to Directive 90/427/EEC "
                "for identification and registration — equine passports)"
            ),
            citation="Commission Implementing Regulation (EU) 2015/262",
            celex="32015R0262",
            eli=_eli_reg_impl(2015, 262),
            url=_eur_lex_uri("32015R0262"),
            source_role="implementing_act",
            relationship_to_target="contextual",
            inclusion_status="candidate_needs_review",
            confidence="high",
            reason=(
                "Equine passport and identification rules historically operative pre-AHL; retained-law baseline "
                "for passport discipline before current AHL delegated/implementing detail (not auto-ingested)."
            ),
            evidence=[eur_evidence, "OJ linkage via CELEX 32015R0262"],
            metadata={
                "equine_law_discovery": {
                    "family": "equine_passport_identification",
                    "lineage": "retained_historical_baseline",
                    "uk_legislation_url": "https://www.legislation.gov.uk/eur/2015/262",
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2015-262-uk-retained",
            target_citation=target_citation,
            title="UK retained / assimilated presentation — Commission Implementing Regulation (EU) 2015/262",
            citation="Retained / assimilated 2015/262 (UK — verify series heading)",
            celex="32015R0262",
            eli=_eli_reg_impl(2015, 262),
            url="https://www.legislation.gov.uk/eur/2015/262",
            source_role="retained_version",
            relationship_to_target="contextual",
            inclusion_status="candidate_needs_review",
            confidence="medium",
            reason="Domestic counterpart for historical passport material; reconcile with assimilated numbering.",
            evidence=[uk_evidence],
            metadata={
                "equine_law_discovery": {
                    "family": "equine_passport_identification",
                    "lineage": "retained_historical_baseline",
                    "paired_eu_celex": "32015R0262",
                    "eur_lex_url": _eur_lex_uri("32015R0262"),
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2015-262-corr-02",
            target_citation=target_citation,
            title="Corrigendum — Commission Implementing Regulation (EU) 2015/262 (revision 02)",
            citation="Corr. OJ notation linked to CELEX 32015R0262R(02)",
            celex="32015R0262R(02)",
            eli=_eli_reg_impl(2015, 262),
            url=_eur_lex_uri("32015R0262R(02)"),
            source_role="corrigendum",
            relationship_to_target="corrects",
            inclusion_status="optional_context",
            confidence="medium",
            reason="Corrective text for the equine passport regime; ingest explicitly if provisions you rely on are touched.",
            evidence=[eur_evidence, "CELEX convention 32015R0262R(02)"],
            metadata={
                "equine_law_discovery": {
                    "family": "equine_passport_identification",
                    "lineage": "corrigendum_only",
                    "parent_candidate_id": "sfc-2015-262-eu-implementing",
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2015-262-annex-I",
            target_citation=target_citation,
            title="Commission Implementing Regulation (EU) 2015/262 — Annex I (model passport / particulars)",
            citation="2015/262 Annex I (verify Annex letter in consolidated OJ/EUR-Lex)",
            celex="32015R0262",
            url=_eur_lex_uri("32015R0262"),
            source_role="annex",
            relationship_to_target="supplements",
            inclusion_status="candidate_needs_review",
            confidence="medium",
            reason="Annex substance is operative but must be harvested as explicit fragments, not hidden in body-only captures.",
            evidence=["EUR-Lex tables of Annexes under CELEX 32015R0262"],
            metadata={
                "equine_law_discovery": {
                    "family": "equine_passport_identification",
                    "lineage": "annex_fragment",
                    "parent_candidate_id": "sfc-2015-262-eu-implementing",
                    "fragment_hint": "annex_I_verify_label",
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2015-262-annex-II",
            target_citation=target_citation,
            title="Commission Implementing Regulation (EU) 2015/262 — Annex II (supplementary equine passport data)",
            citation="2015/262 Annex II (verify Annex letter in consolidated OJ/EUR-Lex)",
            celex="32015R0262",
            url=_eur_lex_uri("32015R0262"),
            source_role="annex",
            relationship_to_target="supplements",
            inclusion_status="candidate_needs_review",
            confidence="medium",
            reason="Separate annex ingest preferred for traceability versus parent recitals.",
            evidence=["EUR-Lex annex schedule for CELEX 32015R0262"],
            metadata={
                "equine_law_discovery": {
                    "family": "equine_passport_identification",
                    "lineage": "annex_fragment",
                    "parent_candidate_id": "sfc-2015-262-eu-implementing",
                    "fragment_hint": "annex_II_verify_label",
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2019-2035-delegated",
            candidate_source_id="eur/2019/2035",
            target_citation=target_citation,
            title=(
                "Commission Delegated Regulation (EU) 2019/2035 supplementing Regulation (EU) 2016/429 "
                "as regards animal health regulatory requirements"
            ),
            citation="Delegated Regulation (EU) 2019/2035",
            celex="32019R2035",
            eli=_eli_reg_del(2019, 2035),
            url=_eur_lex_uri("32019R2035"),
            source_role="delegated_act",
            relationship_to_target="supplements",
            inclusion_status="required_for_scope",
            confidence="high",
            reason="Downstream EU detail under the Animal Health Law for species-specific regimes including equine ID/traceability linkage.",
            evidence=[eur_evidence, _eur_lex_uri("32019R2035")],
            metadata={
                "equine_law_discovery": {
                    "family": "equine_passport_identification",
                    "lineage": "current_operative_eu",
                    "relation_note": "AHL delegated tier for regulatory requirements touching identification topics",
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2021-963-implementing",
            candidate_source_id="eur/2021/963",
            target_citation=target_citation,
            title=(
                "Commission Implementing Regulation (EU) 2021/963 laying down rules for the application of "
                "Regulation (EU) 2016/429 as regards model identification documents"
            ),
            citation="Commission Implementing Regulation (EU) 2021/963",
            celex="32021R0963",
            eli=_eli_reg_impl(2021, 963),
            url=_eur_lex_uri("32021R0963"),
            source_role="implementing_act",
            relationship_to_target="implements",
            inclusion_status="required_for_scope",
            confidence="high",
            reason="Defines model identification documents referenced by modern AHL structure; pairs with delegated 2019/2035.",
            evidence=[eur_evidence, _eur_lex_uri("32021R0963")],
            metadata={
                "equine_law_discovery": {
                    "family": "equine_passport_identification",
                    "lineage": "current_operative_eu",
                    "paired_delegated_celex": "32019R2035",
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2020-688-delegated",
            candidate_source_id="eur/2020/688",
            target_citation=target_citation,
            title=(
                "Commission Delegated Regulation (EU) 2020/688 supplementing Regulation (EU) 2016/429 "
                "as regards animal health certificates for movements within the Union"
            ),
            citation="Delegated Regulation (EU) 2020/688",
            celex="32020R0688",
            eli=_eli_reg_del(2020, 688),
            url=_eur_lex_uri("32020R0688"),
            source_role="delegated_act",
            relationship_to_target="supplements",
            inclusion_status="required_for_scope",
            confidence="high",
            reason="Certificates for intra-Union movement under AHL — review equine-relevant schedules before extraction claims.",
            evidence=[eur_evidence, _eur_lex_uri("32020R0688")],
            metadata={
                "equine_law_discovery": {
                    "family": "movement_entry_certification",
                    "lineage": "current_operative_eu",
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2020-692-delegated",
            candidate_source_id="eur/2020/692",
            target_citation=target_citation,
            title=(
                "Commission Delegated Regulation (EU) 2020/692 supplementing Regulation (EU) 2016/429 "
                "as regards entry into the Union of consignments of animals and goods"
            ),
            citation="Delegated Regulation (EU) 2020/692",
            celex="32020R0692",
            eli=_eli_reg_del(2020, 692),
            url=_eur_lex_uri("32020R0692"),
            source_role="delegated_act",
            relationship_to_target="supplements",
            inclusion_status="required_for_scope",
            confidence="high",
            reason="Third-country entry certificates and lists overlap movement control for equidae imports — scope-check before ingestion.",
            evidence=[eur_evidence, _eur_lex_uri("32020R0692")],
            metadata={
                "equine_law_discovery": {
                    "family": "movement_entry_certification",
                    "lineage": "current_operative_eu",
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-movement-certificate-models",
            target_citation=target_citation,
            title="Official model certificates / lists under 2020/688 and 2020/692 (discover via annex schedules)",
            citation="Annex-hosted certificate models — register after locating species rows",
            source_role="certificate_model",
            relationship_to_target="implements",
            inclusion_status="candidate_needs_review",
            confidence="low",
            reason="Models and species rows live in annexes and implementing acts — not auto-registered.",
            evidence=["Derived index: enumerate annex tables after instrument registration"],
            metadata={
                "equine_law_discovery": {
                    "family": "movement_entry_certification",
                    "lineage": "certificate_or_list_fragment",
                    "authority_source_placeholder": True,
                },
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-uk-domestic-equine-id",
            target_citation=target_citation,
            title=(
                "UK domestic equine passport / identification rules — locate a published national instrument "
                "(not presumed operative via this placeholder)"
            ),
            citation="UK domestic secondary legislation (conceptual locator)",
            source_role="implementing_act",
            relationship_to_target="contextual",
            inclusion_status="candidate_needs_review",
            confidence="low",
            reason="Operational UK domestic layer post-assimilation; locate published instrument IDs before registering.",
            evidence=["Search legislation.gov.uk for equine passport / equine identification commencing points"],
            metadata={
                "equine_law_discovery": {"family": "uk_context", "lineage": "pending_candidate"},
                "authority_source_placeholder": True,
                "fixture": False,
            },
        ),
        SourceFamilyCandidate(
            id="sfc-defra-equine-guidance",
            target_citation=target_citation,
            title="Official UK guidance — equine passports / identification (context only)",
            citation="Guidance portals (conceptual locator)",
            source_role="guidance",
            relationship_to_target="explains",
            inclusion_status="optional_context",
            confidence="low",
            reason="Operational guidance lacks legal effect unless incorporated; label separately from operative sources.",
            evidence=["Verify publisher and revision date against registered legal sources"],
            metadata={
                "equine_law_discovery": {"family": "uk_context", "lineage": "guidance_only"},
                "authority_source_placeholder": True,
                "fixture": False,
            },
        ),
    ]


def _regulation_fixture_rows() -> list[SourceFamilyCandidate]:
    return [
        SourceFamilyCandidate(
            id="sfc-2016-429-base",
            candidate_source_id="eur/2016/429",
            target_citation="Regulation (EU) 2016/429",
            title="Regulation (EU) 2016/429 on animal health (Animal Health Law)",
            citation="EUR 2016/429",
            celex="32016R0429",
            url="https://www.legislation.gov.uk/eur/2016/429",
            source_role="base_act",
            relationship_to_target="is_target",
            inclusion_status="required_core",
            confidence="high",
            reason="Canonical EU base act for the animal health regime",
            evidence=["Fixture: legislation.gov.uk eur/2016/429 path"],
            metadata={
                "fixture": True,
                "equine_law_discovery": {"family": "ahl_core", "lineage": "current_operative_eu"},
                "eur_lex_url": _eur_lex_uri("32016R0429"),
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2016-429-consolidated",
            title="EUR-Lex consolidated text (conceptual grouping)",
            celex="32016R0429",
            source_role="consolidated_text",
            relationship_to_target="supplements",
            inclusion_status="required_core",
            confidence="medium",
            reason="Consolidated compilations supersede fragmented versions for reading order",
            evidence=["Fixture anchor: CELEX-based grouping"],
            metadata={
                "fixture": True,
                "equine_law_discovery": {"family": "ahl_core", "lineage": "current_operative_eu"},
                "eur_lex_url": _eur_lex_uri("32016R0429"),
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2016-429-corr-1",
            title="Corrigendum affecting Article references (illustrative)",
            source_role="corrigendum",
            relationship_to_target="corrects",
            inclusion_status="optional_context",
            confidence="medium",
            reason="Corrigenda correct obvious errors without changing policy intent",
            evidence=["Fixture: EU Official Journal linkage model"],
            metadata={
                "fixture": True,
                "equine_law_discovery": {"family": "ahl_core", "lineage": "corrigendum_only"},
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2016-429-amd-deleg",
            candidate_source_id="eur/2020/example",
            title="Delegated act under Article 109 (conceptual grouping)",
            source_role="delegated_act",
            relationship_to_target="supplements",
            inclusion_status="optional_context",
            confidence="low",
            reason="Delegated acts fill detail left to the Commission by the base act",
            evidence=["Fixture-only identifier; validate before treating as operative law"],
            metadata={
                "fixture": True,
                "authority_source_placeholder": True,
                "equine_law_discovery": {"family": "ahl_core", "lineage": "pending_candidate"},
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2016-429-impl",
            candidate_source_id="eur/2021/example-impl",
            title="Implementing regulation (conditions / forms) (conceptual grouping)",
            source_role="implementing_act",
            relationship_to_target="implements",
            inclusion_status="optional_context",
            confidence="low",
            reason="Implementing acts specify uniform conditions for Union law application",
            evidence=["Fixture-only identifier; verify against published OJ entry"],
            metadata={
                "fixture": True,
                "authority_source_placeholder": True,
                "equine_law_discovery": {"family": "ahl_core", "lineage": "pending_candidate"},
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2016-429-annex",
            title="Annex XIV (model certificates) excerpt (fixture)",
            source_role="annex",
            relationship_to_target="supplements",
            inclusion_status="optional_context",
            confidence="medium",
            reason="Annexes carry mandatory templates referred to by articles",
            evidence=["Fixture grouping only—not an extracted annex body"],
            metadata={
                "fixture": True,
                "equine_law_discovery": {"family": "ahl_core", "lineage": "annex_fragment"},
            },
        ),
        SourceFamilyCandidate(
            id="sfc-2016-429-guid",
            title="Commission guidance interpreting movement rules (fixture)",
            source_role="guidance",
            relationship_to_target="explains",
            inclusion_status="candidate_needs_review",
            confidence="low",
            reason="Guidance informs practice but does not replace published legal text",
            evidence=["Explicitly advisory; verify against binding instruments"],
            metadata={
                "fixture": True,
                "equine_law_discovery": {"family": "ahl_core", "lineage": "guidance_only"},
            },
        ),
        _build_uk_retained(),
    ]


def default_discover(registry_entry: dict[str, Any]) -> list[SourceFamilyCandidate]:
    """Return fixture family members when the mapped instrument is Regulation (EU) 2016/429."""

    ref = registry_entry.get("reference") if isinstance(registry_entry.get("reference"), dict) else {}
    asid = _norm_asid(str(ref.get("authority_source_id") or ""))

    if asid == "eur/2016/429":
        return _regulation_fixture_rows() + _equine_law_discovery_extension()
    return []


def discover_related_for_registry_entry(
    registry_entry: dict[str, Any],
    *,
    discoverer: Callable[[dict[str, Any]], list[SourceFamilyCandidate]] | None = None,
) -> dict[str, Any]:
    """Produce related-instrument candidates; never ingest sources implicitly."""

    fn = discoverer or default_discover
    candidates = fn(registry_entry)
    ref = registry_entry.get("reference") if isinstance(registry_entry.get("reference"), dict) else {}
    return {
        "registry_id": str(registry_entry.get("registry_id") or ""),
        "target_authority_source_id": str(ref.get("authority_source_id") or ""),
        "candidates": [c.model_dump(mode="json") for c in candidates],
    }


def candidates_for_included_ids(
    all_candidates: list[dict[str, Any]],
    included_ids: list[str],
) -> list[SourceFamilyCandidate]:
    want = {str(i).strip() for i in included_ids if str(i).strip()}
    merged: dict[str, dict[str, Any]] = {}
    for row in all_candidates:
        if not isinstance(row, dict):
            continue
        cid = row.get("id")
        if cid is None:
            continue
        if str(cid) in want:
            merged[str(cid)] = row
    return [SourceFamilyCandidate.model_validate(item) for item in merged.values()]
