import json
from pathlib import Path

import pytest
from guidance_relevance_filter.classify import classify
from guidance_relevance_filter.narrowing import StemIndex

from guidance_relevance_web.corpus import Corpus, CorpusCatalog, CorpusError
from guidance_relevance_web.cost_estimate import estimate_usd
from guidance_relevance_web.mailer import Mailer
from guidance_relevance_web.settings import Settings
from guidance_relevance_web.store import Store
from guidance_relevance_web.worker import (
    claim_and_run,
    cli_command,
    cli_env,
    corpus_path_for_job,
    finalize,
    full_corpus_for_job,
    stem_index_path_for_job,
    sweep_job,
)

SLURRY_BODY = {
    "name": "slurry",
    "description": "slurry storage",
    "exclusion_criteria": "not sewage",
    "keep_hints": "",
    "drop_hints": "",
    "lexicon": "slurry\nlagoon",
}


def _preview_events(client, body=SLURRY_BODY):
    res = client.post("/preview", json=body)
    assert res.status_code == 200, res.text
    events = [json.loads(line) for line in res.text.splitlines() if line.strip()]
    assert events, res.text
    return events


def _preview_done(client, body=SLURRY_BODY):
    events = _preview_events(client, body)
    done = next(e for e in reversed(events) if e.get("event") == "done")
    return done, events


def test_health_and_wizard(client):
    assert client.get("/health").json()["status"] == "ok"
    html = client.get("/").text
    assert "Create New Category" in html
    assert "Categories" in html
    assert 'href="/jobs"' in html
    assert "2026-09-08" in html
    assert "1 snapshot" in html
    assert "newest 8 September 2026" in html
    assert 'id="corpus_id"' in html
    assert "Which version of GOV.UK to search" in html
    assert "Start from an example" in html
    assert "Your email address" in html
    assert "Name for this category" in html
    assert "What to Include" in html
    assert "What to Exclude" in html
    assert "Inclusion Keyword(s)" in html
    assert "Page Types" in html
    assert "Examples of tricky pages" in html
    assert "Preview and Wordsearch" in html
    assert "How to write this well" in html
    assert "An example of what good looks like" in html
    assert "govuk-frontend-6.5.0.min.css" in html
    assert "/static/app.js?v=" in html
    assert "/static/style.css?v=" in html
    assert "govuk-generic-header" in html
    assert 'id="organisations"' in html
    assert 'id="organisations-filter"' in html
    assert 'id="organisations-selected"' in html
    assert "Selected organisations" in html
    assert "Clear all" in html
    assert 'id="document_types"' in html
    assert 'data-module="govuk-checkboxes"' in html
    assert 'name="organisations"' in html
    assert 'name="document_types"' in html
    assert 'value="environment-agency"' in html
    assert 'value="department-for-environment-food-rural-affairs"' in html
    assert "defra" in html
    assert 'value="guide"' in html
    assert 'value="detailed_guide"' in html
    type_list = html.split('id="document_types-list"', 1)[1].split(
        'id="group-lexicon"', 1,
    )[0]
    assert 'value="html_publication"' not in type_list
    assert "Tick none" in html
    assert 'id="document_types-list"' in html
    assert 'id="snapshots-data"' in html
    assert "How this narrows your search" in html
    assert "govuk-tabs" in html
    assert 'href="#definition"' in html
    assert 'href="#preview-run"' in html
    assert "Preview and run" in html
    assert "How to run the model" in html
    assert 'id="llm_mode-batch"' in html
    assert 'id="llm_mode-sync"' in html
    assert "checked" in html.split('id="llm_mode-batch"', 1)[1].split(">", 1)[0]
    assert "checked" not in html.split('id="llm_mode-sync"', 1)[1].split(">", 1)[0]
    assert "Batch (recommended)" in html
    assert "Synchronous mode costs twice as much as batch" in html
    assert 'href="#results"' in html
    assert ">Results<" in html
    assert "Run the filter to see results here" in html
    assert 'id="job-status-tag"' not in html
    js = client.get("/static/app.js").text
    assert 'filterId: "organisations-filter"' in js
    assert 'selectedId: "organisations-selected"' in js
    assert "function renderSelected" in js
    assert "scope-selected__chip" in js
    assert "applySnapshotScope" in js
    assert "/jobs/${data.id}#results" in js
    assert "function selectedLlmMode" in js
    assert "cost_estimate_sync" in js
    assert "llm_mode: selectedLlmMode()" in js
    assert '$("job-funnel")' in js
    assert "How we used Inference to filter the pages for relevance" in js
    assert "How we used wordsearch to shortlist pages for inference" in js
    assert "Stage 1: Input Shortlist" in js
    assert "Stage 1: Organisation" in js
    assert "Filtered by Organisation, Document Type and Keywords" in js
    assert "Stage 2: Filtered by LLM Inclusion Rules" in js
    assert "Generous to include as many relevant pages as possible" in js
    assert "Stage 3: Filtered by LLM Exclusion Rules" in js
    assert "Use rules to exclude irrelevant pages from Stage 2" in js
    assert "funnel-story__card" in js
    assert "funnel-story__bar" in js
    assert "funnel-story__cards" in js
    assert "function storyCardLabel" in js
    assert "function previewStoryStages" in js
    assert "Which terms matched" in js
    assert "function defaultStage" in js
    assert 'bar.style.background = colorOf(n.id)' in js
    assert 'document_type_pass: "#4c2c92"' in js
    assert 'would_route: "#00703c"' in js
    css_text = client.get("/static/style.css").text
    assert css_text.count(".scope-picker-list .govuk-checkboxes__item[hidden]")
    assert ".scope-selected" in css_text
    assert ".scope-selected__chip" in css_text
    assert ".funnel-story__bar" in css_text
    assert ".funnel-story__card" in css_text
    assert ".funnel-story__card--muted" in css_text
    assert "grid-template-rows: subgrid" in css_text
    assert "--funnel-cols" in css_text
    assert ".term-rank" in css_text
    assert ".term-rank__bar" in css_text
    assert ".wizard-tabs-form" in css_text
    assert "display: contents" in css_text
    css = client.get("/static/govuk/govuk-frontend-6.5.0.min.css")
    assert css.status_code == 200
    fonts = client.get("/assets/fonts/light-94a07e06a1-v2.woff2")
    assert fonts.status_code == 200


