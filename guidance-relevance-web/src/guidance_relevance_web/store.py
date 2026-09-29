"""Disk job store, previews, and daily routed-page budget."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from .category import title_from_slug
from .corpus import snapshot_label
from .cost_estimate import estimate_usd
from .settings import Settings

STATUSES = ("queued", "running", "done", "failed", "blocked_cap")
_STATUS_LABELS = {
    "queued": "Queued",
    "running": "Running",
    "done": "Done",
    "failed": "Failed",
    "blocked_cap": "Over cap",
}
URL_SAMPLE = 100

CHECKPOINT = "checkpoint.json"
OUTPUT_JSON = "output.json"
METRICS_JSON = "metrics.json"
_JOB_SCAN_ERRORS = (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError)


def status_label(status: str | None) -> str:
    if not status:
        return "—"
    return _STATUS_LABELS.get(status, str(status).replace("_", " ").capitalize())


def llm_mode_from_meta(meta: dict[str, Any], *, fallback: str = "batch") -> str:
    mode = meta.get("llm_mode")
    if mode in ("batch", "sync"):
        return mode
    return fallback if fallback in ("batch", "sync") else "batch"


_PROGRESS_STEPS = (
    (1, "Input shortlist", "Preparing the shortlist…", 33),
    (2, "Inclusion rules", "Reading pages (inclusion rules)…", 66),
    (3, "Exclusion rules", "Reading pages (exclusion rules)…", 90),
)


def progress_view(status: str | None, phase: str | None) -> dict[str, Any]:
    step = 3 if phase == "pass2" else 2 if phase == "pass1" else 1
    n, _title, label, pct = _PROGRESS_STEPS[step - 1]
    return {
        "visible": status in {"queued", "running"},
        "step": n,
        "label": label,
        "pct": pct,
        "steps": [
            {
                "n": s,
                "title": title,
                "state": "done" if s < step else ("current" if s == step else "pending"),
            }
            for s, title, _label, _pct in _PROGRESS_STEPS
        ],
    }


def _usd_label(value: float | None) -> str:
    return "not priced" if value is None else f"${value:.4f}"


def _short_model(model: str | None) -> str:
    if not model:
        return ""
    lower = model.lower()
    if "haiku" in lower:
        return "Haiku"
    if "sonnet" in lower:
        return "Sonnet"
    return model


def _funnel_n(funnel: dict[str, Any], *keys: str) -> int:
    for key in keys:
        raw = funnel.get(key)
        if isinstance(raw, dict):
            n = raw.get("n")
            if n is not None:
                return int(n)
        elif isinstance(raw, bool):
            continue
        elif isinstance(raw, (int, float)):
            return int(raw)
    return 0


def result_caption(
    metrics: dict[str, Any] | None,
    *,
    would_route: int,
    status: str | None,
) -> str:
    """One-liner for the runs list. Prefer metrics.funnel; never read funnel.json."""
    funnel = metrics.get("funnel") if isinstance(metrics, dict) else None
    if isinstance(funnel, dict) and funnel:
        n_hit = _funnel_n(funnel, "lexicon_hit", "would_route")
        n_p1_true = _funnel_n(funnel, "pass1_true")
        kept = _funnel_n(funnel, "pass2_kept", "pass2_keep")
        kept += _funnel_n(funnel, "pass2_unadjudicated")
        if not kept:
            kept = _funnel_n(funnel, "final_true")
        if n_hit or n_p1_true or kept:
            return (
                f"{n_hit:,} keyword hits → {n_p1_true:,} first-pass yes → {kept:,} kept"
            )
    if status in {"queued", "running"}:
        return f"Would route {int(would_route or 0):,}"
    return "—"


def _when_label(created_at: str | None) -> str:
    if not created_at:
        return "—"
    try:
        dt = datetime.fromisoformat(created_at)
    except ValueError:
        return created_at
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.strftime("%d %b %H:%M")


def _run_at_label(created_at: str | None) -> str:
    if not created_at:
        return "—"
    try:
        dt = datetime.fromisoformat(created_at)
    except ValueError:
        return created_at
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return f"{dt.day} {dt.strftime('%B %Y, %H:%M')}"


def _fmt_duration(seconds: int) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _seconds_between(start: str, end: str) -> int | None:
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
    except ValueError:
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=UTC)
    if b.tzinfo is None:
        b = b.replace(tzinfo=UTC)
    return max(0, int((b - a).total_seconds()))


def _llm_elapsed_seconds(metrics: dict[str, Any] | None) -> int | None:
    if not metrics:
        return None
    total = 0
    found = False
    for key in ("pass1", "pass2"):
        meta = (metrics.get(key) or {}).get("batch_meta") or {}
        if "elapsed_seconds" in meta:
            found = True
            total += int(meta.get("elapsed_seconds") or 0)
    return total if found else None


def duration_view(
    metrics: dict[str, Any] | None,
    status: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Wall-clock CLI time if recorded; else sum of LLM pass times."""
    seconds: int | None = None
    source = "run"
    if metrics and metrics.get("elapsed_seconds") is not None:
        seconds = int(metrics["elapsed_seconds"])
    elif status.get("started_at"):
        end = status.get("updated_at")
        if status.get("status") == "running":
            end = (now or datetime.now(UTC)).isoformat(timespec="seconds")
        if end:
            seconds = _seconds_between(str(status["started_at"]), str(end))
    llm = _llm_elapsed_seconds(metrics)
    if seconds is None:
        seconds = llm
        source = "llm"
    if seconds is None:
        return None
    label = _fmt_duration(seconds)
    if source == "llm":
        label = f"LLM {label}"
    return {
        "seconds": seconds,
        "label": label,
        "source": source,
        "llm_seconds": llm,
        "llm_label": _fmt_duration(llm) if llm is not None else None,
    }


