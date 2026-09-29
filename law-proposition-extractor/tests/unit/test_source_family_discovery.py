from pathlib import Path

from law_proposition_extractor_pipeline.linting import load_exported_bundle
from law_proposition_extractor_pipeline.sources.source_family_discovery import (
    candidates_for_included_ids,
    default_discover,
    discover_related_for_registry_entry,
)


def test_regulation_2016_429_fixture_contains_roles() -> None:
    entry = {
        "registry_id": "reg-test",
        "reference": {"authority_source_id": "eur/2016/429", "title": "AHL", "citation": "EUR 2016/429"},
    }
    rows = default_discover(entry)
    roles = {r.source_role for r in rows}
    assert "base_act" in roles
    assert "consolidated_text" in roles
    assert "corrigendum" in roles
    assert "delegated_act" in roles
    assert "implementing_act" in roles
    assert "annex" in roles
    assert "guidance" in roles
    assert "retained_version" in roles
    assert "certificate_model" in roles

    first = next(r for r in rows if r.id == "sfc-2016-429-base")
    assert first.confidence == "high"
    assert first.relationship_to_target == "is_target"
    assert len(first.evidence) >= 1


def test_discover_endpoint_shape() -> None:
    bundle = discover_related_for_registry_entry(
        {
            "registry_id": "x",
            "reference": {"authority_source_id": "eur/2016/429"},
        }
    )
    assert bundle["registry_id"] == "x"
    assert bundle["target_authority_source_id"] == "eur/2016/429"
    assert isinstance(bundle["candidates"], list)
    assert bundle["candidates"][0]["id"]


def test_candidates_for_included_ids_model_roundtrip() -> None:
    disco = discover_related_for_registry_entry(
        {"registry_id": "r", "reference": {"authority_source_id": "eur/2016/429"}}
    )
    raw_list = list(disco["candidates"])
    chosen = candidates_for_included_ids(raw_list, ["sfc-2016-429-base", "sfc-2016-429-guid"])
    assert len(chosen) == 2
    ids = {c.id for c in chosen}
    assert ids == {"sfc-2016-429-base", "sfc-2016-429-guid"}


def test_equine_passport_extension_row_metadata() -> None:
    entry = {
        "registry_id": "reg-test",
        "reference": {"authority_source_id": "eur/2016/429"},
    }
    rows = default_discover(entry)
    eu262 = next(r for r in rows if r.id == "sfc-2015-262-eu-implementing")
    assert eu262.celex == "32015R0262"
    assert eu262.inclusion_status == "candidate_needs_review"
    corr = next(r for r in rows if r.id == "sfc-2015-262-corr-02")
    assert corr.celex == "32015R0262R(02)"
    assert corr.source_role == "corrigendum"
    annex_ids = {r.id for r in rows if str(r.id).startswith("sfc-2015-262-annex")}
    assert annex_ids == {"sfc-2015-262-annex-I", "sfc-2015-262-annex-II"}
    d2035 = next(r for r in rows if r.id == "sfc-2019-2035-delegated")
    i963 = next(r for r in rows if r.id == "sfc-2021-963-implementing")
    assert d2035.inclusion_status == "required_for_scope"
    assert i963.inclusion_status == "required_for_scope"


def test_load_exported_bundle_without_source_family_file(tmp_path: Path) -> None:
    (tmp_path / "sources.json").write_text("[]", encoding="utf-8")
    (tmp_path / "run.json").write_text("{}", encoding="utf-8")
    for name in (
        "source_snapshots.json",
        "source_fragments.json",
        "source_parse_traces.json",
        "source_fetch_metadata.json",
        "source_fetch_attempts.json",
        "source_target_links.json",
        "source_inventory.json",
        "source_categorisation_rationales.json",
        "propositions.json",
        "proposition_extraction_traces.json",
        "divergence_observations.json",
        "divergence_assessments.json",
        "divergence_findings.json",
        "run_artifacts.json",
        "legal_scopes.json",
        "proposition_scope_links.json",
        "scope_inventory.json",
        "scope_review_candidates.json",
    ):
        payload = "{}" if name in {"source_inventory.json", "scope_inventory.json"} else "[]"
        (tmp_path / name).write_text(payload, encoding="utf-8")

    bundle = load_exported_bundle(tmp_path)
    assert bundle.get("source_family_candidates") is None