def test_preview_validation_uses_spec_field_names(client):
    res = client.post("/preview", json={**SLURRY_BODY, "description": "  "})
    assert res.status_code == 400
    assert res.json()["detail"] == "What to Include is required"
    res = client.post("/preview", json={**SLURRY_BODY, "exclusion_criteria": ""})
    assert res.status_code == 400
    assert res.json()["detail"] == "What to Exclude is required"
    res = client.post("/preview", json={**SLURRY_BODY, "lexicon": "# comment only\n"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Inclusion keywords must contain at least one term"


def test_job_rejects_invalid_email(client):
    body, _events = _preview_done(client)
    created = client.post(
        "/jobs", json={"preview_id": body["preview_id"], "email": "not-an-email"},
    )
    assert created.status_code == 400
    assert created.json()["detail"] == "Please enter a valid email address"


def test_job_defaults_llm_mode_batch_and_rejects_invalid(client, settings):
    body, _events = _preview_done(client)
    created = client.post(
        "/jobs", json={"preview_id": body["preview_id"], "email": "a@b.co.uk"},
    )
    assert created.status_code == 202
    job = Store(settings).get(created.json()["id"])
    assert job.read_meta()["llm_mode"] == "batch"
    cmd = cli_command(settings, job, Path("unused.json"))
    assert "--sync" not in cmd

    bad = client.post(
        "/jobs",
        json={
            "preview_id": body["preview_id"],
            "email": "a@b.co.uk",
            "llm_mode": "turbo",
        },
    )
    assert bad.status_code == 422


def test_job_persists_sync_llm_mode(client, settings):
    body, _events = _preview_done(client)
    created = client.post(
        "/jobs",
        json={
            "preview_id": body["preview_id"],
            "email": "a@b.co.uk",
            "llm_mode": "sync",
        },
    )
    assert created.status_code == 202
    job_id = created.json()["id"]
    job = Store(settings).get(job_id)
    assert job.read_meta()["llm_mode"] == "sync"
    view = client.get(f"/api/jobs/{job_id}").json()
    assert view["llm_mode"] == "sync"
    assert view["cost_estimate"]["usd"] == estimate_usd(1, batch=False)["usd"]
    assert "1×" in view["cost_estimate"]["html"]
    html = client.get(f"/jobs/{job_id}").text
    assert "Synchronous 1×" in html
    assert "govuk-tag--red" in html.split('id="job-llm-mode"', 1)[1].split("</dd>", 1)[0]


def test_preview_and_job_queue(client, settings):
    body, events = _preview_done(client)
    assert [e["event"] for e in events if e["event"] == "progress"]
    assert {e["phase"] for e in events if e["event"] == "progress"} >= {"scan", "wordsearch"}
    assert body["cached"] is False
    assert body["counts"]["would_route"] == 1
    routed = next(n for n in body["sankey"]["nodes"] if n["id"] == "would_route")
    assert routed["urls"][0]["lexicon_hits"]
    assert routed["term_hits"]
    assert body["cap"]["ok"] is True
    assert body["cost_estimate"]["would_route"] == 1
    assert "$" in body["cost_estimate"]["summary"]
    assert "0.5×" in body["cost_estimate"]["html"]
    assert "1×" in body["cost_estimate_sync"]["html"]
    assert "0.5×" not in body["cost_estimate_sync"]["html"]
    assert body["cost_estimate_sync"]["usd"] == estimate_usd(1, batch=False)["usd"]
    preview_id = body["preview_id"]

    created = client.post("/jobs", json={"preview_id": preview_id, "email": "a@b.co.uk"})
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]
    view = client.get(f"/api/jobs/{job_id}").json()
    assert view["status"] == "queued"
    assert "email" not in view
    meta = Store(settings).get(job_id).read_meta()
    assert meta["corpus_built_on"] == "2026-09-08"
    assert meta["corpus_n_pages"] == 4
    assert meta["corpus_sha256"]
    assert meta["llm_mode"] == "batch"
    assert view["llm_mode"] == "batch"
    assert view["corpus"] == "8 September 2026 · 4 pages"
    assert view["progress"]["visible"] is True
    assert view["progress"]["step"] == 1
    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    html = page.text
    assert "a@b.co.uk" not in html
    assert "Slurry — Run" in html
    assert f"Job {job_id}" in html
    assert 'href="#definition"' in html
    assert 'href="#preview-run"' in html
    assert 'href="#results"' in html
    assert "govuk-tabs__list-item--selected" in html.split('href="#results"', 1)[0]
    assert 'id="job-funnel"' in html
    name_attrs = html.split('id="name"', 1)[1].split(">", 1)[0]
    assert 'value="slurry"' in name_attrs
    assert "slurry storage" in html.split('id="description"', 1)[1].split("</textarea>", 1)[0]
    assert "not sewage" in html.split('id="exclusion_criteria"', 1)[1].split("</textarea>", 1)[0]
    assert "lagoon" in html.split('id="lexicon"', 1)[1].split("</textarea>", 1)[0]
    assert '<section id="job-progress" class="job-progress">' in html
    assert "Preparing the shortlist…" in html
    assert "Input shortlist" in html
    assert "<pre" not in html.split(">Funnel<", 1)[0]
    assert "Technical log" in html
    assert 'id="job-log-details" open' not in html
    assert "job-status-phase" not in html
    assert "Batch 0.5×" in html
    assert "Synchronous 1×" not in html.split('id="job-llm-mode"', 1)[1].split("</dd>", 1)[0]


def test_preview_second_call_reuses_wordsearch_cache(client):
    first, events = _preview_done(client)
    assert first["cached"] is False
    assert {e["phase"] for e in events if e["event"] == "progress"} >= {"scan", "wordsearch"}
    second, events2 = _preview_done(client)
    assert second["cached"] is True
    assert second["counts"] == first["counts"]
    assert not any(e.get("event") == "progress" for e in events2)
    changed = {**SLURRY_BODY, "description": "a different inclusion spec"}
    third, _ = _preview_done(client, body=changed)
    assert third["cached"] is True


def test_rejects_over_max_routed(client, settings):
    settings.grf_max_routed = 0
    # settings object is already bound into the app; mutate the app copy
    client.app.state.settings.grf_max_routed = 0
    body, _events = _preview_done(client)
    assert body["cap"]["ok"] is False
    created = client.post(
        "/jobs", json={"preview_id": body["preview_id"], "email": "a@b.co.uk"},
    )
    assert created.status_code == 400


def test_worker_finalize_mails_once(settings, monkeypatch, corpus_dir):
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=1,
    )
    (job.output_dir / "output.json").write_text("[]\n")
    (job.output_dir / "metrics.json").write_text(json.dumps({"capped": False}))
    mailer = Mailer(settings)
    finalize(job, store, mailer, settings, 0)
    assert job.read_status()["status"] == "done"
    assert job.read_status().get("email_sent_at")
    assert "op@example.gov.uk" in (job.root / "mail.log").read_text()
    mailer.send(job, subject="again", body="nope")
    assert (job.root / "mail.log").read_text().count("Subject:") == 1


