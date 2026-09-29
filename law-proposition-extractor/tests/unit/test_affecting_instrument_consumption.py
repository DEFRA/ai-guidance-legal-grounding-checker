"""Tests for affecting-instrument independent-consumption matching (20-BR1)."""

from __future__ import annotations

from law_proposition_extractor_domain import SourceLegalEffect
from law_proposition_extractor_pipeline.affecting_instrument_consumption import (
    build_run_source_inventory,
    normalize_celex_identifier,
    normalize_legislation_gov_uk_instrument_identity,
    parse_structured_citation_identity,
    reconcile_affecting_instrument_consumption,
    reconcile_source_legal_effects_artifact,
)
from law_proposition_extractor_pipeline.source_legal_effects import attach_source_legal_effects


def _effect(**kwargs):
    base = {
        "id": "sourceeffect:demo",
        "source_record_id": "src-eur-2009-1224",
        "source_snapshot_id": "snap-eur-2009-1224",
        "annotation_id": "c000004",
        "annotation_label": "F2",
        "independent_consumption_status": "not_assessed",
    }
    base.update(kwargs)
    return base


def _record(
    *,
    record_id: str,
    asid: str,
    url: str | None = None,
    title: str = "",
    citation: str = "",
    celex: str | None = None,
):
    meta: dict = {"authority_source_id": asid}
    if celex:
        meta["celex"] = celex
    return {
        "id": record_id,
        "title": title or asid,
        "citation": citation or asid.upper().replace("/", " "),
        "jurisdiction": "UK",
        "kind": "instrument",
        "source_url": url or f"https://www.legislation.gov.uk/{asid}/data.xml",
        "metadata": meta,
        "authority_source_id": asid,
    }


def _snap(*, snap_id: str, record_id: str, asid: str | None = None):
    meta: dict = {}
    if asid:
        meta["authority_source_id"] = asid
    return {
        "id": snap_id,
        "source_record_id": record_id,
        "version_id": "v1",
        "authoritative_text": "text",
        "provenance": "test",
        "retrieved_at": "2026-07-14T00:00:00Z",
        "content_hash": "abc",
        "metadata": meta,
    }