def _scope_hint(organisations: list[str], document_types: list[str]) -> str:
    parts: list[str] = []
    if organisations:
        parts.append(", ".join(organisations))
    if document_types:
        parts.append(", ".join(document_types))
    return " · ".join(parts)


def _corpus_hint(meta: dict[str, Any]) -> str:
    built = meta.get("corpus_built_on")
    n = meta.get("corpus_n_pages")
    if built and n is not None:
        try:
            return snapshot_label(str(built), int(n))
        except (TypeError, ValueError):
            pass
    sha = str(meta.get("corpus_sha256") or "")
    return f"{sha[:8]}…" if sha else ""


def cost_from_metrics(metrics: dict[str, Any]) -> dict[str, Any] | None:
    """Operator-facing cost from a GRF ``metrics.json``, or None if the run never priced."""
    if "cost_usd" not in metrics and "pass1" not in metrics:
        return None
    pass1 = metrics.get("pass1") or {}
    pass2 = metrics.get("pass2") or {}
    total = metrics.get("cost_usd")
    p1 = pass1.get("cost_usd")
    p2 = pass2.get("cost_usd")
    p1_model = _short_model(pass1.get("model"))
    p2_model = _short_model(pass2.get("model"))
    p1_n = pass1.get("n_routed") or 0
    p2_n = pass2.get("n_positives") or 0
    label = _usd_label(total)
    capped = bool(metrics.get("capped"))
    if capped or total is None:
        detail = label
    else:
        detail = (
            f"{label} — {_usd_label(p1)} pass 1 {p1_model} ({p1_n} pages)"
            f" · {_usd_label(p2)} pass 2 {p2_model} ({p2_n} pages)"
        )
    return {
        "usd": total,
        "label": label,
        "detail": detail,
        "capped": capped,
        "tokens": metrics.get("tokens") or {},
        "pass1": {
            "usd": p1,
            "label": _usd_label(p1),
            "model": p1_model,
            "model_id": pass1.get("model"),
            "n_routed": pass1.get("n_routed"),
        },
        "pass2": {
            "usd": p2,
            "label": _usd_label(p2),
            "model": p2_model,
            "model_id": pass2.get("model"),
            "n_positives": pass2.get("n_positives"),
        },
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _read_json_list(path: Path) -> list:
    if not path.is_file():
        return []
    data = _read_json(path)
    return data if isinstance(data, list) else []


def _job_created_at(job: Job) -> str:
    try:
        return job.read_meta().get("created_at") or ""
    except _JOB_SCAN_ERRORS:
        return ""


@dataclass
class Job:
    root: Path

    @property
    def id(self) -> str:
        return self.root.name

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def run_log(self) -> Path:
        return self.root / "run.log"

    def read_status(self) -> dict[str, Any]:
        return _read_json(self.root / "status.json")

    def read_meta(self) -> dict[str, Any]:
        return _read_json(self.root / "meta.json")

    def write_status(self, **fields: Any) -> dict[str, Any]:
        current: dict[str, Any] = {}
        if (self.root / "status.json").exists():
            try:
                loaded = self.read_status()
                if isinstance(loaded, dict):
                    current = loaded
            except _JOB_SCAN_ERRORS:
                pass
        current.update(fields)
        current["updated_at"] = _now()
        _write_json(self.root / "status.json", current)
        return current

    def tail_log(self, n: int | None = None) -> list[str]:
        if not self.run_log.exists():
            return []
        lines = self.run_log.read_text(errors="replace").splitlines()
        return lines if n is None else lines[-n:]

    def phase(self) -> str:
        status = self.read_status().get("status") or "queued"
        output_json = self.output_dir / OUTPUT_JSON
        checkpoint = self.output_dir / CHECKPOINT
        if output_json.exists() and not checkpoint.exists():
            return "done"
        if checkpoint.exists():
            data = _read_json(checkpoint)
            p2 = data.get("pass2") or {}
            p1 = data.get("pass1") or {}
            if p2.get("batch_id") or p2.get("replies") or p2.get("positive_urls"):
                return "pass2"
            if p1.get("batch_id") or p1.get("replies") or p1.get("routed_urls"):
                return "pass1"
            return "submitting"
        return status

    def public_view(self, *, batch: bool | None = None) -> dict[str, Any]:
        status = self.read_status()
        meta = self.read_meta()
        slug = str(meta.get("category") or "")
        phase = self.phase()
        status_name = status.get("status")
        mode = llm_mode_from_meta(meta)
        is_batch = mode != "sync" if batch is None else batch
        return {
            "id": self.id,
            "status": status_name,
            "status_label": status_label(status_name),
            "phase": phase,
            "progress": progress_view(status_name, phase),
            "category": slug,
            "title": self._title(slug),
            "run_at": _run_at_label(meta.get("created_at")),
            "would_route": meta.get("would_route"),
            "created_at": meta.get("created_at"),
            "organisations": meta.get("organisations") or [],
            "document_types": meta.get("document_types") or [],
            "keywords": self._keywords(slug),
            "corpus": _corpus_hint(meta),
            "corpus_sha256": meta.get("corpus_sha256"),
            "error": status.get("error"),
            "log_tail": self.tail_log(),
            "email_sent_at": status.get("email_sent_at"),
            "capped": status.get("capped", False),
            "can_retry": status.get("status") == "failed",
            "llm_mode": mode,
            "cost": self.read_cost(),
            "cost_estimate": estimate_usd(
                int(meta.get("would_route") or 0), batch=is_batch,
            ),
            "duration": duration_view(self.read_metrics(), status),
        }

    def _title(self, slug: str) -> str:
        path = self.root / "categories.json"
        if path.is_file():
            try:
                cats = _read_json(path)
            except _JOB_SCAN_ERRORS:
                cats = None
            if isinstance(cats, list) and cats and isinstance(cats[0], dict):
                raw = cats[0].get("title")
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
        return title_from_slug(slug) or slug

    def _keywords(self, slug: str) -> list[str]:
        path = self.root / "lexicon.json"
        if not path.is_file():
            return []
        try:
            data = _read_json(path)
        except _JOB_SCAN_ERRORS:
            return []
        if not isinstance(data, dict):
            return []
        terms = data.get(slug)
        if isinstance(terms, list):
            return [str(t) for t in terms]
        for value in data.values():
            if isinstance(value, list):
                return [str(t) for t in value]
        return []

    def wizard_form(self) -> dict[str, Any]:
        """Definition fields for the create wizard. Does not include email."""
        meta = self.read_meta()
        slug = str(meta.get("category") or "")
        cat: dict[str, Any] = {}
        path = self.root / "categories.json"
        if path.is_file():
            try:
                cats = _read_json(path)
            except _JOB_SCAN_ERRORS:
                cats = None
            if isinstance(cats, list) and cats and isinstance(cats[0], dict):
                cat = cats[0]
                if not slug:
                    slug = str(cat.get("name") or "")
        hints = cat.get("adjudication_hints")
        hints = hints if isinstance(hints, dict) else {}
        keep = hints.get("keep") if isinstance(hints.get("keep"), list) else []
        drop = hints.get("drop") if isinstance(hints.get("drop"), list) else []
        return {
            "name": slug,
            "description": str(cat.get("description") or ""),
            "exclusion_criteria": str(cat.get("exclusion_criteria") or ""),
            "keep_hints": "\n".join(str(x) for x in keep),
            "drop_hints": "\n".join(str(x) for x in drop),
            "lexicon": "\n".join(self._keywords(slug)),
            "organisations": [
                str(x) for x in (meta.get("organisations") or [])
            ],
            "document_types": [
                str(x) for x in (meta.get("document_types") or [])
            ],
            "corpus_id": str(meta.get("corpus_sha256") or ""),
        }

    def list_view(self, *, batch: bool | None = None) -> dict[str, Any]:
        status = self.read_status()
        meta = self.read_meta()
        metrics = self.read_metrics()
        orgs = meta.get("organisations") if isinstance(meta.get("organisations"), list) else []
        types = meta.get("document_types") if isinstance(meta.get("document_types"), list) else []
        would = int(meta.get("would_route") or 0)
        st = status.get("status")
        mode = llm_mode_from_meta(meta)
        is_batch = mode != "sync" if batch is None else batch
        return {
            "id": self.id,
            "status": st,
            "status_label": status_label(st),
            "category": meta.get("category"),
            "would_route": would,
            "created_at": meta.get("created_at"),
            "when": _when_label(meta.get("created_at")),
            "organisations": orgs,
            "document_types": types,
            "scope_hint": _scope_hint(orgs, types),
            "corpus": _corpus_hint(meta),
            "llm_mode": mode,
            "cost": cost_from_metrics(metrics) if metrics else None,
            "cost_estimate": estimate_usd(would, batch=is_batch),
            "result": result_caption(metrics, would_route=would, status=st),
            "duration": duration_view(metrics, status),
        }

    def read_metrics(self) -> dict[str, Any] | None:
        path = self.output_dir / METRICS_JSON
        if not path.is_file():
            return None
        try:
            metrics = _read_json(path)
        except (json.JSONDecodeError, OSError):
            return None
        return metrics if isinstance(metrics, dict) else None

    def read_cost(self) -> dict[str, Any] | None:
        metrics = self.read_metrics()
        if metrics is None:
            return None
        return cost_from_metrics(metrics)

    def read_scope(self) -> dict[str, Any] | None:
        path = self.root / "scope.json"
        if not path.is_file():
            return None
        try:
            return _read_json(path)
        except (json.JSONDecodeError, OSError):
            return None

    def has_checkpoint(self) -> bool:
        return (self.output_dir / CHECKPOINT).is_file()

    def retry(self) -> dict[str, Any]:
        """Re-queue a failed run. Checkpoint present → running (sweeper reattaches, no budget debit)."""
        status = self.read_status().get("status")
        if status != "failed":
            raise ValueError(f"cannot retry a {status!r} job")
        nxt = "running" if self.has_checkpoint() else "queued"
        return self.write_status(
            status=nxt, pid=None, error=None, email_sent_at=None, capped=False,
        )


class Store:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.grf_jobs.expanduser().resolve()
        self.jobs_dir = self.root / "jobs"
        self.previews_dir = self.root / "previews"
        self.usage_dir = self.root / "usage"
        self.wordsearch_cache_dir = self.root / "wordsearch-cache"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.previews_dir.mkdir(parents=True, exist_ok=True)
        self.usage_dir.mkdir(parents=True, exist_ok=True)
        self.wordsearch_cache_dir.mkdir(parents=True, exist_ok=True)

    def create_preview(
        self,
        *,
        categories: list[dict],
        lexicons: dict[str, list[str]],
        counts: dict[str, Any],
        warnings: list[str],
        stages: list[dict],
        organisations: list[str] | None = None,
        document_types: list[str] | None = None,
        corpus_sha256: str | None = None,
        corpus_built_on: str | None = None,
        corpus_n_pages: int | None = None,
    ) -> str:
        preview_id = str(uuid.uuid4())
        dest = self.previews_dir / preview_id
        dest.mkdir(parents=True)
        _write_json(dest / "categories.json", categories)
        _write_json(dest / "lexicon.json", lexicons)
        _write_json(dest / "organisations.json", organisations or [])
        _write_json(dest / "document_types.json", document_types or [])
        _write_json(
            dest / "corpus.json",
            {
                "sha256": corpus_sha256,
                "built_on": corpus_built_on,
                "n_pages": corpus_n_pages,
            },
        )
        _write_json(
            dest / "result.json",
            {
                "created_at": _now(),
                "counts": counts,
                "warnings": warnings,
                "stages": stages,
            },
        )
        return preview_id

    @staticmethod
    def wordsearch_cache_key(
        corpus_sha256: str,
        name: str,
        lexicons: dict[str, list[str]],
        organisations: list[str] | None = None,
        document_types: list[str] | None = None,
    ) -> str:
        """Identity of a wordsearch: corpus + category name + lexicon + scope.

        Description / exclusion / hints do not affect routing.
        """
        payload = {
            "v": 4,
            "corpus": corpus_sha256,
            "name": name,
            "lexicon": {
                k: sorted(v, key=str.lower) for k, v in sorted(lexicons.items())
            },
            "organisations": sorted(organisations or [], key=str.lower),
            "document_types": sorted(document_types or [], key=str.lower),
        }
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return sha256(raw.encode("utf-8")).hexdigest()

    def load_wordsearch_cache(self, key: str) -> dict[str, Any] | None:
        path = self.wordsearch_cache_dir / f"{key}.json"
        if not path.is_file():
            return None
        try:
            return _read_json(path)
        except (json.JSONDecodeError, OSError):
            return None

    def save_wordsearch_cache(self, key: str, payload: dict[str, Any]) -> None:
        _write_json(self.wordsearch_cache_dir / f"{key}.json", payload)

    def load_preview(self, preview_id: str) -> dict[str, Any]:
        dest = self.previews_dir / preview_id
        if not dest.is_dir():
            raise FileNotFoundError(preview_id)
        corpus: dict[str, Any] = {}
        if (dest / "corpus.json").is_file():
            raw = _read_json(dest / "corpus.json")
            if isinstance(raw, dict):
                corpus = raw
        return {
            "categories": _read_json(dest / "categories.json"),
            "lexicons": _read_json(dest / "lexicon.json"),
            "result": _read_json(dest / "result.json"),
            "organisations": _read_json_list(dest / "organisations.json"),
            "document_types": _read_json_list(dest / "document_types.json"),
            "corpus": corpus,
        }

    def create_job(
        self,
        *,
        email: str,
        categories: list[dict],
        lexicons: dict[str, list[str]],
        would_route: int,
        preview_id: str | None = None,
        organisations: list[str] | None = None,
        document_types: list[str] | None = None,
        scope: dict[str, Any] | None = None,
        corpus_sha256: str | None = None,
        corpus_built_on: str | None = None,
        corpus_n_pages: int | None = None,
        llm_mode: str = "batch",
    ) -> Job:
        job_id = str(uuid.uuid4())
        root = self.jobs_dir / job_id
        root.mkdir(parents=True)
        (root / "output").mkdir()
        orgs = organisations or []
        types = document_types or []
        _write_json(root / "categories.json", categories)
        _write_json(root / "lexicon.json", lexicons)
        _write_json(root / "organisations.json", orgs)
        _write_json(root / "document_types.json", types)
        meta: dict[str, Any] = {
            "email": email,
            "category": categories[0]["name"],
            "created_at": _now(),
            "would_route": would_route,
            "preview_id": preview_id,
            "organisations": orgs,
            "document_types": types,
            "llm_mode": llm_mode_from_meta({"llm_mode": llm_mode}),
        }
        if corpus_sha256:
            meta["corpus_sha256"] = corpus_sha256
            meta["corpus_built_on"] = corpus_built_on
            meta["corpus_n_pages"] = corpus_n_pages
        _write_json(root / "meta.json", meta)
        if scope:
            _write_json(root / "scope.json", scope)
        job = Job(root)
        job.write_status(status="queued")
        return job

    def get(self, job_id: str) -> Job:
        root = self.jobs_dir / job_id
        if not root.is_dir():
            raise FileNotFoundError(job_id)
        return Job(root)

    def _job_dirs(self) -> list[Job]:
        return [Job(path) for path in self.jobs_dir.iterdir() if path.is_dir()]

    def list_jobs(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for job in self._job_dirs():
            try:
                items.append(job.list_view())
            except _JOB_SCAN_ERRORS:
                continue
        items.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return items

    def queued(self) -> list[Job]:
        jobs: list[Job] = []
        for job in self._job_dirs():
            try:
                if job.read_status().get("status") == "queued":
                    jobs.append(job)
            except _JOB_SCAN_ERRORS:
                continue
        jobs.sort(key=lambda j: _job_created_at(j))
        return jobs

    def incomplete(self) -> list[Job]:
        out: list[Job] = []
        for job in self._job_dirs():
            try:
                if job.read_status().get("status") in {"queued", "running"}:
                    out.append(job)
            except _JOB_SCAN_ERRORS:
                continue
        return out

    def resumable_failed(self) -> list[Job]:
        """Failed runs that still have a live Anthropic-batch checkpoint."""
        out: list[Job] = []
        for job in self._job_dirs():
            try:
                if job.read_status().get("status") == "failed" and job.has_checkpoint():
                    out.append(job)
            except _JOB_SCAN_ERRORS:
                continue
        return out

    def today_key(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def routed_submitted_today(self) -> int:
        path = self.usage_dir / f"{self.today_key()}.json"
        if not path.exists():
            return 0
        return int(_read_json(path).get("routed_submitted") or 0)

    def add_routed_submitted(self, n: int) -> int:
        path = self.usage_dir / f"{self.today_key()}.json"
        current = self.routed_submitted_today()
        total = max(0, current + n)
        _write_json(path, {"date": self.today_key(), "routed_submitted": total})
        return total