def test_cli_command_paths_survive_job_cwd(tmp_path, monkeypatch):
    """Worker Popen cwd is the job dir; relative GRF_JOBS paths must still exist."""
    monkeypatch.chdir(tmp_path)
    jobs = Path("data/jobs")
    jobs.mkdir(parents=True)
    corpus = Path("data/corpus/with_body.json")
    corpus.parent.mkdir(parents=True)
    corpus.write_text("[]\n")
    settings = Settings(grf_jobs=jobs, grf_corpus=corpus.parent, grf_enable_worker=False)
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=1,
    )
    cmd = cli_command(settings, job, corpus)
    cats = Path(cmd[cmd.index("--categories") + 1])
    lex = Path(cmd[cmd.index("--lexicon") + 1])
    input_path = Path(cmd[cmd.index("run") + 1])
    output_dir = Path(cmd[cmd.index("run") + 2])
    assert cats.is_absolute() and cats.is_file()
    assert lex.is_absolute() and lex.is_file()
    assert input_path.is_absolute() and input_path.is_file()
    assert output_dir.is_absolute() and output_dir.is_dir()
    assert "--sync" not in cmd
    monkeypatch.chdir(job.root)
    assert cats.is_file()
    assert lex.is_file()
    assert input_path.is_file()


def test_cli_command_appends_sync_flags(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jobs = Path("data/jobs")
    jobs.mkdir(parents=True)
    corpus = Path("data/corpus/with_body.json")
    corpus.parent.mkdir(parents=True)
    corpus.write_text("[]\n")
    settings = Settings(
        grf_jobs=jobs, grf_corpus=corpus.parent, grf_enable_worker=False,
        grf_llm_mode="sync", grf_sync_concurrency=7,
    )
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=1,
        llm_mode="sync",
    )
    cmd = cli_command(settings, job, corpus)
    assert "--sync" in cmd
    assert cmd[cmd.index("--concurrency") + 1] == "7"