class TestIdentityNormalization:
    def test_instrument_and_data_xml_normalize_identically(self) -> None:
        a = normalize_legislation_gov_uk_instrument_identity(
            "https://www.legislation.gov.uk/uksi/2019/739"
        )
        b = normalize_legislation_gov_uk_instrument_identity(
            "https://www.legislation.gov.uk/uksi/2019/739/data.xml"
        )
        assert a == b == "uksi/2019/739"

    def test_provision_urls_normalize_to_instrument(self) -> None:
        assert (
            normalize_legislation_gov_uk_instrument_identity(
                "https://www.legislation.gov.uk/uksi/2019/739/regulation/3"
            )
            == "uksi/2019/739"
        )
        assert (
            normalize_legislation_gov_uk_instrument_identity(
                "https://www.legislation.gov.uk/uksi/2019/739/regulation/3/made"
            )
            == "uksi/2019/739"
        )

    def test_manifestation_and_pit_suffixes_ignored(self) -> None:
        assert (
            normalize_legislation_gov_uk_instrument_identity(
                "https://www.legislation.gov.uk/uksi/2019/739/2020-12-31/data.xml"
            )
            == "uksi/2019/739"
        )
        assert (
            normalize_legislation_gov_uk_instrument_identity(
                "https://www.legislation.gov.uk/uksi/2019/739/contents"
            )
            == "uksi/2019/739"
        )
        assert (
            normalize_legislation_gov_uk_instrument_identity(
                "http://www.legislation.gov.uk/id/uksi/2019/739"
            )
            == "uksi/2019/739"
        )

    def test_different_types_years_numbers_remain_distinct(self) -> None:
        assert normalize_legislation_gov_uk_instrument_identity(
            "https://www.legislation.gov.uk/uksi/2019/739"
        ) != normalize_legislation_gov_uk_instrument_identity(
            "https://www.legislation.gov.uk/ssi/2019/739"
        )
        assert normalize_legislation_gov_uk_instrument_identity(
            "https://www.legislation.gov.uk/uksi/2019/739"
        ) != normalize_legislation_gov_uk_instrument_identity(
            "https://www.legislation.gov.uk/uksi/2018/739"
        )
        assert normalize_legislation_gov_uk_instrument_identity(
            "https://www.legislation.gov.uk/uksi/2019/739"
        ) != normalize_legislation_gov_uk_instrument_identity(
            "https://www.legislation.gov.uk/uksi/2019/740"
        )

    def test_celex_wrappers_normalize(self) -> None:
        assert normalize_celex_identifier("32015R0812") == "32015R0812"
        assert normalize_celex_identifier("celex: 32015r0812") == "32015R0812"
        assert (
            normalize_celex_identifier(
                "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32015R0812"
            )
            == "32015R0812"
        )

    def test_query_params_do_not_alter_identity(self) -> None:
        assert (
            normalize_legislation_gov_uk_instrument_identity(
                "https://www.legislation.gov.uk/uksi/2019/739?view=extent"
            )
            == "uksi/2019/739"
        )

    def test_normalization_is_deterministic(self) -> None:
        urls = [
            "https://www.legislation.gov.uk/uksi/2019/739/regulation/3/made",
            "http://www.legislation.gov.uk/id/uksi/2019/739",
            "https://www.legislation.gov.uk/uksi/2019/739/data.xml",
        ]
        assert {normalize_legislation_gov_uk_instrument_identity(u) for u in urls} == {
            "uksi/2019/739"
        }

    def test_structured_citations(self) -> None:
        assert parse_structured_citation_identity("S.I. 2019/739") == "uksi/2019/739"
        assert parse_structured_citation_identity("UKSI 2019/739") == "uksi/2019/739"
        assert parse_structured_citation_identity("Regulation (EU) 2015/812") == "eur/2015/812"
        assert (
            parse_structured_citation_identity("Commission Regulation (EU) 2015/812")
            == "eur/2015/812"
        )
        assert parse_structured_citation_identity("2015/812") is None
        assert parse_structured_citation_identity("The Common Fisheries Policy Regulations") is None


