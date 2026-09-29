import json
from pathlib import Path

from fastapi.testclient import TestClient
from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_domain import LegalScopeReviewCandidate, Proposition, ReviewStatus, SourceRecord
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.linting import lint_bundle, lint_export_dir, load_exported_bundle
from law_proposition_extractor_pipeline.run_quality import build_run_quality_summary
from law_proposition_extractor_pipeline.operations import OperationalStore
from law_proposition_extractor_pipeline.scope_linking import (
    build_scope_artifacts_for_run,
    load_seed_legal_scopes,
    register_unknown_scope_review_candidate,
    seed_taxonomy_path,
)


def test_seed_taxonomy_loads_and_has_hierarchy() -> None:
    scopes = load_seed_legal_scopes()
    by_slug = {s.slug: s for s in scopes}
    assert by_slug["equine"].parent_scope_id == "kept_terrestrial_animal"
    assert by_slug["kept_terrestrial_animal"].parent_scope_id == "terrestrial_animal"
    assert by_slug["terrestrial_animal"].parent_scope_id == "animal"
    assert "horse" in by_slug["equine"].synonyms


def test_title_only_equine_no_direct_relevance() -> None:
    prop = Proposition(
        id="prop-title-only-equine",
        topic_id="t",
        source_record_id="src1",
        jurisdiction="EU",
        proposition_text=(
            "Operators must update the bovine herd register before each movement."
        ),
        legal_subject="operator",
        action="update_register",
    )
    src = SourceRecord(
        id="src1",
        title="Derogation for equine passports and bovine herds",
        jurisdiction="EU",
        citation="EU-TEST",
        kind="regulation",
        authoritative_text="Operators must update herd registers. Bovine herds only.",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="run-t1", propositions=[prop], sources=[src])
    equine_explicit = [
        ln
        for ln in payload.proposition_scope_links
        if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert equine_explicit
    eq = equine_explicit[0]
    assert eq.relevance == "contextual"
    assert eq.signals.get("evidence_field") == "source_title"


def test_species_exclusion_list_equine_is_not_direct_high() -> None:
    """Art 109-style 'other species' listing: equine at end of an exclusion chain is not primary."""
    prop = Proposition(
        id="prop-excl-list-equine",
        topic_id="t",
        source_record_id="src1",
        jurisdiction="EU",
        proposition_text=(
            "Member States shall record database information for species other than "
            "bovine, ovine, caprine, porcine and equine when rules so provide."
        ),
        legal_subject="member state",
        action="record database information",
    )
    src = SourceRecord(
        id="src1",
        title="Database regulation",
        jurisdiction="EU",
        citation="REF",
        kind="regulation",
        authoritative_text="General animal health preamble with no equine paragraph.",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="run-excl", propositions=[prop], sources=[src])
    equine = [
        ln
        for ln in payload.proposition_scope_links
        if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert equine
    assert equine[0].relevance == "contextual"
    assert equine[0].confidence == "medium"
    assert equine[0].signals.get("species_exclusion_context") is True


def test_kept_animals_equine_species_remains_direct_high() -> None:
    prop = Proposition(
        id="prop-kept-equine-species",
        topic_id="t",
        source_record_id="src1",
        jurisdiction="EU",
        proposition_text=(
            "Member States must record identification data on kept animals of the equine species."
        ),
        legal_subject="member state",
        action="record",
    )
    src = SourceRecord(
        id="src1",
        title="x",
        jurisdiction="EU",
        citation="y",
        kind="regulation",
        authoritative_text="noise",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="run-kept", propositions=[prop], sources=[src])
    equine = [
        ln
        for ln in payload.proposition_scope_links
        if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert equine
    assert equine[0].relevance == "direct"
    assert equine[0].confidence == "high"
    assert not equine[0].signals.get("species_exclusion_context")


def test_proposition_equidae_is_direct_equine_high() -> None:
    prop = Proposition(
        id="prop-equidae-text",
        topic_id="t",
        source_record_id="src1",
        jurisdiction="EU",
        proposition_text="Operators shall identify equidae before movement.",
        legal_subject="keeper",
        action="identify equidae",
    )
    src = SourceRecord(
        id="src1",
        title="Animal ID",
        jurisdiction="EU",
        citation="REF",
        kind="regulation",
        authoritative_text="General animal rules.",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="run-eq", propositions=[prop], sources=[src])
    equine = [
        ln
        for ln in payload.proposition_scope_links
        if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert equine
    assert equine[0].relevance == "direct"
    assert equine[0].confidence == "high"
    assert equine[0].signals.get("evidence_field") == "proposition_text"


def test_label_only_equine_match_is_not_direct_high() -> None:
    prop = Proposition(
        id="prop-label-only-equine",
        topic_id="t",
        source_record_id="src1",
        jurisdiction="EU",
        proposition_text="Operators must keep records for livestock movement.",
        label="Equine passport logistics dashboard",
        legal_subject="operator",
        action="keep records",
    )
    src = SourceRecord(
        id="src1",
        title="Livestock register",
        jurisdiction="EU",
        citation="REF",
        kind="regulation",
        authoritative_text="No species-specific terms appear in this source fragment.",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="run-label-only", propositions=[prop], sources=[src])
    equine = [
        ln
        for ln in payload.proposition_scope_links
        if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert equine
    assert equine[0].signals.get("evidence_field") == "proposition_label"
    assert equine[0].relevance == "contextual"
    assert equine[0].confidence == "medium"


def test_source_fragment_equidae_supports_direct_high() -> None:
    prop = Proposition(
        id="prop-frag-equidae",
        topic_id="t",
        source_record_id="src1",
        jurisdiction="EU",
        proposition_text="Authorities shall maintain an identification register.",
        label="Register obligations",
        legal_subject="authority",
        action="maintain register",
    )
    src = SourceRecord(
        id="src1",
        title="Identification requirements",
        jurisdiction="EU",
        citation="REF",
        kind="regulation",
        authoritative_text=(
            "The identification document for equidae shall contain the transponder reference."
        ),
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="run-frag-eq", propositions=[prop], sources=[src])
    equine = [
        ln
        for ln in payload.proposition_scope_links
        if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert equine
    assert equine[0].signals.get("evidence_field") == "source_fragment_text"
    assert equine[0].relevance == "direct"
    assert equine[0].confidence == "high"


def test_structured_legal_subject_equidae_supports_direct_high() -> None:
    prop = Proposition(
        id="prop-structured-equidae",
        topic_id="t",
        source_record_id="src1",
        jurisdiction="EU",
        proposition_text="Operators shall register each animal before movement.",
        label="Registration duty",
        legal_subject="keeper of equidae",
        action="register animals",
    )
    src = SourceRecord(
        id="src1",
        title="General registration regulation",
        jurisdiction="EU",
        citation="REF",
        kind="regulation",
        authoritative_text="General procedural text.",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="run-structured-eq", propositions=[prop], sources=[src])
    equine = [
        ln
        for ln in payload.proposition_scope_links
        if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert equine
    assert equine[0].signals.get("evidence_field") == "legal_subject"
    assert equine[0].relevance == "direct"
    assert equine[0].confidence == "high"


def test_weak_source_body_emits_quality_candidate_and_lint_cover() -> None:
    prop = Proposition(
        id="prop-weak-context",
        topic_id="t",
        source_record_id="srcw",
        jurisdiction="EU",
        proposition_text="There is a levy on oats purchased for bedding.",
        legal_subject="buyer",
        action="pay levy",
    )
    src = SourceRecord(
        id="srcw",
        title="Agricultural charges",
        jurisdiction="EU",
        citation="AG-99",
        kind="regulation",
        authoritative_text=(
            "Unrelated preamble. "
            + ("context filler. " * 400)
            + "The farmer kept many horses for draught work historically."
        ),
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(
        run_id="run-weak", propositions=[prop], sources=[src]
    )
    horse_links = [
        ln
        for ln in payload.proposition_scope_links
        if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert horse_links
    assert horse_links[0].signals.get("evidence_field") == "source_context"
    kinds = {
        c.signals.get("review_kind")
        for c in payload.scope_review_candidates
        if c.signals.get("proposition_id") == prop.id
    }
    assert "weak_source_context_only" in kinds
    bundle = {
        "legal_scopes": [s.model_dump(mode="json") for s in payload.legal_scopes],
        "propositions": [prop.model_dump(mode="json")],
        "proposition_scope_links": [
            ln.model_dump(mode="json") for ln in payload.proposition_scope_links
        ],
        "scope_review_candidates": [
            c.model_dump(mode="json") for c in payload.scope_review_candidates
        ],
    }
    report = lint_bundle(bundle)
    assert not any("review coverage gap" in w for w in report["warnings"])


def test_equine_synonym_links_via_deterministic_linker() -> None:
    demo = build_demo_bundle(use_llm=False)
    run_id = str(demo["run"]["id"])

    horse_prop = Proposition(
        id="prop-test-equine",
        topic_id=str(demo["topic"]["id"]),
        source_record_id="src-equine",
        jurisdiction="EU",
        proposition_text="The keeper must identify each horse before movement.",
        legal_subject="keeper",
        action="identify horses",
    )
    src = SourceRecord(
        id="src-equine",
        title="Equine identification instrument",
        jurisdiction="EU",
        citation="TEST-EQUINE",
        kind="regulation",
        authoritative_text="... horses ...",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(
        run_id=run_id,
        propositions=[horse_prop],
        sources=[src],
    )
    equine_links = [
        ln for ln in payload.proposition_scope_links if ln.scope_id == "equine"
    ]
    assert equine_links
    assert equine_links[0].inheritance == "explicit"
    assert equine_links[0].method == "deterministic"
    assert equine_links[0].signals.get("evidence_field") == "proposition_text"


def test_multiple_explicit_scopes_per_proposition() -> None:
    run_id = "run-multi"
    prop = Proposition(
        id="prop-multi",
        topic_id="t",
        source_record_id="s1",
        jurisdiction="EU",
        proposition_text="Database registration is required for cattle movement certificates.",
        legal_subject="operator",
        action="register",
    )
    src = SourceRecord(
        id="s1",
        title="Animal health",
        jurisdiction="EU",
        citation="X",
        kind="regulation",
        authoritative_text="database cattle certificate movement",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(
        run_id=run_id,
        propositions=[prop],
        sources=[src],
    )
    explicit = [ln for ln in payload.proposition_scope_links if ln.inheritance == "explicit"]
    scope_ids = {ln.scope_id for ln in explicit}
    assert len(scope_ids) >= 2


def test_hierarchy_emits_inherited_distinct_from_explicit() -> None:
    prop = Proposition(
        id="prop-hier",
        topic_id="t",
        source_record_id="s1",
        jurisdiction="EU",
        proposition_text="The horse passport must show identification.",
        legal_subject="keeper",
        action="passport",
    )
    src = SourceRecord(
        id="s1",
        title="x",
        jurisdiction="EU",
        citation="y",
        kind="regulation",
        authoritative_text="horse",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="r1", propositions=[prop], sources=[src])
    explicit = [ln for ln in payload.proposition_scope_links if ln.scope_id == "equine"]
    inherited = [ln for ln in payload.proposition_scope_links if ln.scope_id == "animal"]
    assert any(ln.inheritance == "explicit" for ln in explicit)
    assert any(ln.inheritance == "inherited" for ln in inherited)
    animal_inh = [ln for ln in inherited if ln.scope_id == "animal"]
    assert animal_inh
    assert animal_inh[0].relevance == "contextual"
    assert animal_inh[0].signals.get("narrower_scope_id") == "equine"


def test_lint_warns_deterministic_direct_without_prop_or_fragment_grounding() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-direct-bad-ground",
            "proposition_id": bundle["propositions"][0]["id"],
            "proposition_key": bundle["propositions"][0].get("proposition_key"),
            "scope_id": "animal",
            "relevance": "direct",
            "inheritance": "explicit",
            "confidence": "high",
            "method": "deterministic",
            "reason": "synthetic",
            "evidence": ["x"],
            "signals": {"evidence_field": "source_title"},
        }
    )
    report = lint_bundle(bundle)
    assert any("without grounded evidence" in w for w in report["warnings"])


def test_lint_warns_deterministic_direct_proposition_label_not_acceptable_grounding() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-direct-label-ground",
            "proposition_id": bundle["propositions"][0]["id"],
            "proposition_key": bundle["propositions"][0].get("proposition_key"),
            "scope_id": "animal",
            "relevance": "direct",
            "inheritance": "explicit",
            "confidence": "high",
            "method": "deterministic",
            "reason": "synthetic",
            "evidence": ["x"],
            "signals": {"evidence_field": "proposition_label"},
        }
    )
    report = lint_bundle(bundle)
    assert any("without grounded evidence" in w for w in report["warnings"])


def test_sibling_species_ambiguity_emits_candidate() -> None:
    prop = Proposition(
        id="prop-sib",
        topic_id="t",
        source_record_id="sibs",
        jurisdiction="EU",
        proposition_text="The keeper must tag each bovine and equine before transport.",
        legal_subject="keeper",
        action="tag",
    )
    src = SourceRecord(
        id="sibs",
        title="Farm transport",
        jurisdiction="EU",
        citation="TR",
        kind="regulation",
        authoritative_text="Tagging for bovine and equine consignments.",
        review_status=ReviewStatus.PROPOSED,
    )
    payload = build_scope_artifacts_for_run(run_id="run-sib", propositions=[prop], sources=[src])
    kinds = {c.signals.get("review_kind") for c in payload.scope_review_candidates}
    assert "sibling_species_ambiguity" in kinds


def test_unknown_scope_review_candidate_does_not_append_taxonomy() -> None:
    scopes_before = load_seed_legal_scopes()
    candidates: list[LegalScopeReviewCandidate] = []
    register_unknown_scope_review_candidate(
        candidates,
        run_id="run-x",
        suggested_slug="cryptozoology",
        reason="Emerging stakeholder label not in governed taxonomy.",
        evidence=["token:cryptozoology"],
        source="llm_suggestion",
    )
    scopes_after = load_seed_legal_scopes()
    assert len(scopes_before) == len(scopes_after)
    assert len(candidates) == 1
    assert candidates[0].suggested_slug == "cryptozoology"


def test_lint_scope_link_fallback_requires_reason_evidence() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-fallback-bad",
            "proposition_id": bundle["propositions"][0]["id"],
            "proposition_key": bundle["propositions"][0].get("proposition_key"),
            "scope_id": "animal",
            "relevance": "direct",
            "inheritance": "explicit",
            "confidence": "low",
            "method": "fallback",
            "reason": "",
            "evidence": [],
            "signals": {},
        }
    )
    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("fallback missing reason" in e for e in report["errors"])
    assert any("fallback missing evidence" in e for e in report["errors"])


def test_lint_warns_deprecated_scope_and_low_confidence() -> None:
    bundle = build_demo_bundle(use_llm=False)
    for s in bundle["legal_scopes"]:
        if s["id"] == "animal":
            s["status"] = "deprecated"
            break
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-extra",
            "proposition_id": bundle["propositions"][0]["id"],
            "scope_id": "animal",
            "relevance": "contextual",
            "inheritance": "explicit",
            "confidence": "low",
            "method": "manual",
            "reason": "Test coverage.",
            "evidence": ["fixtures"],
            "signals": {},
        }
    )
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-direct-low",
            "proposition_id": bundle["propositions"][0]["id"],
            "scope_id": "equine",
            "relevance": "direct",
            "inheritance": "explicit",
            "confidence": "low",
            "method": "manual",
            "reason": "Direct applicability coverage.",
            "evidence": ["fixtures"],
            "signals": {},
        }
    )
    report = lint_bundle(bundle)
    assert any("deprecated scope" in w for w in report["warnings"])
    assert any("confidence low" in w for w in report["warnings"])
    assert any("psl-direct-low" in w for w in report["warnings"])


def test_lint_contextual_low_confidence_scope_link_no_low_confidence_warning() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-ctx-low",
            "proposition_id": bundle["propositions"][0]["id"],
            "scope_id": "equine",
            "relevance": "contextual",
            "inheritance": "explicit",
            "confidence": "low",
            "method": "manual",
            "reason": "Contextual.",
            "evidence": ["fixtures"],
            "signals": {},
        }
    )
    report = lint_bundle(bundle)
    assert not any("psl-ctx-low" in w for w in report["warnings"])