def test_cli_command_prefers_job_meta_over_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jobs = Path("data/jobs")
    jobs.mkdir(parents=True)
    corpus = Path("data/corpus/with_body.json")
    corpus.parent.mkdir(parents=True)
    corpus.write_text("[]\n")
    settings = Settings(
        grf_jobs=jobs, grf_corpus=corpus.parent, grf_enable_worker=False,
        grf_llm_mode="sync", grf_sync_concurrency=7,
    )
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=1,
        llm_mode="batch",
    )
    assert "--sync" not in cli_command(settings, job, corpus)


def test_cli_command_falls_back_to_settings_when_meta_omits_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jobs = Path("data/jobs")
    jobs.mkdir(parents=True)
    corpus = Path("data/corpus/with_body.json")
    corpus.parent.mkdir(parents=True)
    corpus.write_text("[]\n")
    settings = Settings(
        grf_jobs=jobs, grf_corpus=corpus.parent, grf_enable_worker=False,
        grf_llm_mode="sync", grf_sync_concurrency=4,
    )
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=1,
    )
    meta = job.read_meta()
    meta.pop("llm_mode")
    (job.root / "meta.json").write_text(json.dumps(meta) + "\n")
    cmd = cli_command(settings, job, corpus)
    assert "--sync" in cmd
    assert cmd[cmd.index("--concurrency") + 1] == "4"


def test_claim_runs_cli(settings, monkeypatch, corpus_dir):
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=3,
    )
    calls: list[list[str]] = []

    def fake_run_cli(s, j, pages, stem_index=None):
        calls.append(["run"])
        (j.output_dir / "output.json").write_text("[]\n")
        (j.output_dir / "metrics.json").write_text("{}")
        j.write_status(status="running", pid=None)
        return 0

    monkeypatch.setattr("guidance_relevance_web.worker.run_cli", fake_run_cli)
    mailer = Mailer(settings)
    assert claim_and_run(store, settings, mailer, corpus_dir / "with_body.json") is True
    assert calls == [["run"]]
    assert store.routed_submitted_today() == 3
    assert job.read_status()["status"] == "done"


def test_claim_refunds_budget_if_cli_never_starts(settings, monkeypatch, corpus_dir):
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=546,
    )

    def fake_run_cli(s, j, pages, stem_index=None):
        j.write_status(status="running", pid=None)
        return 2

    monkeypatch.setattr("guidance_relevance_web.worker.run_cli", fake_run_cli)
    mailer = Mailer(settings)
    assert claim_and_run(store, settings, mailer, corpus_dir / "with_body.json") is True
    assert store.routed_submitted_today() == 0
    assert job.read_status()["status"] == "failed"


def test_preview_scope_filters_and_job_corpus_slice(client, settings, corpus_dir):
    body, _ = _preview_done(
        client,
        body={**SLURRY_BODY, "organisations": "environment-agency"},
    )
    assert body["counts"]["input_pages"] == 1
    assert body["counts"]["would_route"] == 1
    assert [n["id"] for n in body["sankey"]["nodes"]] == [
        "organisation_pass", "would_route",
    ]
    preview_id = body["preview_id"]
    created = client.post("/jobs", json={"preview_id": preview_id, "email": "a@b.co.uk"})
    assert created.status_code == 202, created.text
    store = Store(settings)
    job = store.get(created.json()["id"])
    assert job.read_meta()["organisations"] == ["environment-agency"]
    scope = job.read_scope()
    assert scope["counts"]["organisation_miss"] == 3
    assert scope["counts"]["organisation_filter"] is True
    page = client.get(f"/jobs/{created.json()['id']}")
    assert "environment-agency" in page.text
    org_input = page.text.split('id="organisations-environment-agency"', 1)[1].split(">", 1)[0]
    assert "checked" in org_input
    sliced = corpus_path_for_job(job, corpus_dir / "with_body.json")
    assert sliced == job.root / "corpus.json"
    pages = json.loads(sliced.read_text())
    assert [p["url"] for p in pages] == ["https://www.gov.uk/guidance/storing-slurry"]


def test_preview_organisations_array(client):
    body, _ = _preview_done(
        client,
        body={**SLURRY_BODY, "organisations": ["environment-agency"]},
    )
    assert body["counts"]["organisation_filter"] is True
    assert body["counts"]["input_pages"] == 1


def test_preview_document_types_array_or_csv(client):
    listed, _ = _preview_done(client, body={**SLURRY_BODY, "document_types": ["guide"]})
    assert listed["counts"]["document_type_filter"] is True
    assert listed["counts"]["input_pages"] == 3
    csv, _ = _preview_done(client, body={**SLURRY_BODY, "document_types": "detailed_guide"})
    assert csv["counts"]["document_type_filter"] is True
    assert csv["counts"]["input_pages"] == 1
    assert csv["counts"]["would_route"] == 0


