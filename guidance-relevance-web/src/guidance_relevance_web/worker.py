"""Single-slot GRF CLI worker + checkpoint sweeper."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from guidance_relevance_filter.narrowing import (
    iter_json_items,
    load_or_build_stem_index,
    sha256_file,
    stem_index_path,
)

from .category import page_matches_document_types, page_matches_organisations
from .corpus import CorpusCatalog, CorpusError
from .mailer import Mailer, job_mail
from .settings import Settings
from .store import CHECKPOINT, OUTPUT_JSON, Job, Store, llm_mode_from_meta

CorpusSource = CorpusCatalog | Path

CORPUS_JSON = "corpus.json"


def _job_scope_list(job: Job, name: str) -> list:
    path = job.root / f"{name}.json"
    if path.is_file():
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
    return job.read_meta().get(name) or []


def full_corpus_for_job(job: Job, corpus: CorpusSource) -> Path:
    """Pinned snapshot for this job, or a Path fallback used by tests.

    Missing pin: newest if the library has exactly one snapshot, else error.
    Unknown / deleted sha: error (do not fall through to newest).
    """
    if isinstance(corpus, Path):
        return corpus
    sha = str(job.read_meta().get("corpus_sha256") or "").strip() or None
    if sha:
        return corpus.get(sha).pages_path
    snapshots = corpus.list()
    if len(snapshots) == 1:
        return corpus.get(snapshots[0].id).pages_path
    raise CorpusError(
        "job has no corpus_sha256; cannot pick among "
        f"{len(snapshots)} snapshots. Re-preview and submit."
    )


def corpus_path_for_job(job: Job, full_corpus: Path) -> Path:
    """Slice the frozen corpus into job-local corpus.json when scope filters exist."""
    organisations = _job_scope_list(job, "organisations")
    document_types = _job_scope_list(job, "document_types")
    if not organisations and not document_types:
        return full_corpus
    dest = job.root / CORPUS_JSON
    if not dest.is_file():
        _write_sliced_corpus(
            full_corpus, dest,
            organisations=organisations, document_types=document_types,
        )
    return dest


def _write_sliced_corpus(
    src: Path,
    dest: Path,
    *,
    organisations: list,
    document_types: list,
) -> None:
    tmp = dest.with_name(dest.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as out:
        out.write("[\n")
        first = True
        for page in iter_json_items(src):
            if organisations and not page_matches_organisations(page, organisations):
                continue
            if document_types and not page_matches_document_types(page, document_types):
                continue
            if not first:
                out.write(",\n")
            json.dump(page, out, ensure_ascii=False)
            first = False
        out.write("\n]\n")
    tmp.replace(dest)


def stem_index_path_for_job(job: Job, corpus: CorpusSource, full_corpus: Path) -> Path:
    """Snapshot sqlite — never a per-slice copy."""
    if not isinstance(corpus, Path):
        sha = str(job.read_meta().get("corpus_sha256") or "").strip() or None
        return corpus.get(sha).ensure_stem_index().path
    sha = sha256_file(full_corpus)
    dest = stem_index_path(full_corpus, sha)
    load_or_build_stem_index(full_corpus, corpus_sha256=sha, path=dest)
    return dest

log = logging.getLogger(__name__)


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def anthropic_ready(settings: Settings) -> bool:
    return bool(settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))


def cli_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    return env


def cli_command(
    settings: Settings,
    job: Job,
    corpus_pages: Path,
    *,
    stem_index: Path | None = None,
) -> list[str]:
    # Popen cwd is the job dir, so relative GRF_JOBS/GRF_CORPUS paths would
    # resolve as jobs/<id>/data/jobs/... and Click --exists would fail.
    cmd = [
        sys.executable,
        "-m",
        "guidance_relevance_filter",
        "run",
        str(corpus_pages.resolve()),
        str(job.output_dir.resolve()),
        "--categories",
        str((job.root / "categories.json").resolve()),
        "--lexicon",
        str((job.root / "lexicon.json").resolve()),
        "--max-routed",
        str(settings.grf_max_routed),
    ]
    if stem_index is not None:
        cmd.extend(["--stem-index", str(stem_index.resolve())])
    mode = llm_mode_from_meta(job.read_meta(), fallback=settings.grf_llm_mode)
    if mode == "sync":
        cmd.extend(["--sync", "--concurrency", str(settings.grf_sync_concurrency)])
    return cmd


def run_cli(
    settings: Settings,
    job: Job,
    corpus_pages: Path,
    stem_index: Path | None = None,
) -> int:
    job.output_dir.mkdir(parents=True, exist_ok=True)
    cmd = cli_command(settings, job, corpus_pages, stem_index=stem_index)
    log.info("job %s: %s", job.id, " ".join(cmd))
    with job.run_log.open("ab") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(job.root),
            env=cli_env(settings),
        )
        job.write_status(
            status="running",
            pid=proc.pid,
            started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        return proc.wait()


def finalize(job: Job, store: Store, mailer: Mailer, settings: Settings, code: int) -> None:
    metrics_path = job.output_dir / "metrics.json"
    capped = False
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
        capped = bool(metrics.get("capped"))
    output_ok = (job.output_dir / OUTPUT_JSON).exists()
    if code == 0 and output_ok and not capped:
        job.write_status(status="done", pid=None, error=None)
    elif capped:
        job.write_status(status="blocked_cap", pid=None, capped=True, error="max-routed exceeded")
    else:
        job.write_status(
            status="failed",
            pid=None,
            error=f"guidance-relevance-filter exited {code}",
        )
    subject, body = job_mail(job, settings)
    mailer.send(job, subject=subject, body=body)


def _fail_corpus(job: Job, mailer: Mailer, settings: Settings, exc: Exception) -> None:
    job.write_status(status="failed", pid=None, error=str(exc))
    subject, body = job_mail(job, settings)
    mailer.send(job, subject=subject, body=body)


def claim_and_run(store: Store, settings: Settings, mailer: Mailer, corpus: CorpusSource) -> bool:
    if not anthropic_ready(settings):
        log.error("ANTHROPIC_API_KEY unset; not claiming")
        return False
    queued = store.queued()
    if not queued:
        return False
    job = queued[0]
    try:
        full = full_corpus_for_job(job, corpus)
    except CorpusError as e:
        log.error("job %s: %s", job.id, e)
        _fail_corpus(job, mailer, settings, e)
        return True
    would_route = int(job.read_meta().get("would_route") or 0)
    store.add_routed_submitted(would_route)
    code = run_cli(
        settings, job, corpus_path_for_job(job, full),
        stem_index=stem_index_path_for_job(job, corpus, full),
    )
    never_started = (
        not (job.output_dir / "metrics.json").exists()
        and not (job.output_dir / OUTPUT_JSON).exists()
    )
    if code != 0 and never_started:
        store.add_routed_submitted(-would_route)
    finalize(job, store, mailer, settings, code)
    return True


def sweep_job(
    job: Job,
    store: Store,
    settings: Settings,
    mailer: Mailer,
    corpus: CorpusSource,
    *,
    resume_failed: bool = False,
) -> None:
    status = job.read_status()
    kind = status.get("status")
    if kind in {"done", "blocked_cap"}:
        return
    output_ok = (job.output_dir / OUTPUT_JSON).exists()
    checkpoint = job.output_dir / CHECKPOINT
    if kind == "failed":
        if not resume_failed or not checkpoint.exists():
            return
    if output_ok and not checkpoint.exists() and kind == "running":
        finalize(job, store, mailer, settings, 0)
        return
    if kind == "running" and _pid_alive(status.get("pid")):
        return
    if kind in {"queued", "running", "failed"} and (checkpoint.exists() or kind == "running"):
        if not anthropic_ready(settings):
            log.error("ANTHROPIC_API_KEY unset; not reattaching job %s", job.id)
            return
        if kind == "failed":
            job.write_status(email_sent_at=None)
        log.info("job %s: sweeper reattaching", job.id)
        try:
            full = full_corpus_for_job(job, corpus)
        except CorpusError as e:
            log.error("job %s: %s", job.id, e)
            _fail_corpus(job, mailer, settings, e)
            return
        code = run_cli(
            settings, job, corpus_path_for_job(job, full),
            stem_index=stem_index_path_for_job(job, corpus, full),
        )
        finalize(job, store, mailer, settings, code)


class Worker:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        mailer: Mailer,
        corpus: CorpusSource,
    ) -> None:
        self.store = store
        self.settings = settings
        self.mailer = mailer
        self.corpus = corpus
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_sweep = 0.0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="grf-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        try:
            for job in (*self.store.incomplete(), *self.store.resumable_failed()):
                sweep_job(
                    job, self.store, self.settings, self.mailer, self.corpus,
                    resume_failed=True,
                )
        except Exception:
            log.exception("startup sweep failed")
        self._last_sweep = time.monotonic()
        while not self._stop.is_set():
            try:
                ran = claim_and_run(self.store, self.settings, self.mailer, self.corpus)
            except Exception:
                log.exception("worker claim/run failed")
                ran = False
            now = time.monotonic()
            if now - self._last_sweep >= self.settings.grf_sweep_seconds:
                self._last_sweep = now
                try:
                    for job in self.store.incomplete():
                        sweep_job(
                            job, self.store, self.settings, self.mailer, self.corpus,
                        )
                except Exception:
                    log.exception("sweeper failed")
            if not ran:
                self._stop.wait(self.settings.grf_queue_poll_seconds)
