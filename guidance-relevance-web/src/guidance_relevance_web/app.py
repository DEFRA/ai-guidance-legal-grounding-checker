"""FastAPI operator UI."""

from __future__ import annotations

import io
import json
import logging
import queue
import re
import threading
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from guidance_relevance_filter.annotate import STAGE_GUIDE
from markupsafe import Markup
from pydantic import BaseModel, field_validator

from .category import (
    category_document,
    is_slug,
    lexicon_document,
    packaged_templates,
    parse_hint_lines,
    parse_lexicon_lines,
    parse_scope_list,
    scope_options,
)
from .corpus import CorpusCatalog, CorpusError, UnknownCorpus
from .cost_estimate import llm_badge_html
from .funnel_view import (
    DOCUMENT_TYPE_MISS,
    DOCUMENT_TYPE_PASS,
    ORGANISATION_MISS,
    ORGANISATION_PASS,
    view_from_journal,
)
from .mailer import Mailer
from .preview import run_preview
from .settings import Settings, get_settings
from .store import Store
from .worker import Worker
from .xlsx import (
    original_kept_urls,
    pages_from_kept,
    parse_workbook,
    split_kept_dropped,
    workbook_bytes,
)

log = logging.getLogger(__name__)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PACKAGE = Path(__file__).resolve().parent
_ZIP_NAMES = ("output.json", "funnel.json", "metrics.json", "MODEL.md", "adjudication.json")
def _built_on_label(built_on: str | None) -> str | None:
    if not built_on:
        return built_on
    raw = str(built_on).strip()
    try:
        dt = datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError:
        return raw
    return f"{dt.day} {dt.strftime('%B %Y')}"


_EMPTY_WIZARD_FORM = {
    "name": "",
    "description": "",
    "exclusion_criteria": "",
    "keep_hints": "",
    "drop_hints": "",
    "lexicon": "",
    "organisations": [],
    "document_types": [],
    "corpus_id": "",
}


class PreviewIn(BaseModel):
    name: str
    description: str
    exclusion_criteria: str = ""
    keep_hints: str = ""
    drop_hints: str = ""
    lexicon: str = ""
    organisations: list[str] = []
    document_types: list[str] = []
    corpus_id: str = ""

    @field_validator("organisations", "document_types", mode="before")
    @classmethod
    def _scope_list_field(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return parse_scope_list(value)
        if isinstance(value, (list, tuple)):
            return parse_scope_list([str(v) for v in value])
        return parse_scope_list(str(value))


class JobIn(BaseModel):
    preview_id: str
    email: str
    name: str | None = None
    description: str | None = None
    exclusion_criteria: str | None = None
    keep_hints: str | None = None
    drop_hints: str | None = None
    lexicon: str | None = None
    llm_mode: Literal["batch", "sync"] = "batch"


def _asset_v() -> str:
    latest = 0
    for name in ("app.js", "style.css"):
        path = _PACKAGE / "static" / name
        try:
            latest = max(latest, path.stat().st_mtime_ns)
        except OSError:
            continue
    return str(latest)


def _templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(_PACKAGE / "templates"))


def _category_payload(data: PreviewIn | dict[str, Any]) -> tuple[list[dict], dict[str, list[str]]]:
    if isinstance(data, PreviewIn):
        name = data.name.strip()
        description = data.description
        exclusion = data.exclusion_criteria
        keep = parse_hint_lines(data.keep_hints)
        drop = parse_hint_lines(data.drop_hints)
        terms = parse_lexicon_lines(data.lexicon)
    else:
        name = str(data.get("name") or "").strip()
        description = str(data.get("description") or "")
        exclusion = str(data.get("exclusion_criteria") or "")
        keep = parse_hint_lines(str(data.get("keep_hints") or ""))
        drop = parse_hint_lines(str(data.get("drop_hints") or ""))
        terms = parse_lexicon_lines(str(data.get("lexicon") or ""))
    if not is_slug(name):
        raise HTTPException(
            400,
            "Name must use lowercase letters, numbers and underscores, "
            "for example animal_liquid_waste",
        )
    if not description.strip():
        raise HTTPException(400, "What to Include is required")
    if not exclusion.strip():
        raise HTTPException(400, "What to Exclude is required")
    if not terms:
        raise HTTPException(400, "Inclusion keywords must contain at least one term")
    categories = category_document(
        name=name,
        description=description,
        exclusion_criteria=exclusion,
        keep_hints=keep,
        drop_hints=drop,
    )
    return categories, lexicon_document(name, terms)


