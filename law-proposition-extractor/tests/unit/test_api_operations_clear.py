"""API tests for /ops/dev/clear/* endpoints."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle


def test_ops_dev_clear_runs_dry_run_and_respects_confirm(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_dir = tmp_path / "bundle"
    export_bundle(bundle=bundle, output_dir=str(export_dir))

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"version": "0.1", "sources": [{"registry_id": "from-test"}]}, indent=2),
        encoding="utf-8",
    )

    previous_export = settings.operations_export_dir
    previous_reg = settings.source_registry_path
    settings.operations_export_dir = str(export_dir)
    settings.source_registry_path = str(registry_path)
    try:
        client = TestClient(app)

        dry = client.post("/ops/dev/clear/runs", json={"dry_run": True})
        assert dry.status_code == 200
        assert dry.json()["dry_run"] is True
        assert any(export_dir.rglob("*"))

        bad = client.post(
            "/ops/dev/clear/runs",
            json={"dry_run": False, "confirmation_text": "wrong"},
        )
        assert bad.status_code == 400

        ok = client.post(
            "/ops/dev/clear/runs",
            json={"dry_run": False, "confirmation_text": "CLEAR RUNS"},
        )
        assert ok.status_code == 200
        assert not any(export_dir.iterdir())

        kept = json.loads(registry_path.read_text(encoding="utf-8"))
        assert kept["sources"] == [{"registry_id": "from-test"}]
    finally:
        settings.operations_export_dir = previous_export
        settings.source_registry_path = previous_reg


def test_ops_dev_clear_all_resets_registry(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_dir = tmp_path / "bundle"
    export_bundle(bundle=bundle, output_dir=str(export_dir))

    registry_path = tmp_path / "registry-all.json"
    registry_path.write_text(
        json.dumps({"version": "0.1", "sources": [{"registry_id": "zap"}]}, indent=2),
        encoding="utf-8",
    )
    snapshot_cache = tmp_path / "snap-cache"
    snapshot_cache.mkdir()
    (snapshot_cache / "a.json").write_text("{}", encoding="utf-8")
    derived_cache = tmp_path / "derived-cache"
    derived_cache.mkdir()
    (derived_cache / "b.txt").write_text("x", encoding="utf-8")

    previous_export = settings.operations_export_dir
    previous_reg = settings.source_registry_path
    previous_sc = settings.source_cache_dir
    previous_dd = settings.derived_cache_dir
    settings.operations_export_dir = str(export_dir)
    settings.source_registry_path = str(registry_path)
    settings.source_cache_dir = str(snapshot_cache)
    settings.derived_cache_dir = str(derived_cache)

    try:
        client = TestClient(app)

        dry = client.post("/ops/dev/clear/all", json={"dry_run": True})
        assert dry.status_code == 200
        assert (snapshot_cache / "a.json").exists()

        bad = client.post(
            "/ops/dev/clear/all",
            json={"dry_run": False, "confirmation_text": ""},
        )
        assert bad.status_code == 400

        ok = client.post(
            "/ops/dev/clear/all",
            json={"dry_run": False, "confirmation_text": "CLEAR ALL"},
        )
        assert ok.status_code == 200
        assert ok.json()["registry_reset_written"] is True
        assert not any(export_dir.iterdir())

        emptied = json.loads(registry_path.read_text(encoding="utf-8"))
        assert emptied == {"version": "0.1", "sources": []}
        assert not any(snapshot_cache.iterdir())
        assert not any(derived_cache.iterdir())
    finally:
        settings.operations_export_dir = previous_export
        settings.source_registry_path = previous_reg
        settings.source_cache_dir = previous_sc
        settings.derived_cache_dir = previous_dd
