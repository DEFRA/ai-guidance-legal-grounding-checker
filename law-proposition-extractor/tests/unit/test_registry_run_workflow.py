from pathlib import Path

from law_proposition_extractor_pipeline.runner import run_registry_sources
from law_proposition_extractor_pipeline.sources import SourceRegistryService


def _reference(
    *,
    authority_source_id: str,
    source_id: str,
    jurisdiction: str,
    citation: str,
    text: str,
) -> dict[str, object]:
    return {
        "authority": "case_file",
        "authority_source_id": authority_source_id,
        "id": source_id,
        "title": f"{jurisdiction} source",
        "jurisdiction": jurisdiction,
        "citation": citation,
        "kind": "regulation",
        "text": text,
        "authoritative_locator": "article:10",
        "version_id": "v1",
    }


def test_run_registry_sources_supports_divergence_mode(tmp_path: Path) -> None:
    registry_path = tmp_path / "source-registry.json"
    source_cache_dir = tmp_path / "source-cache"
    derived_cache_dir = tmp_path / "derived-cache"
    registry = SourceRegistryService(
        registry_path=registry_path,
        source_cache_dir=source_cache_dir,
    )
    first = registry.register_reference(
        reference=_reference(
            authority_source_id="eu-source-001",
            source_id="src-eu-001",
            jurisdiction="EU",
            citation="EU-EXAMPLE-001",
            text=(
                "Article 10. Operators must maintain a movement register before dispatch. "
                "The competent authority may inspect the register."
            ),
        ),
        refresh=True,
    )
    second = registry.register_reference(
        reference=_reference(
            authority_source_id="uk-source-001",
            source_id="src-uk-001",
            jurisdiction="UK",
            citation="UK-EXAMPLE-001",
            text=(
                "Article 10. Operators must maintain a movement register before dispatch. "
                "The appropriate authority may inspect the register."
            ),
        ),
        refresh=True,
    )

    bundle = run_registry_sources(
        registry_ids=[first["registry_id"], second["registry_id"]],
        topic_name="Registry-backed movement records",
        analysis_mode="divergence",
        analysis_scope="eu_uk",
        source_registry_path=str(registry_path),
        source_cache_dir=str(source_cache_dir),
        derived_cache_dir=str(derived_cache_dir),
        use_llm=False,
    )

    assert bundle["run"]["workflow_mode"] == "divergence"
    assert len(bundle["source_records"]) == 2
    assert len(bundle["propositions"]) >= 2


def test_run_registry_sources_applies_extraction_limits_and_scopes(tmp_path: Path) -> None:
    registry_path = tmp_path / "source-registry.json"
    source_cache_dir = tmp_path / "source-cache"
    derived_cache_dir = tmp_path / "derived-cache"
    registry = SourceRegistryService(
        registry_path=registry_path,
        source_cache_dir=source_cache_dir,
    )
    first = registry.register_reference(
        reference=_reference(
            authority_source_id="eu-source-001",
            source_id="src-eu-001",
            jurisdiction="EU",
            citation="EU-EXAMPLE-001",
            text=(
                "Article 10. Operators must maintain a movement register before dispatch. "
                "The competent authority may inspect the register."
            ),
        ),
        refresh=True,
    )

    bundle = run_registry_sources(
        registry_ids=[first["registry_id"]],
        topic_name="Scoped run",
        analysis_mode="single_jurisdiction",
        source_registry_path=str(registry_path),
        source_cache_dir=str(source_cache_dir),
        derived_cache_dir=str(derived_cache_dir),
        use_llm=False,
        extraction_mode="heuristic",
        focus_scopes=["equine", "horse"],
        max_propositions_per_source=9,
    )

    traces = bundle.get("stage_traces", [])
    ext = next(t for t in traces if t.get("stage_name") == "proposition extraction")
    inputs = ext.get("inputs", {})
    assert inputs.get("max_propositions_per_source") == 9
    assert inputs.get("focus_scopes") == ["equine", "horse"]
    assert inputs.get("extraction_mode") == "heuristic"


def test_run_registry_sources_family_candidates_audit_only(tmp_path: Path) -> None:
    registry_path = tmp_path / "source-registry.json"
    source_cache_dir = tmp_path / "source-cache"
    derived_cache_dir = tmp_path / "derived-cache"
    registry = SourceRegistryService(
        registry_path=registry_path,
        source_cache_dir=source_cache_dir,
    )
    target = registry.register_reference(
        reference={
            "authority": "case_file",
            "authority_source_id": "eur/2016/429",
            "id": "src-eur-429",
            "title": "EU Animal Health",
            "jurisdiction": "EU",
            "citation": "EUR 2016/429",
            "kind": "regulation",
            "text": (
                "Article 10. Operators must maintain a movement register before dispatch. "
                "The competent authority may inspect the register."
            ),
            "authoritative_locator": "article:10",
            "version_id": "v1",
        },
        refresh=True,
    )

    bundle = run_registry_sources(
        registry_ids=[target["registry_id"]],
        topic_name="Family context audit",
        analysis_mode="single_jurisdiction",
        source_registry_path=str(registry_path),
        source_cache_dir=str(source_cache_dir),
        derived_cache_dir=str(derived_cache_dir),
        use_llm=False,
        source_family_selection={
            "registry_id": target["registry_id"],
            "included_candidate_ids": ["sfc-2016-429-guid"],
        },
    )

    assert len(bundle["source_records"]) == 1
    sf = bundle.get("source_family_candidates") or []
    assert len(sf) == 1
    assert sf[0]["id"] == "sfc-2016-429-guid"