_SCOPE_STAGES = frozenset({
    ORGANISATION_MISS, ORGANISATION_PASS, DOCUMENT_TYPE_MISS, DOCUMENT_TYPE_PASS,
})


def _funnel_from_run(job) -> dict[str, Any] | None:
    path = job.output_dir / "funnel.json"
    if not path.exists():
        return None
    return view_from_journal(json.loads(path.read_text()), scope=job.read_scope())


def _scope_from_preview(preview: dict[str, Any]) -> dict[str, Any] | None:
    orgs = preview.get("organisations") or []
    types = preview.get("document_types") or []
    if not orgs and not types:
        return None
    result = preview.get("result") or {}
    counts = result.get("counts") or {}
    return {
        "organisations": orgs,
        "document_types": types,
        "counts": {
            "corpus_pages": counts.get("corpus_pages"),
            "input_pages": counts.get("input_pages"),
            "organisation_miss": counts.get("organisation_miss"),
            "document_type_miss": counts.get("document_type_miss"),
            "organisation_filter": counts.get("organisation_filter", bool(orgs)),
            "document_type_filter": counts.get("document_type_filter", bool(types)),
        },
        "stages": [
            s for s in result.get("stages") or []
            if s.get("stage") in _SCOPE_STAGES
        ],
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = Store(settings)
    catalog = CorpusCatalog(settings.grf_corpus)
    mailer = Mailer(settings)
    worker = Worker(store, settings, mailer, catalog)
    templates = _templates()
    templates.env.filters["tojson"] = lambda v: Markup(json.dumps(v))
    templates.env.globals["llm_mode"] = settings.grf_llm_mode
    templates.env.globals["llm_badge"] = Markup(
        llm_badge_html(settings.grf_llm_mode != "sync")
    )
    templates.env.globals["batch_badge"] = templates.env.globals["llm_badge"]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logging.basicConfig(level=logging.INFO)
        if settings.grf_enable_worker:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(title="Guidance Relevance Filter", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.catalog = catalog
    app.state.mailer = mailer
    app.state.worker = worker
    static = _PACKAGE / "static"
    static.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static)), name="static")
    app.mount("/assets", StaticFiles(directory=str(static / "govuk" / "assets")), name="govuk-assets")

    def ctx(request: Request, **extra: Any) -> dict[str, Any]:
        form = {**_EMPTY_WIZARD_FORM, **(extra.pop("form", None) or {})}
        snapshots = catalog.views()
        newest = snapshots[0] if snapshots else None
        selected = None
        corpus_id = str(form.get("corpus_id") or "")
        if corpus_id:
            selected = next((s for s in snapshots if s["id"] == corpus_id), None)
        if selected is None:
            selected = newest
        if newest is None:
            built_on, n_pages = None, None
            corpus_error = (
                f"No snapshots in {catalog.root}. "
                "See docs/updating-the-corpus.md."
            )
            organisation_options, document_type_options = scope_options([], [])
        else:
            built_on, n_pages, corpus_error = newest["built_on"], newest["n_pages"], None
            organisation_options, document_type_options = scope_options(
                selected.get("organisations") or [],
                selected.get("document_types") or [],
            )
        return {
            "request": request,
            "form": form,
            "job": extra.get("job"),
            "funnel": extra.get("funnel"),
            "built_on": built_on,
            "built_on_label": _built_on_label(built_on),
            "n_pages": n_pages,
            "snapshot_count": len(snapshots),
            "snapshots": snapshots,
            "corpus_error": corpus_error,
            "max_routed": settings.grf_max_routed,
            "daily_max": settings.grf_daily_max_routed,
            "daily_used": store.routed_submitted_today(),
            "templates_json": packaged_templates(),
            "document_type_options": document_type_options,
            "organisation_options": organisation_options,
            "stage_guide": STAGE_GUIDE,
            "nav": "",
            "llm_mode": settings.grf_llm_mode,
            "asset_v": _asset_v(),
            **extra,
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def wizard_page(request: Request, job=None) -> HTMLResponse:
        extra: dict[str, Any] = {"nav": "create"}
        if job is not None:
            extra["job"] = job.public_view()
            extra["llm_mode"] = extra["job"]["llm_mode"]
            extra["funnel"] = _funnel_from_run(job)
            extra["form"] = job.wizard_form()
        return templates.TemplateResponse(request, "wizard.html", ctx(request, **extra))

    @app.get("/", response_class=HTMLResponse)
    def wizard(request: Request) -> HTMLResponse:
        return wizard_page(request)

    @app.post("/preview")
    def preview(body: PreviewIn) -> StreamingResponse:
        try:
            corpus = catalog.get(body.corpus_id.strip() or None)
        except UnknownCorpus as e:
            raise HTTPException(400, str(e)) from e
        except CorpusError as e:
            raise HTTPException(503, str(e)) from e
        categories, lexicons = _category_payload(body)
        organisations = body.organisations
        document_types = body.document_types
        manifest = corpus.require()

        def events():
            q: queue.Queue[dict[str, Any] | None] = queue.Queue()
            boxed: dict[str, Any] = {}

            def on_progress(phase: str, done: int, total: int) -> None:
                q.put({"event": "progress", "phase": phase, "done": done, "total": total})

            def work() -> None:
                try:
                    boxed["result"] = run_preview(
                        corpus=corpus,
                        categories=categories,
                        lexicons=lexicons,
                        settings=settings,
                        store=store,
                        on_progress=on_progress,
                        organisations=organisations,
                        document_types=document_types,
                    )
                except Exception as e:
                    boxed["error"] = e
                finally:
                    q.put(None)

            thread = threading.Thread(target=work, name="grf-preview")
            thread.start()
            while True:
                item = q.get()
                if item is None:
                    break
                yield json.dumps(item) + "\n"
            thread.join()
            if "error" in boxed:
                yield json.dumps({"event": "error", "detail": str(boxed["error"])}) + "\n"
                return
            result = boxed["result"]
            preview_id = store.create_preview(
                categories=categories,
                lexicons=lexicons,
                counts=result["counts"],
                warnings=result["warnings"],
                stages=result["stages"],
                organisations=organisations,
                document_types=document_types,
                corpus_sha256=manifest.with_body_sha256,
                corpus_built_on=manifest.built_on,
                corpus_n_pages=manifest.n_pages,
            )
            daily = store.routed_submitted_today()
            would = result["counts"]["would_route"]
            daily_ok = daily + would <= settings.grf_daily_max_routed
            yield json.dumps({
                "event": "done",
                "preview_id": preview_id,
                **result,
                "daily": {
                    "used": daily,
                    "max": settings.grf_daily_max_routed,
                    "ok": daily_ok,
                },
            }) + "\n"

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache"},
        )

    @app.post("/jobs")
    def create_job(body: JobIn) -> JSONResponse:
        if not _EMAIL.match(body.email.strip()):
            raise HTTPException(400, "Please enter a valid email address")
        try:
            preview = store.load_preview(body.preview_id)
        except FileNotFoundError:
            raise HTTPException(400, "unknown or expired preview_id — run Preview again") from None
        would = int(preview["result"]["counts"]["would_route"])
        if would > settings.grf_max_routed:
            raise HTTPException(
                400,
                f"would_route {would} exceeds max-routed {settings.grf_max_routed}",
            )
        daily = store.routed_submitted_today()
        if daily + would > settings.grf_daily_max_routed:
            raise HTTPException(
                400,
                f"daily routed budget exceeded "
                f"({daily} + {would} > {settings.grf_daily_max_routed})",
            )
        pinned = preview.get("corpus") or {}
        job = store.create_job(
            email=str(body.email),
            categories=preview["categories"],
            lexicons=preview["lexicons"],
            would_route=would,
            preview_id=body.preview_id,
            organisations=preview.get("organisations") or [],
            document_types=preview.get("document_types") or [],
            scope=_scope_from_preview(preview),
            corpus_sha256=pinned.get("sha256"),
            corpus_built_on=pinned.get("built_on"),
            corpus_n_pages=pinned.get("n_pages"),
            llm_mode=body.llm_mode,
        )
        return JSONResponse({"id": job.id, "status": "queued"}, status_code=202)

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "jobs.html",
            ctx(request, nav="runs", jobs=store.list_jobs()),
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str) -> HTMLResponse:
        try:
            job = store.get(job_id)
        except FileNotFoundError:
            raise HTTPException(404, "job not found") from None
        return wizard_page(request, job)

    @app.get("/api/jobs/{job_id}")
    def job_api(job_id: str) -> dict[str, Any]:
        try:
            job = store.get(job_id)
        except FileNotFoundError:
            raise HTTPException(404, "job not found") from None
        view = job.public_view()
        view["funnel"] = _funnel_from_run(job)
        return view

    @app.post("/jobs/{job_id}/retry")
    def retry_job(request: Request, job_id: str) -> Response:
        try:
            job = store.get(job_id)
        except FileNotFoundError:
            raise HTTPException(404, "job not found") from None
        try:
            status = job.retry()
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        if "application/json" in (request.headers.get("accept") or ""):
            return JSONResponse({"id": job.id, "status": status.get("status")}, status_code=202)
        return RedirectResponse(f"/jobs/{job.id}#results", status_code=303)

    @app.get("/jobs/{job_id}/download.zip")
    def download_zip(job_id: str) -> Response:
        try:
            job = store.get(job_id)
        except FileNotFoundError:
            raise HTTPException(404, "job not found") from None
        if job.phase() != "done" and job.read_status().get("status") not in {
            "done", "blocked_cap", "failed",
        }:
            raise HTTPException(409, "run is not finished")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in _ZIP_NAMES:
                path = job.output_dir / name
                if path.is_file():
                    zf.write(path, arcname=name)
        return Response(
            buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.zip"'},
        )

    @app.get("/jobs/{job_id}/pages.xlsx")
    def download_xlsx(job_id: str) -> Response:
        try:
            job = store.get(job_id)
        except FileNotFoundError:
            raise HTTPException(404, "job not found") from None
        output = job.output_dir / "output.json"
        if not output.exists():
            raise HTTPException(409, "run has no output.json yet")
        pages = json.loads(output.read_text())
        cat = job.read_meta()["category"]
        kept, dropped = split_kept_dropped(pages, cat)
        data = workbook_bytes(kept, dropped)
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{job_id}-pages.xlsx"'},
        )

    @app.post("/jobs/{job_id}/pages")
    async def upload_pages(job_id: str, file: UploadFile) -> JSONResponse:
        try:
            job = store.get(job_id)
        except FileNotFoundError:
            raise HTTPException(404, "job not found") from None
        output = job.output_dir / "output.json"
        if not output.exists():
            raise HTTPException(409, "run has no output.json yet")
        raw = await file.read()
        try:
            kept_rows, _dropped_rows = parse_workbook(raw)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        pages = json.loads(output.read_text())
        cat = job.read_meta()["category"]
        try:
            payload = pages_from_kept(kept_rows, original_kept_urls(pages, cat))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        dest = job.root / "pages.json"
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return JSONResponse({"ok": True, "path": str(dest), **payload["accounting"]})

    return app
