from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from law_proposition_extractor_domain import (
    AffectingInstrumentConsumptionStatus,
    OutstandingEffectsStatus,
    SourceEffectCategory,
    SourceEffectRepresentationStatus,
    SourceEffectStatus,
    SourceFragment,
    SourceLegalEffect,
    SourceSnapshot,
)
from law_proposition_extractor_pipeline.source_legal_effects import (
    attach_source_legal_effects,
    build_source_legal_effects_artifact,
)
from law_proposition_extractor_pipeline.sources.adapters import LegislationGovUkAuthorityAdapter, SourceFetchRequest
from law_proposition_extractor_pipeline.sources.legislation_effects import (
    finalize_source_legal_effects,
    link_effects_to_fragments,
    locator_from_clml_id,
    normalize_effect_category,
    parse_source_legal_effects,
    source_effect_id,
    source_effect_link_id,
)
from law_proposition_extractor_pipeline.sources.service import SourceIngestionService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "legislation_effects"


def _load(name: str) -> ElementTree.Element:
    return ElementTree.fromstring((FIXTURES / name).read_text(encoding="utf-8"))


def _frag(
    *,
    frag_id: str,
    locator: str,
    snapshot_id: str = "snap-demo",
    source_id: str = "src-demo",
) -> SourceFragment:
    return SourceFragment(
        id=frag_id,
        fragment_id=frag_id,
        source_record_id=source_id,
        source_snapshot_id=snapshot_id,
        locator=locator,
        fragment_text=f"text for {locator}",
        fragment_hash="abc",
    )


