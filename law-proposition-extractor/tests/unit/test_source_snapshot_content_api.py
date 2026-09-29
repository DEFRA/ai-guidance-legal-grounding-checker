from pathlib import Path

from fastapi.testclient import TestClient
from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle


def test_source_snapshot_list_and_content_endpoints(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    snapshot_id = str(bundle["source_snapshots"][0]["id"])

    previous_export_dir = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)

        listed = client.get("/ops/source-snapshots", params={"run_id": run_id})
        assert listed.status_code == 200
        rows = listed.json()["source_snapshots"]
        assert rows
        assert "authoritative_text" not in rows[0]
        assert rows[0]["has_authoritative_text"] is True
        assert any(row["id"] == snapshot_id for row in rows)

        content = client.get(
            f"/ops/source-snapshots/{snapshot_id}/content",
            params={"run_id": run_id},
        )
        assert content.status_code == 200
        payload = content.json()
        assert payload["available"] is True
        assert payload["snapshot_id"] == snapshot_id
        assert isinstance(payload["content"], str)
        assert payload["content"].strip()

        missing = client.get(
            "/ops/source-snapshots/snap-does-not-exist/content",
            params={"run_id": run_id},
        )
        assert missing.status_code == 404
    finally:
        settings.operations_export_dir = previous_export_dir
