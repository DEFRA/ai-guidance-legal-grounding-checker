from pathlib import Path

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


def test_api_run_job_from_registry_returns_job_id_fast(tmp_path: Path) -> None:
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
                    authority_source_id="eu-x",
                    source_id="src-eu-x",
                    jurisdiction="EU",
                    citation="EU-X",
                    text="Article 1. Example text for registry job test.",
                ),
                "refresh": True,
            },
        )
        assert reg.status_code == 200
        registry_id = reg.json()["registry_id"]

        queued = client.post(
            "/ops/run-jobs/from-registry",
            json={
                "registry_ids": [registry_id],
                "topic_name": "Job API test",
                "analysis_mode": "single_jurisdiction",
                "use_llm": False,
            },
        )
        assert queued.status_code == 200
        body = queued.json()
        assert body.get("status") == "queued"
        job_id = str(body.get("job_id") or "")
        assert job_id

        job_res = client.get(f"/ops/run-jobs/{job_id}")
        assert job_res.status_code == 200
        job = job_res.json()["job"]
        assert job["id"] == job_id

        ev_res = client.get(f"/ops/run-jobs/{job_id}/events")
        assert ev_res.status_code == 200
        events = ev_res.json()["events"]
        assert isinstance(events, list)
        nums = [int(e["sequence_number"]) for e in events]
        assert nums == sorted(nums)

        list_res = client.get("/ops/run-jobs")
        assert list_res.status_code == 200
        assert any(str(j.get("id")) == job_id for j in list_res.json()["jobs"])

        sync = client.post(
            "/ops/runs/from-registry",
            json={
                "registry_ids": [registry_id],
                "topic_name": "Sync still works",
                "analysis_mode": "single_jurisdiction",
                "use_llm": False,
            },
        )
        assert sync.status_code == 200
        assert sync.json().get("run", {}).get("id")
    finally:
        settings.source_registry_path = previous_registry
        settings.source_cache_dir = previous_source_cache
        settings.derived_cache_dir = previous_derived_cache
        settings.operations_export_dir = previous_export_dir


def test_api_run_job_from_registry_accepts_continue_repairable_policy(tmp_path: Path) -> None:
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
                    authority_source_id="eu-y",
                    source_id="src-eu-y",
                    jurisdiction="EU",
                    citation="EU-Y",
                    text="Article 1. Example text for continue_repairable policy test.",
                ),
                "refresh": True,
            },
        )
        assert reg.status_code == 200
        registry_id = reg.json()["registry_id"]

        queued = client.post(
            "/ops/run-jobs/from-registry",
            json={
                "registry_ids": [registry_id],
                "topic_name": "Policy acceptance test",
                "analysis_mode": "single_jurisdiction",
                "use_llm": False,
                "model_error_policy": "continue_repairable",
            },
        )
        assert queued.status_code == 200
        assert queued.json().get("status") == "queued"
    finally:
        settings.source_registry_path = previous_registry
        settings.source_cache_dir = previous_source_cache
        settings.derived_cache_dir = previous_derived_cache
        settings.operations_export_dir = previous_export_dir


def test_api_run_job_not_found(tmp_path: Path) -> None:
    previous_export_dir = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path / "exported-bundle")
    try:
        client = TestClient(app)
        r = client.get("/ops/run-jobs/00000000-0000-0000-0000-000000000099")
        assert r.status_code == 404
    finally:
        settings.operations_export_dir = previous_export_dir


def test_api_run_job_equine_corpus_queues(tmp_path: Path) -> None:
    """POST returns immediately; equine jobs share run-job persistence with registry runs."""
    repo_root = Path(__file__).resolve().parents[2]
    corpus_cfg = repo_root / "examples" / "corpus_equine_law.json"
    assert corpus_cfg.is_file(), f"Missing equine corpus fixture at {corpus_cfg}"

    previous_export_dir = settings.operations_export_dir
    previous_source_cache = settings.source_cache_dir
    previous_derived_cache = settings.derived_cache_dir

    settings.operations_export_dir = str(tmp_path / "exported-bundle")
    settings.source_cache_dir = str(tmp_path / "source-cache")
    settings.derived_cache_dir = str(tmp_path / "derived-cache")
    try:
        client = TestClient(app)
        queued = client.post(
            "/ops/run-jobs/equine-corpus",
            json={"corpus_config_path": str(corpus_cfg), "use_llm": False},
        )
        assert queued.status_code == 200
        body = queued.json()
        assert body.get("status") == "queued"
        job_id = str(body.get("job_id") or "")
        assert job_id

        job_res = client.get(f"/ops/run-jobs/{job_id}")
        assert job_res.status_code == 200
        job = job_res.json()["job"]
        summary = job.get("request_summary") or {}
        assert summary.get("job_kind") == "equine_corpus"

        unsupported = client.post("/ops/run-jobs/equine-corpus", json={"corpus_id": "unknown_corpus"})
        assert unsupported.status_code == 400
    finally:
        settings.operations_export_dir = previous_export_dir
        settings.source_cache_dir = previous_source_cache
        settings.derived_cache_dir = previous_derived_cache