class TestMatching:
    def test_exact_uri_plus_snapshot_consumed(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[
                _record(
                    record_id="src-uksi-2019-739",
                    asid="uksi/2019/739",
                    title="The Common Fisheries Policy (Amendment etc.) (EU Exit) Regulations 2019",
                    citation="UKSI 2019/739",
                )
            ],
            source_snapshots=[
                _snap(snap_id="snap-uksi-739", record_id="src-uksi-2019-739", asid="uksi/2019/739")
            ],
        )
        effect = _effect(
            affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739/regulation/3",
            affecting_instrument_citation="UKSI 2019/739",
        )
        out = reconcile_affecting_instrument_consumption([effect], inventory=inventory)[0]
        assert out["independent_consumption_status"] == "consumed_in_current_run"
        assert out["matched_source_record_id"] == "src-uksi-2019-739"
        assert out["matched_source_snapshot_ids"] == ["snap-uksi-739"]
        assert out["consumption_match_basis"] == "canonical_authority_uri"
        assert out["matched_instrument_identity"] == "uksi/2019/739"
        assert out["consumption_match_evidence"][0]["normalized_identity"] == "uksi/2019/739"

    def test_celex_plus_snapshot_consumed(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[
                _record(
                    record_id="src-eur-2015-812",
                    asid="eur/2015/812",
                    celex="32015R0812",
                )
            ],
            source_snapshots=[
                _snap(snap_id="snap-812", record_id="src-eur-2015-812", asid="eur/2015/812")
            ],
        )
        effect = _effect(
            affecting_instrument_uri=None,
            metadata={"celex": "CELEX:32015r0812"},
        )
        out = reconcile_affecting_instrument_consumption([effect], inventory=inventory)[0]
        assert out["independent_consumption_status"] == "consumed_in_current_run"
        assert out["matched_source_record_id"] == "src-eur-2015-812"
        assert out["consumption_match_basis"] == "celex_identifier"

    def test_structured_citation_match(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[_record(record_id="src-uksi-2019-739", asid="uksi/2019/739")],
            source_snapshots=[
                _snap(snap_id="snap-uksi", record_id="src-uksi-2019-739", asid="uksi/2019/739")
            ],
        )
        effect = _effect(
            affecting_instrument_uri=None,
            affecting_instrument_citation="S.I. 2019/739",
        )
        out = reconcile_affecting_instrument_consumption([effect], inventory=inventory)[0]
        assert out["independent_consumption_status"] == "consumed_in_current_run"
        assert out["consumption_match_basis"] == "normalized_citation"

    def test_register_match_without_snapshot(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[],
            source_snapshots=[],
            source_register_entries=[
                {
                    "source_id": "reg-uksi-2019-739",
                    "canonical_uri": "http://www.legislation.gov.uk/id/uksi/2019/739",
                    "title": "UKSI 2019/739",
                }
            ],
        )
        effect = _effect(
            affecting_instrument_uri="http://www.legislation.gov.uk/id/uksi/2019/739",
            affecting_instrument_citation="UKSI 2019/739",
        )
        out = reconcile_affecting_instrument_consumption([effect], inventory=inventory)[0]
        assert (
            out["independent_consumption_status"] == "present_in_source_register_but_not_consumed"
        )
        assert out["matched_source_record_id"] == "reg-uksi-2019-739"
        assert out["matched_source_snapshot_ids"] == []

    def test_source_record_without_snapshot_is_register_only(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[_record(record_id="src-uksi-2019-739", asid="uksi/2019/739")],
            source_snapshots=[],
        )
        effect = _effect(
            affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739",
        )
        diagnostics: list[dict] = []
        out = reconcile_affecting_instrument_consumption(
            [effect], inventory=inventory, diagnostics=diagnostics
        )[0]
        assert (
            out["independent_consumption_status"] == "present_in_source_register_but_not_consumed"
        )
        assert any(
            d.get("code") == "affecting_instrument_source_record_missing_snapshot"
            for d in diagnostics
        )

    def test_precise_identifier_no_match(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[_record(record_id="src-eur-2009-1224", asid="eur/2009/1224")],
            source_snapshots=[
                _snap(snap_id="snap-1224", record_id="src-eur-2009-1224", asid="eur/2009/1224")
            ],
        )
        effect = _effect(
            affecting_instrument_uri="http://www.legislation.gov.uk/id/eur/2015/812",
            affecting_instrument_citation="Regulation (EU) 2015/812",
        )
        out = reconcile_affecting_instrument_consumption([effect], inventory=inventory)[0]
        assert out["independent_consumption_status"] == "not_matched"
        assert out["consumption_match_basis"] == "no_match"
        assert out.get("matched_source_record_id") is None

    def test_insufficient_identity_not_assessed(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[_record(record_id="src-a", asid="eur/2009/1224")],
            source_snapshots=[_snap(snap_id="snap-a", record_id="src-a")],
        )
        effect = _effect(
            affecting_instrument_uri=None,
            affecting_instrument_citation=None,
            affecting_instrument_title="Some vague amending instrument",
        )
        diagnostics: list[dict] = []
        out = reconcile_affecting_instrument_consumption(
            [effect], inventory=inventory, diagnostics=diagnostics
        )[0]
        assert out["independent_consumption_status"] == "not_assessed"
        assert out["consumption_match_basis"] == "insufficient_identity"
        assert any(
            d.get("code") == "affecting_instrument_identifier_insufficient" for d in diagnostics
        )

    def test_title_only_similarity_does_not_match(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[
                _record(
                    record_id="src-uksi-2019-739",
                    asid="uksi/2019/739",
                    title="The Common Fisheries Policy (Amendment etc.) (EU Exit) Regulations 2019",
                )
            ],
            source_snapshots=[
                _snap(snap_id="snap-uksi", record_id="src-uksi-2019-739", asid="uksi/2019/739")
            ],
        )
        effect = _effect(
            affecting_instrument_uri=None,
            affecting_instrument_citation=None,
            affecting_instrument_title=(
                "The Common Fisheries Policy (Amendment etc.) (EU Exit) Regulations 2019"
            ),
        )
        out = reconcile_affecting_instrument_consumption([effect], inventory=inventory)[0]
        assert out["independent_consumption_status"] == "not_assessed"
        assert out.get("matched_source_record_id") is None

    def test_does_not_match_own_principal_source(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[_record(record_id="src-eur-2009-1224", asid="eur/2009/1224")],
            source_snapshots=[
                _snap(snap_id="snap-1224", record_id="src-eur-2009-1224", asid="eur/2009/1224")
            ],
        )
        effect = _effect(
            source_record_id="src-eur-2009-1224",
            affecting_instrument_uri="https://www.legislation.gov.uk/eur/2009/1224",
        )
        out = reconcile_affecting_instrument_consumption([effect], inventory=inventory)[0]
        assert out["independent_consumption_status"] == "not_matched"
        assert out.get("matched_source_record_id") is None

    def test_ambiguous_duplicate_source_records(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[
                _record(record_id="src-a", asid="uksi/2019/739"),
                _record(record_id="src-b", asid="uksi/2019/739"),
            ],
            source_snapshots=[
                _snap(snap_id="snap-a", record_id="src-a", asid="uksi/2019/739"),
                _snap(snap_id="snap-b", record_id="src-b", asid="uksi/2019/739"),
            ],
        )
        effect = _effect(
            affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739",
        )
        diagnostics: list[dict] = []
        out = reconcile_affecting_instrument_consumption(
            [effect], inventory=inventory, diagnostics=diagnostics
        )[0]
        assert out["independent_consumption_status"] == "not_matched"
        assert out["consumption_match_basis"] == "ambiguous_identity"
        assert out.get("matched_source_record_id") is None
        assert any(d.get("code") == "affecting_instrument_match_ambiguous" for d in diagnostics)

    def test_conflicting_strong_identifiers(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[
                _record(record_id="src-uksi", asid="uksi/2019/739"),
                _record(record_id="src-eur", asid="eur/2015/812", celex="32015R0812"),
            ],
            source_snapshots=[
                _snap(snap_id="snap-uksi", record_id="src-uksi", asid="uksi/2019/739"),
                _snap(snap_id="snap-eur", record_id="src-eur", asid="eur/2015/812"),
            ],
        )
        effect = _effect(
            affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739",
            metadata={"celex": "32015R0812"},
        )
        diagnostics: list[dict] = []
        out = reconcile_affecting_instrument_consumption(
            [effect], inventory=inventory, diagnostics=diagnostics
        )[0]
        assert out.get("matched_source_record_id") is None
        assert out["consumption_match_basis"] == "ambiguous_identity"
        assert any(d.get("code") == "affecting_instrument_identity_conflict" for d in diagnostics)

    def test_multiple_snapshots_retained_deterministically(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[_record(record_id="src-uksi", asid="uksi/2019/739")],
            source_snapshots=[
                _snap(snap_id="snap-b", record_id="src-uksi", asid="uksi/2019/739"),
                _snap(snap_id="snap-a", record_id="src-uksi", asid="uksi/2019/739"),
            ],
        )
        effect = _effect(
            affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739",
        )
        out = reconcile_affecting_instrument_consumption([effect], inventory=inventory)[0]
        assert out["matched_source_snapshot_ids"] == ["snap-a", "snap-b"]

    def test_empty_inventory_does_not_crash(self) -> None:
        artifact = reconcile_source_legal_effects_artifact(
            {
                "schema_version": "1",
                "run_id": "run-empty",
                "effects": [
                    _effect(affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739")
                ],
                "effect_links": [],
                "diagnostics": [],
                "outstanding_effects_status": "source_status_unknown",
                "metadata": {},
            },
            source_records=[],
            source_snapshots=[],
        )
        assert artifact["effects"][0]["independent_consumption_status"] == "not_assessed"

    def test_older_effect_round_trip_without_match_fields(self) -> None:
        effect = SourceLegalEffect.model_validate(
            {
                "id": "sourceeffect:legacy",
                "source_record_id": "src-a",
                "source_snapshot_id": "snap-a",
                "independent_consumption_status": "not_assessed",
            }
        )
        dumped = effect.model_dump(mode="json")
        assert dumped["matched_source_snapshot_ids"] == []
        assert dumped["consumption_match_evidence"] == []
        assert dumped["matched_source_record_id"] is None

    def test_matching_is_run_scoped_via_attach(self) -> None:
        effect_inventory = {
            "effects": [
                _effect(
                    affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739/regulation/3"
                )
            ],
            "effect_links": [],
            "diagnostics": [],
            "outstanding_effects_status": "source_status_unknown",
            "metadata": {},
        }
        bundle_a = {
            "run": {"id": "run-a"},
            "source_records": [_record(record_id="src-eur", asid="eur/2009/1224")],
            "source_snapshots": [
                {
                    **_snap(snap_id="snap-eur", record_id="src-eur", asid="eur/2009/1224"),
                    "metadata": {
                        "authority_source_id": "eur/2009/1224",
                        "source_legal_effects": effect_inventory,
                    },
                }
            ],
        }
        bundle_b = {
            "run": {"id": "run-b"},
            "source_records": [
                _record(record_id="src-eur", asid="eur/2009/1224"),
                _record(record_id="src-uksi", asid="uksi/2019/739"),
            ],
            "source_snapshots": [
                {
                    **_snap(snap_id="snap-eur", record_id="src-eur", asid="eur/2009/1224"),
                    "metadata": {
                        "authority_source_id": "eur/2009/1224",
                        "source_legal_effects": effect_inventory,
                    },
                },
                _snap(snap_id="snap-uksi", record_id="src-uksi", asid="uksi/2019/739"),
            ],
        }
        attach_source_legal_effects(bundle_a)
        attach_source_legal_effects(bundle_b)
        assert (
            bundle_a["source_legal_effects"]["effects"][0]["independent_consumption_status"]
            == "not_matched"
        )
        assert (
            bundle_b["source_legal_effects"]["effects"][0]["independent_consumption_status"]
            == "consumed_in_current_run"
        )
        assert (
            bundle_b["source_legal_effects"]["effects"][0]["matched_source_record_id"] == "src-uksi"
        )

    def test_deterministic_ordering(self) -> None:
        inventory = build_run_source_inventory(
            source_records=[_record(record_id="src-uksi", asid="uksi/2019/739")],
            source_snapshots=[
                _snap(snap_id="snap-uksi", record_id="src-uksi", asid="uksi/2019/739")
            ],
        )
        effects = [
            _effect(
                id="sourceeffect:b",
                annotation_label="F5",
                annotation_id="b",
                affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739",
            ),
            _effect(
                id="sourceeffect:a",
                annotation_label="F4",
                annotation_id="a",
                affecting_instrument_uri="https://www.legislation.gov.uk/uksi/2019/739",
            ),
        ]
        first = reconcile_affecting_instrument_consumption(effects, inventory=inventory)
        second = reconcile_affecting_instrument_consumption(
            list(reversed(effects)), inventory=inventory
        )
        # Status/evidence identical per effect id regardless of input order.
        by_id_1 = {e["id"]: e for e in first}
        by_id_2 = {e["id"]: e for e in second}
        for eid in by_id_1:
            assert (
                by_id_1[eid]["independent_consumption_status"]
                == by_id_2[eid]["independent_consumption_status"]
            )
            assert (
                by_id_1[eid]["matched_source_record_id"] == by_id_2[eid]["matched_source_record_id"]
            )
            assert (
                by_id_1[eid]["consumption_match_evidence"]
                == by_id_2[eid]["consumption_match_evidence"]
            )
