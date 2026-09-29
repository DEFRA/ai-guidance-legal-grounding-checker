from pathlib import Path
from typing import Any

import law_proposition_extractor_api.main as api_main
from fastapi.testclient import TestClient
from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings


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


def test_api_source_registry_workflow(tmp_path: Path) -> None:
    previous_registry = settings.source_registry_path
    previous_source_cache = settings.source_cache_dir
    previous_derived_cache = settings.derived_cache_dir
    previous_export_dir = settings.operations_export_dir

    settings.source_registry_path = str(tmp_path / "source-registry.json")
    settings.source_cache_dir = str(tmp_path / "source-cache")
    settings.derived_cache_dir = str(tmp_path / "derived-cache")
    settings.operations_export_dir = str(tmp_path / "exported-bundle")
    try:
        client = TestClient(app)

        register_a = client.post(
            "/ops/source-registry/register",
            json={
                "reference": _reference(
                    authority_source_id="eu-source-001",
                    source_id="src-eu-001",
                    jurisdiction="EU",
                    citation="EU-EXAMPLE-001",
                    text=(
                        "Article 10. Operators must maintain a movement register before dispatch. "
                        "The competent authority may inspect the register."
                    ),
                ),
                "refresh": True,
            },
        )
        assert register_a.status_code == 200
        registry_id_a = register_a.json()["registry_id"]

        register_b = client.post(
            "/ops/source-registry/register",
            json={
                "reference": _reference(
                    authority_source_id="uk-source-001",
                    source_id="src-uk-001",
                    jurisdiction="UK",
                    citation="UK-EXAMPLE-001",
                    text=(
                        "Article 10. Operators must maintain a movement register before dispatch. "
                        "The appropriate authority may inspect the register."
                    ),
                ),
                "refresh": True,
            },
        )
        assert register_b.status_code == 200
        registry_id_b = register_b.json()["registry_id"]

        listed = client.get("/ops/source-registry")
        assert listed.status_code == 200
        assert len(listed.json()["sources"]) == 2

        inspected = client.get(f"/ops/source-registry/{registry_id_a}")
        assert inspected.status_code == 200
        assert inspected.json()["registry_id"] == registry_id_a

        refreshed = client.post(f"/ops/source-registry/{registry_id_a}/refresh")
        assert refreshed.status_code == 200
        assert refreshed.json()["current_state"]["source_record"]["id"] == "src-eu-001"

        run_response = client.post(
            "/ops/runs/from-registry",
            json={
                "registry_ids": [registry_id_a, registry_id_b],
                "topic_name": "Registry API run",
                "analysis_mode": "divergence",
                "analysis_scope": "eu_uk",
                "use_llm": False,
            },
        )
        assert run_response.status_code == 200
        assert run_response.json()["run"]["workflow_mode"] == "divergence"
        exported_run_id = str(run_response.json()["run"]["id"])
        runs_payload = client.get("/ops/runs").json()
        indexed = {item["run_id"]: item for item in runs_payload["runs"]}
        assert exported_run_id in indexed
        assert indexed[exported_run_id]["proposition_count"] >= 0
        assert (
            Path(settings.operations_export_dir) / "runs"
        ).exists()
    finally:
        settings.source_registry_path = previous_registry
        settings.source_cache_dir = previous_source_cache
        settings.derived_cache_dir = previous_derived_cache
        settings.operations_export_dir = previous_export_dir


def test_api_run_from_registry_extraction_options_in_trace(tmp_path: Path) -> None:
    previous_registry = settings.source_registry_path
    previous_source_cache = settings.source_cache_dir
    previous_derived_cache = settings.derived_cache_dir
    previous_export_dir = settings.operations_export_dir

    settings.source_registry_path = str(tmp_path / "source-registry.json")
    settings.source_cache_dir = str(tmp_path / "source-cache")
    settings.derived_cache_dir = str(tmp_path / "derived-cache")
    settings.operations_export_dir = str(tmp_path / "exported-bundle")
    try:
        client = TestClient(app)
        reg = client.post(
            "/ops/source-registry/register",
            json={
                "reference": _reference(
                    authority_source_id="eu-source-001",
                    source_id="src-eu-001",
                    jurisdiction="EU",
                    citation="EU-EXAMPLE-001",
                    text=(
                        "Article 10. Operators must maintain a movement register before dispatch. "
                        "The competent authority may inspect the register."
                    ),
                ),
                "refresh": True,
            },
        )
        assert reg.status_code == 200
        registry_id = reg.json()["registry_id"]

        run_response = client.post(
            "/ops/runs/from-registry",
            json={
                "registry_ids": [registry_id],
                "topic_name": "Scoped API run",
                "analysis_mode": "single_jurisdiction",
                "use_llm": False,
                "extraction_mode": "heuristic",
                "max_propositions_per_source": 6,
                "focus_scopes": ["equine", "horse"],
            },
        )
        assert run_response.status_code == 200
        traces = run_response.json().get("stage_traces", [])
        ext = next(t for t in traces if t.get("stage_name") == "proposition extraction")
        assert ext["inputs"]["max_propositions_per_source"] == 6
        assert ext["inputs"]["focus_scopes"] == ["equine", "horse"]
        assert ext["inputs"]["extraction_mode"] == "heuristic"
    finally:
        settings.source_registry_path = previous_registry
        settings.source_cache_dir = previous_source_cache
        settings.derived_cache_dir = previous_derived_cache
        settings.operations_export_dir = previous_export_dir