def test_sliced_job_reuses_full_stem_index(client, settings, corpus_dir, monkeypatch):
    corpus = Corpus(corpus_dir)
    full = corpus.ensure_stem_index()
    snapshot_sqlite = full.path

    body, _ = _preview_done(
        client,
        body={**SLURRY_BODY, "organisations": "environment-agency"},
    )
    created = client.post("/jobs", json={"preview_id": body["preview_id"], "email": "a@b.co.uk"})
    job = Store(settings).get(created.json()["id"])
    sliced = corpus_path_for_job(job, corpus_dir / "with_body.json")
    assert sliced == job.root / "corpus.json"
    assert not (job.root / "stem_index").exists()
    index_path = stem_index_path_for_job(
        job, corpus_dir / "with_body.json", corpus_dir / "with_body.json",
    )
    assert index_path == snapshot_sqlite
    cmd = cli_command(settings, job, sliced, stem_index=index_path)
    assert cmd[cmd.index("--stem-index") + 1] == str(index_path.resolve())
    assert snapshot_sqlite.is_file()

    def boom(_text):
        raise AssertionError("stem_index should not run when the inverted index is used")

    monkeypatch.setattr("guidance_relevance_filter.classify.stem_index", boom)
    pages = json.loads(sliced.read_text())
    categories = json.loads((job.root / "categories.json").read_text())
    lexicons = json.loads((job.root / "lexicon.json").read_text())
    loaded = StemIndex.open(index_path, corpus.require().with_body_sha256)
    assert loaded is not None
    results, stats = classify(
        loaded.items_for_urls([p["url"] for p in pages]),
        categories, lexicons, score_only=True, stem_index_db=loaded,
    )
    assert stats["n_routed"] == 1
    assert results[0]["url"] == "https://www.gov.uk/guidance/storing-slurry"
    loaded.close()


def test_xlsx_download_and_upload(client, settings):
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=1,
    )
    pages = [
        {
            "url": "https://www.gov.uk/guidance/keep",
            "content_id": "c1",
            "meta_data": {
                "title": "Keep",
                "labels": {"slurry": True},
                "funnel": {"stage": "pass2_keep"},
            },
        }
    ]
    (job.output_dir / "output.json").write_text(json.dumps(pages))
    (job.output_dir / "funnel.json").write_text("{}")
    job.write_status(status="done")
    zipped = client.get(f"/jobs/{job.id}/download.zip")
    assert zipped.status_code == 200
    assert zipped.headers["content-type"].startswith("application/zip")
    xlsx = client.get(f"/jobs/{job.id}/pages.xlsx")
    assert xlsx.status_code == 200
    uploaded = client.post(
        f"/jobs/{job.id}/pages",
        files={
            "file": (
                "pages.xlsx",
                xlsx.content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["n_pages"] == 1
    assert body["n_added"] == 0
    written = json.loads((job.root / "pages.json").read_text())
    assert written["pages"][0]["url"] == "https://www.gov.uk/guidance/keep"


def test_job_page_shows_cost_from_metrics(client, settings):
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=544,
    )
    (job.output_dir / "metrics.json").write_text(json.dumps({
        "cost_usd": 3.3508,
        "capped": False,
        "tokens": {"input": 4175991, "output": 86747},
        "pass1": {
            "model": "claude-haiku-4-5-20251001",
            "n_routed": 544,
            "cost_usd": 1.8472,
        },
        "pass2": {
            "model": "claude-sonnet-4-6",
            "n_positives": 178,
            "cost_usd": 1.5036,
        },
    }))
    job.write_status(status="done")
    view = client.get(f"/api/jobs/{job.id}").json()
    assert view["cost"]["usd"] == 3.3508
    assert view["cost"]["label"] == "$3.3508"
    assert view["cost"]["detail"] == (
        "$3.3508 — $1.8472 pass 1 Haiku (544 pages) · $1.5036 pass 2 Sonnet (178 pages)"
    )
    page = client.get(f"/jobs/{job.id}")
    assert page.status_code == 200
    assert "$3.3508 — $1.8472 pass 1 Haiku (544 pages) · $1.5036 pass 2 Sonnet (178 pages)" in page.text
    assert "0.5×" not in page.text.split('id="job-cost"', 1)[1].split("</dd>", 1)[0]


def test_queued_job_shows_cost_estimate(client, settings):
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=544,
    )
    view = client.get(f"/api/jobs/{job.id}").json()
    assert view["cost"] is None
    assert view["cost_estimate"]["usd"] == 3.35
    assert view["llm_mode"] == "batch"
    page = client.get(f"/jobs/{job.id}")
    assert "$3.35" in page.text
    assert "$1.66–$6.22" in page.text
    assert "0.5×" in page.text
    assert "Not a quote" in page.text
    assert "Batch 0.5×" in page.text


def test_job_page_summary_fields(client, settings):
    store = Store(settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{
            "name": "slurry_small_test",
            "title": "Animal Liquid Waste",
            "description": "d",
            "exclusion_criteria": "e",
        }],
        lexicons={"slurry_small_test": [
            "slurry", "digestate", "manure", "dirty water",
            "silage effluent", "livestock waste", "nutrient management",
        ]},
        would_route=30,
        organisations=[
            "department-for-environment-food-rural-affairs",
            "environment-agency",
            "rural-payments-agency",
            "natural-england",
        ],
        document_types=[
            "detailed_guide", "guidance", "statutory_guidance", "form", "notice",
        ],
    )
    _set_created(job, "2026-09-10T14:32:00+00:00")
    (job.output_dir / "metrics.json").write_text(json.dumps({
        "cost_usd": 0.8036,
        "pass1": {
            "model": "claude-haiku-4-5-20251001",
            "n_routed": 30,
            "cost_usd": 0.0642,
        },
        "pass2": {
            "model": "claude-sonnet-4-6",
            "n_positives": 30,
            "cost_usd": 0.7394,
        },
    }))
    job.write_status(status="done")
    html = client.get(f"/jobs/{job.id}").text
    assert "Animal Liquid Waste — Run 10 September 2026, 14:32" in html
    assert f"Job {job.id}" in html
    assert "Animal Liquid Waste (slurry_small_test)" in html
    assert ">Organisations<" in html
    assert (
        "department-for-environment-food-rural-affairs, environment-agency, "
        "rural-payments-agency, natural-england"
    ) in html
    assert ">Document types<" in html
    assert "detailed_guide, guidance, statutory_guidance, form, notice" in html
    assert ">Keywords<" in html
    assert (
        "slurry, digestate, manure, dirty water, silage effluent, "
        "livestock waste, nutrient management"
    ) in html
    assert (
        "$0.8036 — $0.0642 pass 1 Haiku (30 pages) · $0.7394 pass 2 Sonnet (30 pages)"
    ) in html
    assert "Would route" not in html
    assert "Duration" not in html
    assert ">Index<" not in html
    assert html.count(">Done<") == 1
    assert "done / done" not in html
    assert "job-status-phase" not in html
    assert "<pre" not in html.split(">Funnel<", 1)[0]
    assert '<section id="job-progress" class="job-progress" hidden>' in html
    assert "Technical log" in html
    assert 'id="job-log-details" open' not in html