def test_lint_inherited_low_confidence_parent_scope_no_low_confidence_warning() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-inh-low",
            "proposition_id": bundle["propositions"][0]["id"],
            "scope_id": "animal",
            "relevance": "indirect",
            "inheritance": "inherited",
            "confidence": "low",
            "method": "manual",
            "reason": "Parent scope.",
            "evidence": ["fixtures"],
            "signals": {},
        }
    )
    report = lint_bundle(bundle)
    assert not any("psl-inh-low" in w for w in report["warnings"])


def test_lint_direct_low_confidence_warns_and_counts_in_run_quality() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-dir-low",
            "proposition_id": bundle["propositions"][0]["id"],
            "scope_id": "equine",
            "relevance": "direct",
            "inheritance": "explicit",
            "confidence": "low",
            "method": "manual",
            "reason": "Direct low.",
            "evidence": ["fixtures"],
            "signals": {},
        }
    )
    report = lint_bundle(bundle)
    assert any("psl-dir-low" in w and "confidence low" in w for w in report["warnings"])
    summary = build_run_quality_summary(bundle, lint_report=report)
    assert summary["metrics"]["legal_scope_warning_count"] >= 1


def test_lint_invalid_scope_and_missing_proposition() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_scope_links"].append(
        {
            "id": "psl-bad-scope",
            "proposition_id": bundle["propositions"][0]["id"],
            "scope_id": "not-a-real-scope-id",
            "relevance": "direct",
            "inheritance": "explicit",
            "confidence": "high",
            "method": "deterministic",
            "reason": "x",
            "evidence": ["y"],
            "signals": {},
        }
    )
    report = lint_bundle(bundle)
    assert any("invalid scope_id" in e for e in report["errors"])

    bundle_ok = build_demo_bundle(use_llm=False)
    bundle_ok["proposition_scope_links"].append(
        {
            "id": "psl-bad-prop",
            "proposition_id": "missing-prop-id",
            "scope_id": "animal",
            "relevance": "direct",
            "inheritance": "explicit",
            "confidence": "high",
            "method": "deterministic",
            "reason": "x",
            "evidence": ["y"],
            "signals": {},
        }
    )
    report2 = lint_bundle(bundle_ok)
    assert any("missing proposition" in e for e in report2["errors"])