def test_api_source_registry_search_endpoint() -> None:
    class FakeSearchService:
        def search(
            self,
            *,
            query: str,
            provider: str = "legislation_gov_uk",
            limit: int = 10,
            registry_entries: Any = None,
        ) -> dict[str, Any]:
            assert provider == "legislation_gov_uk"
            assert limit == 8
            return {
                "provider": provider,
                "query": query,
                "count": 1,
                "candidates": [
                    {
                        "title": "Animal Health Law",
                        "citation": "EUR 2016/429",
                        "source_identifier": "eur/2016/429",
                        "authority_source_id": "eur/2016/429",
                        "jurisdiction": "EU",
                        "authority": "legislation_gov_uk",
                        "canonical_source_url": "https://www.legislation.gov.uk/eur/2016/429",
                        "provenance": "search.legislation_gov_uk",
                    }
                ],
            }

    previous_factory = api_main._source_search_service
    api_main._source_search_service = lambda: FakeSearchService()
    try:
        client = TestClient(app)
        response = client.post(
            "/ops/source-registry/search",
            json={"query": "2016/429", "provider": "legislation_gov_uk", "limit": 8},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["candidates"][0]["authority_source_id"] == "eur/2016/429"
    finally:
        api_main._source_search_service = previous_factory


def test_api_source_registry_discover_related(tmp_path: Path) -> None:
    previous_registry = settings.source_registry_path
    previous_source_cache = settings.source_cache_dir

    settings.source_registry_path = str(tmp_path / "source-registry.json")
    settings.source_cache_dir = str(tmp_path / "source-cache")

    try:
        client = TestClient(app)

        register = client.post(
            "/ops/source-registry/register",
            json={
                "reference": _reference(
                    authority_source_id="eur/2016/429",
                    source_id="src-eur-429",
                    jurisdiction="EU",
                    citation="EUR 2016/429",
                    text="Animal health exemplar stub.",
                ),
                "refresh": False,
            },
        )
        assert register.status_code == 200
        registry_id = register.json()["registry_id"]

        discover = client.post(f"/ops/source-registry/{registry_id}/discover-related")
        assert discover.status_code == 200
        body = discover.json()
        ids = [c["id"] for c in body["candidates"]]
        assert "sfc-2016-429-base" in ids
        assert body["target_authority_source_id"] == "eur/2016/429"

    finally:
        settings.source_registry_path = previous_registry
        settings.source_cache_dir = previous_source_cache


def test_api_register_family_candidates_duplicate(tmp_path: Path) -> None:
    previous_registry = settings.source_registry_path
    previous_source_cache = settings.source_cache_dir

    settings.source_registry_path = str(tmp_path / "source-registry.json")
    settings.source_cache_dir = str(tmp_path / "source-cache")

    try:
        client = TestClient(app)

        existing = client.post(
            "/ops/source-registry/register",
            json={
                "reference": {
                    "authority": "legislation_gov_uk",
                    "authority_source_id": "eur/2016/429",
                    "id": "src-eur-2016-429",
                    "title": "Existing",
                    "jurisdiction": "EU",
                    "citation": "EUR 2016/429",
                    "kind": "legislation",
                    "source_url": "https://www.legislation.gov.uk/eur/2016/429/data.xml",
                    "version_id": "latest",
                },
                "refresh": False,
            },
        )
        assert existing.status_code == 200

        target = client.post(
            "/ops/source-registry/register",
            json={
                "reference": _reference(
                    authority_source_id="eur/2016/429",
                    source_id="src-eur-429",
                    jurisdiction="EU",
                    citation="EUR 2016/429",
                    text="Animal health exemplar stub for discovery anchor.",
                ),
                "refresh": False,
            },
        )
        assert target.status_code == 200
        registry_id_target = target.json()["registry_id"]

        response = client.post(
            "/ops/source-registry/register-family-candidates",
            json={
                "target_registry_id": registry_id_target,
                "candidate_ids": ["sfc-2016-429-base"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["registered"] == []
        assert len(body["already_registered"]) == 1
        assert body["already_registered"][0]["candidate_id"] == "sfc-2016-429-base"
    finally:
        settings.source_registry_path = previous_registry
        settings.source_cache_dir = previous_source_cache