class TestParsingAndClassification:
    def test_explicit_amendment_commentary_produces_effect(self) -> None:
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        labels = {e.annotation_label for e in parsed.effects}
        assert "F1" in labels
        assert any(e.effect_category == SourceEffectCategory.INSERTION for e in parsed.effects)
        assert any(e.effect_category == SourceEffectCategory.SUBSTITUTION for e in parsed.effects)

    def test_non_amendment_editorial_footnote_not_amendment_effect(self) -> None:
        parsed = parse_source_legal_effects(
            _load("mixed_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        editorial = [e for e in parsed.effects if e.annotation_id == "c-editorial"]
        # Type=X with no instrument cite and no amendment markers may be omitted,
        # or present only as editorial_note — never as substitution/insertion.
        for effect in editorial:
            assert effect.effect_category == SourceEffectCategory.EDITORIAL_NOTE
        assert not any(
            e.annotation_id == "f00001" or (e.effect_description or "").startswith("Opinion of")
            for e in parsed.effects
        )

    def test_raw_and_normalized_category_preserved(self) -> None:
        parsed = parse_source_legal_effects(
            _load("mixed_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        sub = next(e for e in parsed.effects if e.annotation_id == "c-sub")
        assert sub.raw_effect_category == "Substitution"
        assert sub.effect_category == SourceEffectCategory.SUBSTITUTION
        outstanding = next(
            e for e in parsed.effects if e.effect_status == SourceEffectStatus.SOURCE_MARKS_OUTSTANDING
        )
        assert outstanding.raw_effect_category == "words substituted"
        assert outstanding.effect_category == SourceEffectCategory.SUBSTITUTION

    def test_normalize_is_conservative(self) -> None:
        assert normalize_effect_category("gibberish") == SourceEffectCategory.UNKNOWN
        assert normalize_effect_category("words substituted") == SourceEffectCategory.SUBSTITUTION

    def test_missing_optional_fields_do_not_crash(self) -> None:
        root = ElementTree.fromstring(
            """<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
            <Commentaries><Commentary Type="F" id="c1"><Para><Text>Inserted by X.</Text></Para></Commentary></Commentaries>
            </Legislation>"""
        )
        parsed = parse_source_legal_effects(root, source_record_id="s", source_snapshot_id="snap")
        assert len(parsed.effects) == 1
        assert parsed.effects[0].affecting_instrument_uri is None

    def test_namespace_aware_parsing(self) -> None:
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        assert parsed.effects

    def test_duplicate_refs_do_not_duplicate_effect(self) -> None:
        parsed = parse_source_legal_effects(
            _load("duplicate_refs.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        assert len([e for e in parsed.effects if e.annotation_id == "c-dup"]) == 1


class TestAnnotationResolution:
    def test_label_resolves_to_commentary(self) -> None:
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap-demo-1224-revised",
        )
        by_label = {e.annotation_label: e for e in parsed.effects}
        assert by_label["F2"].annotation_id == "key-ae688d7efb8d525f494201f970bc3e75"
        assert "Art. 49a(1)" in (by_label["F2"].effect_description or "")

    def test_one_effect_multiple_fragment_links(self) -> None:
        parsed = parse_source_legal_effects(
            _load("mixed_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        multi = next(e for e in parsed.effects if e.annotation_id == "c-multi")
        locs = parsed.effect_locators[multi.id]
        assert "regulation:2:paragraph:1" in locs
        assert "regulation:2:paragraph:2" in locs
        fragments = [
            _frag(frag_id="frag-p1", locator="regulation:2:paragraph:1"),
            _frag(frag_id="frag-p2", locator="regulation:2:paragraph:2"),
        ]
        effects, links, _ = link_effects_to_fragments(parsed, fragments)
        multi_links = [lnk for lnk in links if lnk.effect_id == multi.id and lnk.linkage_status == "linked"]
        assert len(multi_links) == 2
        assert len([e for e in effects if e.annotation_id == "c-multi"]) == 1

    def test_unresolved_label_creates_diagnostic(self) -> None:
        parsed = parse_source_legal_effects(
            _load("mixed_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        assert any(
            d.get("code") == "source_effect_reference_unresolved"
            and d.get("annotation_id") == "missing-ref"
            for d in parsed.diagnostics
        )

    def test_link_ordering_deterministic(self) -> None:
        parsed = parse_source_legal_effects(
            _load("mixed_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        fragments = [
            _frag(frag_id="frag-2", locator="regulation:2:paragraph:2"),
            _frag(frag_id="frag-1", locator="regulation:2:paragraph:1"),
            _frag(frag_id="frag-r1", locator="regulation:1"),
        ]
        _, links_a, _ = link_effects_to_fragments(parsed, fragments)
        _, links_b, _ = link_effects_to_fragments(parsed, list(reversed(fragments)))
        assert [lnk.id for lnk in links_a] == [lnk.id for lnk in links_b]


class TestFragmentLinkage:
    def test_article_49a_paragraph_links(self) -> None:
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src-demo",
            source_snapshot_id="snap-demo-1224-revised",
        )
        fragments = [
            _frag(frag_id="frag-demo-49a", locator="article:49a"),
            _frag(frag_id="frag-demo-49a-p1", locator="article:49a:paragraph:1"),
            _frag(frag_id="frag-demo-49a-p2", locator="article:49a:paragraph:2"),
            _frag(frag_id="frag-demo-49a-p3", locator="article:49a:paragraph:3"),
        ]
        effects, links, _ = link_effects_to_fragments(parsed, fragments)
        by_label = {e.annotation_label: e for e in effects}
        f2_links = [lnk for lnk in links if lnk.effect_id == by_label["F2"].id]
        assert any(
            lnk.affected_locator == "article:49a:paragraph:1"
            and lnk.source_fragment_id == "frag-demo-49a-p1"
            for lnk in f2_links
        )
        f3_links = [lnk for lnk in links if lnk.effect_id == by_label["F3"].id]
        assert any(lnk.affected_locator == "article:49a:paragraph:2" for lnk in f3_links)
        f1_links = [lnk for lnk in links if lnk.effect_id == by_label["F1"].id]
        # Article-level insertion must not be guessed down to a single paragraph only.
        f1_locs = {lnk.affected_locator for lnk in f1_links if lnk.affected_locator}
        assert "article:49a" in f1_locs or f1_locs == {
            "article:49a",
            "article:49a:paragraph:1",
            "article:49a:paragraph:2",
            "article:49a:paragraph:3",
        }

    def test_locator_from_clml_id(self) -> None:
        assert locator_from_clml_id("article-49a-1") == "article:49a:paragraph:1"
        assert locator_from_clml_id("article-49a") == "article:49a"
        assert locator_from_clml_id("article-49a-2-a") == "article:49a:paragraph:2"

    def test_snapshot_scoped_ids_do_not_collide(self) -> None:
        a = source_effect_id(source_snapshot_id="snap-a", annotation_id="c1", effect_description="x")
        b = source_effect_id(source_snapshot_id="snap-b", annotation_id="c1", effect_description="x")
        assert a != b
        assert a.startswith("sourceeffect:")


class TestStatusTruthfulness:
    def test_outstanding_preserved(self) -> None:
        parsed = parse_source_legal_effects(
            _load("mixed_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        assert parsed.outstanding_effects_status == OutstandingEffectsStatus.SOURCE_REPORTS_PRESENT
        outstanding = [
            e for e in parsed.effects if e.effect_status == SourceEffectStatus.SOURCE_MARKS_OUTSTANDING
        ]
        assert outstanding
        assert all(
            e.independent_consumption_status
            == AffectingInstrumentConsumptionStatus.NOT_ASSESSED
            for e in outstanding
        )

    def test_absence_of_status_is_unknown_not_none(self) -> None:
        parsed = parse_source_legal_effects(
            _load("no_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        assert parsed.outstanding_effects_status == OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN

    def test_revised_manifestation_alone_does_not_imply_none(self) -> None:
        # article_49a fixture is revised + EffectsApplied link, but no UnappliedEffects.
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        assert parsed.outstanding_effects_status == OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN
        assert parsed.metadata.get("effects_applied_link_present") is True

    def test_empty_unapplied_effects_is_none(self) -> None:
        parsed = parse_source_legal_effects(
            _load("empty_unapplied_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        assert parsed.outstanding_effects_status == OutstandingEffectsStatus.SOURCE_REPORTS_NONE

    def test_commentary_effects_have_unknown_applied_status(self) -> None:
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        commentary_effects = [
            e
            for e in parsed.effects
            if e.source_representation_status
            in {
                SourceEffectRepresentationStatus.ANNOTATION_PRESENT,
                SourceEffectRepresentationStatus.REVISED_TEXT_REFERENCE_PRESENT,
            }
        ]
        assert commentary_effects
        assert all(
            e.effect_status == SourceEffectStatus.SOURCE_STATUS_UNKNOWN for e in commentary_effects
        )

    def test_effect_date_from_commentary_not_retrieval(self) -> None:
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        f2 = next(e for e in parsed.effects if e.annotation_label == "F2")
        assert f2.effect_date is not None
        assert f2.effect_date.isoformat() == "2020-12-31"


class TestPersistenceAndIdentity:
    def test_stable_ids_independent_of_ordering(self) -> None:
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        ids_a = [e.id for e in parsed.effects]
        ids_b = [e.id for e in parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        ).effects]
        assert ids_a == ids_b
        assert all(i.startswith("sourceeffect:") for i in ids_a)

    def test_stable_link_ids(self) -> None:
        a = source_effect_link_id(
            effect_id="sourceeffect:abc",
            affected_locator="article:49a:paragraph:1",
            source_fragment_id="frag-1",
        )
        b = source_effect_link_id(
            effect_id="sourceeffect:abc",
            affected_locator="article:49a:paragraph:1",
            source_fragment_id="frag-1",
        )
        assert a == b
        assert a.startswith("sourceeffectlink:")

    def test_serialization_round_trip(self) -> None:
        parsed = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap",
        )
        fragments = [
            _frag(frag_id="frag-demo-49a", locator="article:49a"),
            _frag(frag_id="frag-demo-49a-p1", locator="article:49a:paragraph:1"),
            _frag(frag_id="frag-demo-49a-p2", locator="article:49a:paragraph:2"),
            _frag(frag_id="frag-demo-49a-p3", locator="article:49a:paragraph:3"),
        ]
        inventory = finalize_source_legal_effects(parsed, fragments)
        for row in inventory["effects"]:
            restored = SourceLegalEffect.model_validate(row)
            assert restored.id == row["id"]
            assert restored.independent_consumption_status == (
                AffectingInstrumentConsumptionStatus.NOT_ASSESSED
            )

    def test_two_snapshots_different_inventories(self) -> None:
        a = parse_source_legal_effects(
            _load("article_49a_amendments.xml"),
            source_record_id="src",
            source_snapshot_id="snap-a",
        )
        b = parse_source_legal_effects(
            _load("no_effects.xml"),
            source_record_id="src",
            source_snapshot_id="snap-b",
        )
        assert a.effects and not b.effects
        assert {e.id for e in a.effects}.isdisjoint({e.id for e in b.effects})

    def test_empty_artifact_valid(self) -> None:
        artifact = build_source_legal_effects_artifact(run_id="run-1", source_snapshots=[])
        assert artifact["effects"] == []
        assert artifact["outstanding_effects_status"] == (
            OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN.value
        )

    def test_older_runs_without_artifact_load(self) -> None:
        # attach from snapshots without inventories → empty unknown
        bundle = {
            "run": {"id": "run-old"},
            "source_snapshots": [
                {"id": "snap", "metadata": {}},
            ],
        }
        attach_source_legal_effects(bundle)
        assert bundle["source_legal_effects"]["effects"] == []
        assert bundle["source_legal_effects"]["outstanding_effects_status"] == "source_status_unknown"


class TestArticle49aRegression:
    def test_article_49a_inventory_shape(self) -> None:
        xml_text = (FIXTURES / "article_49a_amendments.xml").read_text(encoding="utf-8")

        def fetch_xml(_url: str) -> tuple[str, dict]:
            return xml_text, {
                "status": 200,
                "content_type": "application/xml",
                "response_bytes": len(xml_text),
                "resolved_url": "https://www.legislation.gov.uk/eur/2009/1224/article/49a/data.xml",
                "requested_url": "https://www.legislation.gov.uk/eur/2009/1224/article/49a/data.xml",
            }

        service = SourceIngestionService(
            adapters={
                "legislation_gov_uk": LegislationGovUkAuthorityAdapter(fetch_xml=fetch_xml),
            }
        )
        result = service.ingest_sources(
            [
                {
                    "id": "src-demo-1224",
                    "authority": "legislation_gov_uk",
                    "authority_source_id": "eur/2009/1224",
                    "snapshot_id": "snap-demo-1224-revised",
                    "source_url": "https://www.legislation.gov.uk/eur/2009/1224/article/49a/data.xml",
                    "version_id": "v1",
                    "retrieved_at": datetime(2026, 7, 14, tzinfo=UTC),
                }
            ]
        )
        assert result.source_legal_effects
        inventory = result.source_legal_effects[0]
        effects = inventory["effects"]
        links = inventory["effect_links"]
        by_label = {e["annotation_label"]: e for e in effects if e.get("annotation_label")}
        assert set(by_label) >= {"F1", "F2", "F3", "F4"}
        assert by_label["F2"]["effect_category"] == "substitution"
        assert by_label["F2"]["source_snapshot_id"] == "snap-demo-1224-revised"
        assert by_label["F2"]["affecting_instrument_uri"]
        assert by_label["F2"]["effect_status"] == "source_status_unknown"
        assert by_label["F2"]["independent_consumption_status"] == "not_assessed"

        f2_links = [lnk for lnk in links if lnk["effect_id"] == by_label["F2"]["id"]]
        assert any(lnk.get("affected_locator") == "article:49a:paragraph:1" for lnk in f2_links)

        # Fragment back-refs present for linked paragraphs
        p1 = next(f for f in result.fragments if f.locator == "article:49a:paragraph:1")
        assert by_label["F2"]["id"] in p1.source_legal_effect_ids

        # Manifestation revised must not imply outstanding=none
        assert inventory["outstanding_effects_status"] == "source_status_unknown"

        # Snapshot round-trip via SourceSnapshot
        snap = result.snapshots[0]
        assert snap.manifestation_type is not None
        assert snap.manifestation_type.value == "revised"
        restored = SourceSnapshot.model_validate(snap.model_dump(mode="json"))
        assert "source_legal_effects" in restored.metadata

        source = result.sources[0]
        bundle = {
            "run": {"id": "run-demo"},
            "source_records": [source.model_dump(mode="json")],
            "source_snapshots": [snap.model_dump(mode="json")],
        }
        attach_source_legal_effects(bundle)
        artifact = bundle["source_legal_effects"]
        assert artifact["schema_version"] == "1"
        assert len(artifact["effects"]) >= 4
        # After run-scoped reconciliation, precise URIs with no matching consumed
        # affecting instrument become not_matched (not left as not_assessed).
        assert all(
            e.get("independent_consumption_status")
            in {"not_matched", "not_assessed", "present_in_source_register_but_not_consumed"}
            for e in artifact["effects"]
        )
        f2 = next(e for e in artifact["effects"] if e.get("annotation_label") == "F2")
        assert f2["independent_consumption_status"] == "not_matched"
        assert f2.get("matched_source_record_id") is None


class TestAdapterIntegration:
    def test_adapter_stores_draft_effects_metadata(self) -> None:
        xml_text = (FIXTURES / "no_effects.xml").read_text(encoding="utf-8")

        def fetch_xml(_url: str) -> tuple[str, dict]:
            return xml_text, {
                "status": 200,
                "content_type": "application/xml",
                "response_bytes": len(xml_text),
                "resolved_url": "https://www.legislation.gov.uk/uksi/2018/1/data.xml",
                "requested_url": "https://www.legislation.gov.uk/uksi/2018/1/data.xml",
            }

        adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fetch_xml)
        result = adapter.fetch(
            SourceFetchRequest(
                authority="legislation_gov_uk",
                authority_source_id="uksi/2018/1",
                version_id="v1",
                expected_content_hash=None,
                raw_source={
                    "source_url": "https://www.legislation.gov.uk/uksi/2018/1/data.xml",
                },
            )
        )
        draft = result.payload.metadata.get("source_legal_effects_draft")
        assert isinstance(draft, dict)
        assert draft["outstanding_effects_status"] == "source_status_unknown"
        assert draft["effects"] == []
