"""Tests for /ops/proposition-groups list + detail."""

import json
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.operations import OperationalStore


def test_proposition_groups_paginated_summaries(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])

    prev = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        r0 = client.get("/ops/proposition-groups", params={"run_id": run_id, "limit": 1, "offset": 0})
        assert r0.status_code == 200
        p0 = r0.json()
        assert p0["run_id"] == run_id
        assert p0["limit"] == 1
        assert p0["offset"] == 0
        assert p0["total_groups"] >= 1
        assert p0["total_rows"] >= 1
        assert len(p0["groups"]) == 1
        g = p0["groups"][0]
        assert "group_id" in g
        assert "row_ids" in g and isinstance(g["row_ids"], list)
        assert "display_label" in g
        dumped = json.dumps(g)
        assert "fragment_text" not in dumped

        r1 = client.get("/ops/proposition-groups", params={"run_id": run_id, "limit": 1, "offset": 1})
        assert r1.status_code == 200
        p1 = r1.json()
        if p0["total_groups"] > 1:
            assert p1["groups"][0]["group_id"] != p0["groups"][0]["group_id"]
    finally:
        settings.operations_export_dir = prev


def test_proposition_groups_scope_equine_filters_server_side(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])

    prev = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        all_gr = client.get("/ops/proposition-groups", params={"run_id": run_id, "limit": 500})
        scoped = client.get(
            "/ops/proposition-groups",
            params={"run_id": run_id, "limit": 500, "scope": "equine"},
        )
        assert all_gr.status_code == 200 and scoped.status_code == 200
        pa = all_gr.json()
        pb = scoped.json()
        assert pb["total_rows"] <= pa["total_rows"]
        assert pb["total_groups"] <= pa["total_groups"]
    finally:
        settings.operations_export_dir = prev


def test_proposition_group_detail_returns_rows(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])

    prev = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        lst = client.get("/ops/proposition-groups", params={"run_id": run_id, "limit": 5})
        gid = lst.json()["groups"][0]["group_id"]

        d = client.get(f"/ops/proposition-groups/{quote(gid, safe='')}", params={"run_id": run_id})
        assert d.status_code == 200
        body = d.json()
        assert body["group_id"] == gid
        assert isinstance(body.get("effective_propositions"), list)
        assert len(body["effective_propositions"]) >= 1
        assert isinstance(body.get("extraction_trace_references"), list)
    finally:
        settings.operations_export_dir = prev


def test_proposition_group_detail_fish_style_group_id() -> None:
    """Fish instrument family keys contain '/' (e.g. 2008/1005); route must use {group_id:path}."""
    fish_export = Path(__file__).resolve().parents[2] / "runs/fish/pilot-principal-frontier-core5-batch-export"
    if not (fish_export / "runs/run-001/manifest.json").is_file():
        return

    prev = settings.operations_export_dir
    settings.operations_export_dir = str(fish_export)
    try:
        client = TestClient(app)
        lst = client.get("/ops/proposition-groups", params={"run_id": "run-001", "limit": 1})
        assert lst.status_code == 200
        gid = lst.json()["groups"][0]["group_id"]
        assert "/" in gid

        d = client.get(f"/ops/proposition-groups/{quote(gid, safe='')}", params={"run_id": "run-001"})
        assert d.status_code == 200
        assert d.json()["group_id"] == gid
        assert len(d.json()["effective_propositions"]) >= 1
    finally:
        settings.operations_export_dir = prev


def test_empty_article_filter_returns_no_groups(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])

    prev = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        absurd = client.get(
            "/ops/proposition-groups",
            params={"run_id": run_id, "article": "zzzznonexistent999", "limit": 50},
        )
        assert absurd.status_code == 200
        assert absurd.json()["total_groups"] == 0
        assert absurd.json()["groups"] == []
    finally:
        settings.operations_export_dir = prev


def test_operational_store_group_totals_match_rows(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    store = OperationalStore(export_dir=tmp_path)
    full = store.list_proposition_groups(run_id=run_id, limit=500, offset=0)
    assert full["total_groups"] >= len(full["groups"])
    assert full["total_rows"] >= 1
