"""Tiny frozen corpus + FastAPI app with the worker disabled."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from guidance_relevance_web.app import create_app
from guidance_relevance_web.category import unique_scope
from guidance_relevance_web.settings import Settings
from guidance_relevance_web.store import Store


def _page(
    url: str,
    title: str,
    body: str | None,
    content_id: str = "cid",
    *,
    document_type: str = "guide",
    organisations: list[str] | None = None,
    primary: str | None = None,
) -> dict:
    meta: dict = {"title": title, "body_text": body, "document_type": document_type}
    if organisations is not None:
        meta["organisations"] = organisations
    if primary is not None:
        meta["primary_publishing_organisation"] = primary
    return {"url": url, "content_id": content_id, "meta_data": meta}


def write_snapshot(root: Path, pages: list, built_on: str, *, stamp_scope: bool = True) -> str:
    raw = json.dumps(pages).encode()
    digest = sha256(raw).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    (root / "with_body.json").write_bytes(raw)
    payload: dict = {
        "built_on": built_on,
        "n_pages": len(pages),
        "with_body_sha256": digest,
    }
    if stamp_scope:
        orgs, types = unique_scope(pages)
        payload["organisations"] = orgs
        payload["document_types"] = types
    (root / "MANIFEST.json").write_text(json.dumps(payload))
    return digest


def _default_pages() -> list:
    return [
        _page(
            "https://www.gov.uk/guidance/storing-slurry",
            "Storing slurry",
            "Rules for slurry stores and lagoons.",
            organisations=["environment-agency"],
            primary="environment-agency",
        ),
        _page(
            "https://www.gov.uk/guidance/fishing-quota",
            "Fishing quota",
            "Catch certificates for fishery products.",
            organisations=["department-for-environment-food-rural-affairs"],
            primary="department-for-environment-food-rural-affairs",
        ),
        _page(
            "https://www.gov.uk/guidance/empty",
            "Empty",
            "",
            document_type="detailed_guide",
        ),
        _page("https://www.gov.uk/guidance/missing", "Missing", None),
    ]


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    write_snapshot(root, _default_pages(), "2026-09-08")
    return root


@pytest.fixture
def library_dir(tmp_path: Path) -> dict:
    """Legacy flat 4-page snapshot + a newer 1-page child (fish only)."""
    root = tmp_path / "library"
    root.mkdir()
    old_sha = write_snapshot(root, _default_pages(), "2026-09-08")
    new_pages = [
        _page(
            "https://www.gov.uk/guidance/fishing-quota",
            "Fishing quota",
            "Catch certificates for fishery products.",
            organisations=["department-for-environment-food-rural-affairs"],
            primary="department-for-environment-food-rural-affairs",
        ),
    ]
    new_root = root / "2026-09-10-new"
    new_sha = write_snapshot(new_root, new_pages, "2026-09-10")
    return {
        "root": root,
        "old_sha": old_sha,
        "new_sha": new_sha,
        "new_root": new_root,
    }


def _settings_for(tmp_path: Path, corpus: Path, jobs_name: str = "jobs") -> Settings:
    jobs = tmp_path / jobs_name
    jobs.mkdir(exist_ok=True)
    return Settings(
        grf_corpus=corpus,
        grf_jobs=jobs,
        grf_max_routed=650,
        grf_daily_max_routed=2000,
        grf_enable_worker=False,
        grf_llm_mode="batch",
        grf_public_base_url="http://testserver",
        mail_url=None,
        mail_from="noreply@test",
        anthropic_api_key="sk-test",
    )


@pytest.fixture
def settings(tmp_path: Path, corpus_dir: Path) -> Settings:
    return _settings_for(tmp_path, corpus_dir)


@pytest.fixture
def library_settings(tmp_path: Path, library_dir: dict) -> Settings:
    return _settings_for(tmp_path, library_dir["root"], "library-jobs")


@pytest.fixture
def library_client(library_settings: Settings):
    from fastapi.testclient import TestClient
    with TestClient(create_app(library_settings)) as c:
        yield c


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture
def store(settings: Settings) -> Store:
    return Store(settings)
