"""Surface behaviour when the operations export directory has no runs yet."""

from fastapi.testclient import TestClient

from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings


def test_ops_runs_empty_when_export_dir_has_no_runs(tmp_path) -> None:
    previous = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        response = client.get("/ops/runs")
        assert response.status_code == 200
        assert response.json()["runs"] == []
    finally:
        settings.operations_export_dir = previous