def test_running_pass1_job_page_marks_inclusion_step(client, store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=10,
    )
    job.write_status(status="running")
    (job.output_dir / "checkpoint.json").write_text(json.dumps({
        "pass1": {"batch_id": "msgbatch_1"},
    }) + "\n")
    html = client.get(f"/jobs/{job.id}").text
    assert "Reading pages (inclusion rules)…" in html
    assert 'job-steps__item job-steps__item--done" data-step="1"' in html
    assert 'job-steps__item job-steps__item--current" data-step="2"' in html
    assert 'job-steps__item job-steps__item--pending" data-step="3"' in html
    assert 'aria-valuenow="66"' in html
    assert "<pre" not in html.split(">Funnel<", 1)[0]
    assert 'id="job-log-details" open' not in html


def test_failed_job_page_shows_error_and_open_log(client, store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=10,
    )
    job.write_status(status="failed", error="guidance-relevance-filter exited 1")
    job.run_log.write_text("cli boom\n")
    html = client.get(f"/jobs/{job.id}").text
    assert "<pre" not in html.split(">Funnel<", 1)[0]
    assert '<section id="job-progress" class="job-progress" hidden>' in html
    assert 'id="job-error"' in html
    assert "guidance-relevance-filter exited 1" in html
    assert 'id="job-log-details" open' in html
    assert "Technical log" in html
    assert "cli boom" in html
    assert f'action="/jobs/{job.id}/retry"' in html


