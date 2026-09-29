from pathlib import Path

from law_proposition_extractor_pipeline.sources import SourceRegistryService


def _example_reference() -> dict[str, object]:
    return {
        "authority": "case_file",
        "authority_source_id": "example-eu-001",
        "id": "src-eu-001",
        "title": "Example EU instrument",
        "jurisdiction": "EU",
        "citation": "EU-EXAMPLE-001",
        "kind": "regulation",
        "text": "Article 10. Operators must maintain a movement register before dispatch.",
        "authoritative_locator": "article:10",
        "version_id": "v1",
    }


def test_source_registry_register_refresh_and_build_case_sources(tmp_path: Path) -> None:
    registry = SourceRegistryService(
        registry_path=tmp_path / "source-registry.json",
        source_cache_dir=tmp_path / "source-cache",
    )
    entry = registry.register_reference(reference=_example_reference(), refresh=True)

    assert entry["registry_id"] == "reg-case-file-example-eu-001"
    current_state = entry["current_state"]
    assert isinstance(current_state, dict)
    assert current_state["source_record"]["id"] == "src-eu-001"
    assert current_state["source_snapshot"]["source_record_id"] == "src-eu-001"
    assert current_state["source_fragment"]["source_record_id"] == "src-eu-001"

    listed = registry.list_entries()
    assert len(listed) == 1
    assert listed[0]["registry_id"] == entry["registry_id"]

    refreshed = registry.refresh_reference(registry_id=entry["registry_id"])
    refresh_history = refreshed["refresh_history"]
    assert isinstance(refresh_history, list)
    assert len(refresh_history) >= 2

    case_sources = registry.build_case_sources(registry_ids=[entry["registry_id"]])
    assert len(case_sources) == 1
    assert case_sources[0]["authority"] == "case_file"
    assert case_sources[0]["text"]