def test_old_bundle_without_scope_files_loads_via_load_exported_bundle(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text('{"id":"run-old-001"}', encoding="utf-8")
    (tmp_path / "sources.json").write_text("[]", encoding="utf-8")
    (tmp_path / "propositions.json").write_text("[]", encoding="utf-8")
    (tmp_path / "divergence_observations.json").write_text("[]", encoding="utf-8")
    (tmp_path / "run_artifacts.json").write_text("[]", encoding="utf-8")

    loaded = load_exported_bundle(tmp_path)
    assert loaded.get("legal_scopes") == []
    assert loaded.get("proposition_scope_links") == []
    report = lint_export_dir(export_dir=tmp_path)
    assert report["run_id"] == "run-old-001"


def test_export_and_ops_api_roundtrip(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    assert (tmp_path / "legal_scopes.json").exists()
    assert (tmp_path / "proposition_scope_links.json").exists()
    assert (tmp_path / "scope_inventory.json").exists()

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("legal_scope_count", 0) >= 10

    root_ls = json.loads((tmp_path / "legal_scopes.json").read_text(encoding="utf-8"))
    assert isinstance(root_ls, list) and len(root_ls) >= 10

    previous_export_dir = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        run_id = str(bundle["run"]["id"])
        ls = client.get("/ops/legal-scopes", params={"run_id": run_id})
        assert ls.status_code == 200
        assert ls.json()["count"] >= 10
        pl = client.get("/ops/proposition-scope-links", params={"run_id": run_id})
        assert pl.status_code == 200
        scoped = client.get(
            "/ops/legal-scopes/animal/propositions",
            params={"run_id": run_id, "include_descendants": "true"},
        )
        assert scoped.status_code == 200
        body = scoped.json()
        assert "proposition_scope_links" in body
        assert body["scope_id"] == "animal"
        scoped_exact = client.get(
            "/ops/legal-scopes/animal/propositions",
            params={"run_id": run_id, "include_descendants": "false"},
        )
        assert scoped_exact.status_code == 200
        assert scoped_exact.json()["allowed_scope_ids"] == ["animal"]
    finally:
        settings.operations_export_dir = previous_export_dir


def test_ops_parent_scope_includes_descendant_propositions(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    store = OperationalStore(export_dir=tmp_path)
    run_id = str(bundle["run"]["id"])
    wide = store.list_propositions_for_scope(
        "animal",
        run_id=run_id,
        include_descendants=True,
    )
    narrow = store.list_propositions_for_scope(
        "animal",
        run_id=run_id,
        include_descendants=False,
    )
    assert wide["link_count"] >= narrow["link_count"]

    equine_rows = store.list_propositions_for_scope("equine", run_id=run_id)
    assert isinstance(equine_rows["allowed_scope_ids"], list)
    assert isinstance(equine_rows["proposition_scope_links"], list)


def test_seed_fixture_path_exists() -> None:
    assert seed_taxonomy_path().exists()