def _set_created(job, when: str) -> None:
    meta = json.loads((job.root / "meta.json").read_text())
    meta["created_at"] = when
    (job.root / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")


def test_jobs_index_empty(client):
    page = client.get("/jobs")
    assert page.status_code == 200
    html = page.text
    assert "No runs yet" in html
    assert 'href="/jobs"' in html
    assert "Categories" in html
    assert "Create category" in html


def test_jobs_index_lists_runs_newest_first(client, settings):
    store = Store(settings)
    queued = store.create_job(
        email="secret-owner@example.gov.uk",
        categories=[{"name": "fishing", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"fishing": ["quota"]},
        would_route=10,
    )
    done = store.create_job(
        email="secret-owner@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=544,
        organisations=["environment-agency"],
    )
    (done.output_dir / "metrics.json").write_text(json.dumps({
        "cost_usd": 3.3508,
        "capped": False,
        "elapsed_seconds": 75,
        "pass1": {
            "model": "claude-haiku-4-5-20251001",
            "n_routed": 544,
            "cost_usd": 1.8472,
            "batch_meta": {"elapsed_seconds": 40},
        },
        "pass2": {
            "model": "claude-sonnet-4-6",
            "n_positives": 178,
            "cost_usd": 1.5036,
            "batch_meta": {"elapsed_seconds": 20},
        },
        "funnel": {
            "lexicon_hit": {"n": 544},
            "pass1_true": {"n": 178},
            "pass2_kept": {"n": 133},
            "final_true": {"n": 133},
        },
    }))
    done.write_status(status="done")
    _set_created(queued, "2026-09-01T10:00:00+00:00")
    _set_created(done, "2026-09-10T14:15:00+00:00")
    broken = store.jobs_dir / "broken"
    broken.mkdir()
    (broken / "meta.json").write_text("{")

    page = client.get("/jobs")
    assert page.status_code == 200
    html = page.text
    assert "secret-owner@example.gov.uk" not in html
    assert html.index("slurry") < html.index("fishing")
    assert f'href="/jobs/{done.id}"' in html
    assert f'href="/jobs/{queued.id}"' in html
    assert "544 keyword hits → 178 first-pass yes → 133 kept" in html
    assert "$3.3508" in html
    assert "Would route 10" in html
    assert "est." in html
    assert "$3.35" in html
    assert "environment-agency" in html
    assert "10 Sep 14:15" in html
    assert "1m15s" in html
    assert "14:15 UTC" not in html
    assert ">Done<" in html
    assert ">Queued<" in html

    job_page = client.get(f"/jobs/{done.id}")
    assert job_page.status_code == 200
    job_html = job_page.text
    assert 'href="/jobs"' in job_html
    assert "Categories" in job_html
    assert "secret-owner@example.gov.uk" not in job_html
    assert "Slurry — Run 10 September 2026, 14:15" in job_html
    assert f"Job {done.id}" in job_html
    assert "Slurry (slurry)" in job_html
    assert "Organisations" in job_html
    assert "environment-agency" in job_html
    assert "Document types" in job_html
    assert "Keywords" in job_html
    assert ">slurry<" in job_html or "slurry" in job_html
    assert "Would route" not in job_html
    assert "Duration" not in job_html
    assert "$3.3508 — $1.8472 pass 1 Haiku (544 pages) · $1.5036 pass 2 Sonnet (178 pages)" in job_html
    assert job_html.count(">Done<") == 1
    assert "done / done" not in job_html
    assert "<pre" not in job_html.split(">Funnel<", 1)[0]
    assert '<section id="job-progress" class="job-progress" hidden>' in job_html
    assert "Technical log" in job_html
    assert 'id="job-log-details" open' not in job_html


def test_retry_failed_checkpoint_reattaches_without_redebit(client, settings, store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=596,
    )
    (job.output_dir / "checkpoint.json").write_text("{}\n")
    job.write_status(
        status="failed",
        error="guidance-relevance-filter exited 1",
        email_sent_at="2026-09-10T14:50:13+00:00",
    )
    store.add_routed_submitted(596)
    page = client.get(f"/jobs/{job.id}")
    assert page.status_code == 200
    assert f'action="/jobs/{job.id}/retry"' in page.text
    res = client.post(
        f"/jobs/{job.id}/retry",
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 202, res.text
    assert res.json()["status"] == "running"
    status = job.read_status()
    assert status["status"] == "running"
    assert status["pid"] is None
    assert status["error"] is None
    assert status["email_sent_at"] is None
    assert store.routed_submitted_today() == 596


def test_retry_failed_without_checkpoint_requeues(client, store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=3,
    )
    job.write_status(status="failed", error="exited 1")
    res = client.post(
        f"/jobs/{job.id}/retry",
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 202
    assert res.json()["status"] == "queued"


def test_retry_rejects_done(client, store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=3,
    )
    job.write_status(status="done")
    res = client.post(f"/jobs/{job.id}/retry")
    assert res.status_code == 409


def test_cli_env_injects_settings_key(settings, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = cli_env(settings)
    assert env["ANTHROPIC_API_KEY"] == "sk-test"


def test_claim_skips_when_anthropic_key_missing(settings, monkeypatch, corpus_dir, store):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    bare = settings.model_copy(update={"anthropic_api_key": None})
    store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=3,
    )
    assert claim_and_run(store, bare, Mailer(bare), corpus_dir / "with_body.json") is False
    assert store.queued()


def test_startup_sweep_reattaches_failed_checkpoint(settings, monkeypatch, corpus_dir, store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=596,
    )
    (job.output_dir / "checkpoint.json").write_text("{}\n")
    job.write_status(
        status="failed", error="exited 1", email_sent_at="2026-09-10T14:50:13+00:00",
    )
    calls: list[str] = []

    def fake_run_cli(s, j, pages, stem_index=None):
        calls.append(j.id)
        (j.output_dir / "output.json").write_text("[]\n")
        (j.output_dir / "metrics.json").write_text("{}")
        (j.output_dir / "checkpoint.json").unlink()
        return 0

    monkeypatch.setattr("guidance_relevance_web.worker.run_cli", fake_run_cli)
    assert store.resumable_failed()[0].id == job.id
    sweep_job(job, store, settings, Mailer(settings), corpus_dir / "with_body.json")
    assert calls == []
    sweep_job(
        job, store, settings, Mailer(settings), corpus_dir / "with_body.json",
        resume_failed=True,
    )
    assert calls == [job.id]
    assert job.read_status()["status"] == "done"
    assert job.read_status()["email_sent_at"] != "2026-09-10T14:50:13+00:00"


def test_sweep_skips_reattach_when_anthropic_key_missing(
    settings, monkeypatch, corpus_dir, store,
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    bare = settings.model_copy(update={"anthropic_api_key": None})
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=596,
    )
    (job.output_dir / "checkpoint.json").write_text("{}\n")
    job.write_status(status="failed", error="exited 1")

    def boom(*_a, **_k):
        raise AssertionError("must not spawn CLI without a key")

    monkeypatch.setattr("guidance_relevance_web.worker.run_cli", boom)
    sweep_job(
        job, store, bare, Mailer(bare), corpus_dir / "with_body.json",
        resume_failed=True,
    )
    assert job.read_status()["status"] == "failed"


def test_library_wizard_lists_both_newest_selected(library_client, library_dir):
    html = library_client.get("/").text
    assert "2 snapshots" in html
    assert "newest 10 September 2026" in html
    assert "10 September 2026 · 1 pages (newest)" in html
    assert "8 September 2026 · 4 pages" in html
    assert f'value="{library_dir["new_sha"]}"' in html
    assert f'value="{library_dir["old_sha"]}"' in html
    select = html.split('id="corpus_id"', 1)[1]
    first_option = select.split("<option", 2)[1]
    assert library_dir["new_sha"] in first_option
    assert "selected" in first_option
    assert library_dir["old_sha"] not in first_option
    org_block = html.split('id="organisations-list"', 1)[1].split('id="group-document_types"', 1)[0]
    assert 'value="department-for-environment-food-rural-affairs"' in org_block
    assert "defra" in org_block
    assert 'value="environment-agency"' not in org_block
    type_block = html.split('id="document_types-list"', 1)[1].split('id="group-lexicon"', 1)[0]
    assert 'value="guide"' in type_block
    assert 'value="detailed_guide"' not in type_block
    snapshots = html.split('id="snapshots-data"', 1)[1]
    assert "environment-agency" in snapshots
    assert "detailed_guide" in snapshots


def test_library_preview_defaults_to_newest(library_client, library_dir, library_settings):
    body, _ = _preview_done(library_client)
    assert body["counts"]["corpus_pages"] == 1
    assert body["counts"]["would_route"] == 0
    created = library_client.post(
        "/jobs", json={"preview_id": body["preview_id"], "email": "a@b.co.uk"},
    )
    assert created.status_code == 202
    meta = Store(library_settings).get(created.json()["id"]).read_meta()
    assert meta["corpus_sha256"] == library_dir["new_sha"]
    assert meta["corpus_n_pages"] == 1


def test_library_preview_pins_older_and_worker_uses_that_file(
    library_client, library_dir, library_settings, monkeypatch,
):
    body, _ = _preview_done(
        library_client,
        body={**SLURRY_BODY, "corpus_id": library_dir["old_sha"]},
    )
    assert body["counts"]["corpus_pages"] == 4
    assert body["counts"]["would_route"] == 1
    created = library_client.post(
        "/jobs", json={"preview_id": body["preview_id"], "email": "a@b.co.uk"},
    )
    assert created.status_code == 202
    store = Store(library_settings)
    job = store.get(created.json()["id"])
    assert job.read_meta()["corpus_sha256"] == library_dir["old_sha"]
    job_html = library_client.get(f"/jobs/{job.id}").text
    corpus_select = job_html.split('id="corpus_id"', 1)[1].split("</select>", 1)[0]
    old_option = [p for p in corpus_select.split("<option") if library_dir["old_sha"] in p][0]
    assert "selected" in old_option
    org_block = job_html.split(
        'id="organisations-list"', 1,
    )[1].split('id="group-document_types"', 1)[0]
    assert 'value="environment-agency"' in org_block
    catalog = CorpusCatalog(library_dir["root"])
    pinned = full_corpus_for_job(job, catalog)
    assert pinned == library_dir["root"].resolve() / "with_body.json"

    captured: list[Path] = []

    def fake_run_cli(s, j, pages, stem_index=None):
        captured.append(Path(pages))
        (j.output_dir / "output.json").write_text("[]\n")
        (j.output_dir / "metrics.json").write_text("{}")
        j.write_status(status="running", pid=None)
        return 0

    monkeypatch.setattr("guidance_relevance_web.worker.run_cli", fake_run_cli)
    assert claim_and_run(store, library_settings, Mailer(library_settings), catalog) is True
    assert captured == [library_dir["root"].resolve() / "with_body.json"]
    runs = library_client.get("/jobs").text
    assert "8 September 2026 · 4 pages" in runs


def test_library_unknown_corpus_is_400(library_client):
    res = library_client.post("/preview", json={**SLURRY_BODY, "corpus_id": "0" * 64})
    assert res.status_code == 400
    assert "Unknown corpus" in res.json()["detail"]


def test_unpinned_job_fails_when_library_has_many(library_dir, library_settings):
    store = Store(library_settings)
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=1,
    )
    catalog = CorpusCatalog(library_dir["root"])
    with pytest.raises(CorpusError, match="no corpus_sha256"):
        full_corpus_for_job(job, catalog)
    mailer = Mailer(library_settings)
    assert claim_and_run(store, library_settings, mailer, catalog) is True
    assert job.read_status()["status"] == "failed"
    assert "no corpus_sha256" in job.read_status()["error"]
