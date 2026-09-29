import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from guidance_relevance_web.store import (
    Store,
    _run_at_label,
    _write_json,
    duration_view,
    progress_view,
    status_label,
)


def _job(store: Store, name: str = "slurry"):
    return store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": name, "description": "d", "exclusion_criteria": "e"}],
        lexicons={name: [name]},
        would_route=1,
    )


def _break(store: Store, *, status: str = "") -> None:
    broken = store.jobs_dir / "broken"
    broken.mkdir()
    (broken / "status.json").write_text(status)


def test_queued_skips_empty_and_invalid_status(store):
    good = _job(store)
    _break(store)
    (store.jobs_dir / "empty-dir").mkdir()
    truncated = store.jobs_dir / "truncated"
    truncated.mkdir()
    (truncated / "status.json").write_text("{")

    queued = store.queued()
    assert [j.id for j in queued] == [good.id]
    assert [j.id for j in store.incomplete()] == [good.id]
    assert store.resumable_failed() == []
    assert [row["id"] for row in store.list_jobs()] == [good.id]


def test_write_status_recovers_empty_file(store):
    job = _job(store)
    (job.root / "status.json").write_text("")
    job.write_status(status="queued")
    assert job.read_status()["status"] == "queued"


def test_write_json_concurrent_leaves_valid_object(tmp_path: Path):
    path = tmp_path / "status.json"

    def write(n: int) -> None:
        _write_json(path, {"n": n})

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(write, range(40)))
    data = json.loads(path.read_text())
    assert isinstance(data["n"], int)
    assert not list(tmp_path.glob("*.tmp"))


def test_duration_prefers_process_elapsed_over_llm_passes():
    view = duration_view(
        {
            "elapsed_seconds": 75,
            "pass1": {"batch_meta": {"elapsed_seconds": 7}},
            "pass2": {"batch_meta": {"elapsed_seconds": 17}},
        },
        {"status": "done"},
    )
    assert view["label"] == "1m15s"
    assert view["source"] == "run"
    assert view["llm_label"] == "24s"


def test_duration_falls_back_to_llm_pass_times():
    view = duration_view(
        {
            "pass1": {"batch_meta": {"elapsed_seconds": 7}},
            "pass2": {"batch_meta": {"elapsed_seconds": 17}},
        },
        {"status": "done"},
    )
    assert view["label"] == "LLM 24s"
    assert view["source"] == "llm"


def test_duration_uses_status_started_at_while_running():
    view = duration_view(
        None,
        {
            "status": "running",
            "started_at": "2026-09-11T16:00:00+00:00",
        },
        now=datetime(2026, 9, 11, 16, 2, tzinfo=UTC),
    )
    assert view["label"] == "2m00s"
    assert view["source"] == "run"


def test_run_at_label_full_date():
    assert _run_at_label("2026-09-10T14:32:00+00:00") == "10 September 2026, 14:32"
    assert _run_at_label(None) == "—"


def test_status_label_sentence_case():
    assert status_label("done") == "Done"
    assert status_label("queued") == "Queued"
    assert status_label("blocked_cap") == "Over cap"
    assert status_label(None) == "—"


def test_progress_view_maps_phase_to_step():
    queued = progress_view("queued", "queued")
    assert queued["visible"] is True
    assert queued["step"] == 1
    assert queued["pct"] == 33
    assert queued["label"] == "Preparing the shortlist…"
    assert [s["state"] for s in queued["steps"]] == ["current", "pending", "pending"]

    running = progress_view("running", "running")
    assert running["step"] == 1
    assert running["pct"] == 33

    submitting = progress_view("running", "submitting")
    assert submitting["step"] == 1
    assert submitting["label"] == "Preparing the shortlist…"

    pass1 = progress_view("running", "pass1")
    assert pass1["visible"] is True
    assert pass1["step"] == 2
    assert pass1["pct"] == 66
    assert pass1["label"] == "Reading pages (inclusion rules)…"
    assert [s["state"] for s in pass1["steps"]] == ["done", "current", "pending"]

    pass2 = progress_view("running", "pass2")
    assert pass2["step"] == 3
    assert pass2["pct"] == 90
    assert pass2["label"] == "Reading pages (exclusion rules)…"
    assert [s["state"] for s in pass2["steps"]] == ["done", "done", "current"]

    done = progress_view("done", "done")
    assert done["visible"] is False
    failed = progress_view("failed", "pass1")
    assert failed["visible"] is False
    blocked = progress_view("blocked_cap", "pass2")
    assert blocked["visible"] is False


def test_public_view_title_keywords_and_run_at(store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{
            "name": "slurry_small_test",
            "title": "Animal Liquid Waste",
            "description": "d",
            "exclusion_criteria": "e",
        }],
        lexicons={"slurry_small_test": ["slurry", "digestate"]},
        would_route=30,
        organisations=["environment-agency"],
        document_types=["guidance"],
    )
    meta = json.loads((job.root / "meta.json").read_text())
    meta["created_at"] = "2026-09-10T14:32:00+00:00"
    (job.root / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    view = job.public_view()
    assert view["title"] == "Animal Liquid Waste"
    assert view["category"] == "slurry_small_test"
    assert view["run_at"] == "10 September 2026, 14:32"
    assert view["keywords"] == ["slurry", "digestate"]
    assert view["organisations"] == ["environment-agency"]
    assert view["document_types"] == ["guidance"]
    assert view["llm_mode"] == "batch"
    assert view["progress"]["visible"] is True
    assert view["progress"]["step"] == 1
    form = job.wizard_form()
    assert form["name"] == "slurry_small_test"
    assert form["description"] == "d"
    assert form["exclusion_criteria"] == "e"
    assert form["lexicon"] == "slurry\ndigestate"
    assert form["organisations"] == ["environment-agency"]
    assert form["document_types"] == ["guidance"]
    assert "email" not in form


def test_wizard_form_includes_hints_and_corpus(store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{
            "name": "slurry",
            "description": "keep slurry",
            "exclusion_criteria": "not sewage",
            "adjudication_hints": {
                "keep": ["grant page that funds stores"],
                "drop": ["coal slurry"],
            },
        }],
        lexicons={"slurry": ["slurry", "lagoon"]},
        would_route=1,
        corpus_sha256="abc123",
    )
    form = job.wizard_form()
    assert form["keep_hints"] == "grant page that funds stores"
    assert form["drop_hints"] == "coal slurry"
    assert form["lexicon"] == "slurry\nlagoon"
    assert form["corpus_id"] == "abc123"


def test_public_view_title_falls_back_to_slug(store):
    job = _job(store, "slurry_small_test")
    assert job.public_view()["title"] == "Slurry Small Test"


def test_public_view_uses_job_llm_mode_for_estimate(store):
    job = store.create_job(
        email="op@example.gov.uk",
        categories=[{"name": "slurry", "description": "d", "exclusion_criteria": "e"}],
        lexicons={"slurry": ["slurry"]},
        would_route=544,
        llm_mode="sync",
    )
    view = job.public_view()
    assert view["llm_mode"] == "sync"
    assert view["cost_estimate"]["usd"] == 6.70
    assert "1×" in view["cost_estimate"]["html"]
    listed = job.list_view()
    assert listed["llm_mode"] == "sync"
    assert listed["cost_estimate"]["usd"] == 6.70
