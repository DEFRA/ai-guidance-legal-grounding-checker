"""Join a URL CSV against a finished Guidance Relevance Filter run.

Indexes ``output.json`` (preferred) or ``funnel.json``, matches each CSV URL by
gov.uk path, and appends ``funnel_stage`` / ``funnel_reason``.
"""
from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .funnel import (
    COSINE_MISS,
    EMPTY_BODY,
    LEXICON_MISS,
    MISSING_BODY,
    PASS1_FALSE,
    PASS2_DROP,
    PASS2_KEEP,
    PASS2_UNADJUDICATED,
    ROUTING_MISS_STAGES,
)

NOT_IN_CORPUS = "not_in_corpus"
NOT_IN_CORPUS_REASON = "not in relevance-filter output"

FUNNEL_STAGE_COL = "funnel_stage"
FUNNEL_REASON_COL = "funnel_reason"

DEFAULT_URL_COLUMN = "url"
URL_COLUMN_FALLBACKS = (DEFAULT_URL_COLUMN, "Original URL", "clened-urls")

STAGE_KEYS = (
    MISSING_BODY,
    EMPTY_BODY,
    LEXICON_MISS,
    COSINE_MISS,
    PASS1_FALSE,
    PASS2_DROP,
    PASS2_KEEP,
    PASS2_UNADJUDICATED,
)

# Pipeline order for humans: each URL dies at the first rejecting stage.
# The last two are both "survived pass 2" outcomes, not sequential drops.
STAGE_GUIDE: tuple[tuple[str, str, str], ...] = (
    (
        NOT_IN_CORPUS,
        "Never reached the filter",
        "This URL was not in the run at all. The filter never saw it — usually "
        "it was never fetched, or the address didn't match.",
    ),
    (
        MISSING_BODY,
        "Couldn't download the page",
        "The page was in the corpus, but fetching its text failed. No model was asked.",
    ),
    (
        EMPTY_BODY,
        "Page has no text",
        "The page exists but the body was empty. No model was asked.",
    ),
    (
        LEXICON_MISS,
        "No topic keywords",
        "A word-search of the title and body found none of the topic's keywords. "
        "Rejected before any AI call.",
    ),
    (
        COSINE_MISS,
        "Below similarity threshold",
        "Embedding similarity against the category was below the cosine "
        "threshold. Rejected before any AI call.",
    ),
    (
        PASS1_FALSE,
        "First AI pass said no",
        "The cheap gate routed the page, so a cheap model read it and decided "
        "it is not about the topic. Stopped here.",
    ),
    (
        PASS2_DROP,
        "Second AI pass said no",
        "The first model said yes (any mention counts). A stricter model then "
        "re-read it with the exclusion rules and dropped it — a passing mention, "
        "the wrong meaning of a word, or the wrong subject.",
    ),
    (
        PASS2_UNADJUDICATED,
        "Second pass failed; kept anyway",
        "The first model said yes, but the second model's answer couldn't be "
        "read. We keep it rather than silently dropping it.",
    ),
    (
        PASS2_KEEP,
        "Kept — on topic",
        "Both passes agreed the page is about the topic. This is a keeper.",
    ),
)

_GOVUK_PATH = re.compile(r"https?:/+www\.gov\.uk(/[^?\s#]*)", re.IGNORECASE)


class AnnotateError(Exception):
    """User-facing join failure (missing file, missing column, bad JSON)."""


def govuk_path(url: str) -> str | None:
    """Public gov.uk path, with Content-API prefix and trailing slash stripped."""
    url = (url or "").strip()
    if not url:
        return None
    m = _GOVUK_PATH.search(url)
    path = m.group(1).rstrip("/") if m else urlparse(url).path.rstrip("/")
    if path.startswith("/api/content/"):
        path = path[len("/api/content") :]
    return path or None


def drop_reason(rec: dict) -> str:
    """Deciding text for a funnel record (notebook ``drop_reason`` rules)."""
    stage = str(rec.get("stage") or "")
    if stage == PASS2_DROP:
        tag = rec.get("exclusion_hit") or ""
        body = rec.get("pass2_reason") or rec.get("reason") or ""
        return f"[{tag}] {body}".strip()
    if stage == PASS1_FALSE:
        return rec.get("pass1_reason") or rec.get("reason") or ""
    if stage in {*ROUTING_MISS_STAGES, EMPTY_BODY, MISSING_BODY}:
        return rec.get("reason") or rec.get("fetch_error") or stage
    return rec.get("pass2_reason") or rec.get("pass1_reason") or rec.get("reason") or ""


def _first_reason(reasons: Any) -> str:
    if isinstance(reasons, dict):
        for value in reasons.values():
            if value:
                return str(value)
    return ""


def record_from_output_page(page: dict) -> dict:
    md = page.get("meta_data") or {}
    funnel = md.get("funnel") or {}
    return {
        "url": page.get("url") or "",
        "stage": funnel.get("stage") or "",
        "pass1_reason": funnel.get("pass1_reason") or "",
        "pass2_reason": funnel.get("pass2_reason") or "",
        "exclusion_hit": funnel.get("exclusion_hit") or "",
        "fetch_error": funnel.get("fetch_error") or "",
        "reason": _first_reason(md.get("reasons")),
    }


def _index_records(records: list[dict]) -> dict[str, dict]:
    by_path: dict[str, dict] = {}
    for rec in records:
        path = govuk_path(rec.get("url") or "")
        if path:
            by_path[path] = rec
    return by_path


def index_output_json(pages: list[dict]) -> dict[str, dict]:
    return _index_records([record_from_output_page(p) for p in pages])


def index_funnel_json(doc: dict) -> dict[str, dict]:
    records: list[dict] = []
    for stage in STAGE_KEYS:
        for rec in doc.get(stage) or []:
            row = dict(rec)
            row.setdefault("stage", stage)
            records.append(row)
    return _index_records(records)


def index_loaded(payload: Any, name: str = "artifact") -> dict[str, dict]:
    if isinstance(payload, list):
        return index_output_json(payload)
    if isinstance(payload, dict) and any(k in payload for k in STAGE_KEYS):
        return index_funnel_json(payload)
    raise AnnotateError(
        f"{name} is neither a pages list (output.json) nor a funnel journal"
    )


def index_payload(name: str, data: bytes | str) -> dict[str, dict]:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as e:
        raise AnnotateError(f"{name} is not valid JSON") from e
    return index_loaded(payload, name)


def load_run(path: Path) -> dict[str, dict]:
    """Index a run directory, ``output.json``, or ``funnel.json``."""
    path = Path(path)
    if not path.exists():
        raise AnnotateError(f"No such file or directory: {path}")
    if path.is_dir():
        output = path / "output.json"
        funnel = path / "funnel.json"
        if output.exists():
            return index_payload(output.name, output.read_text())
        if funnel.exists():
            return index_payload(funnel.name, funnel.read_text())
        raise AnnotateError(f"{path} has neither output.json nor funnel.json")
    return index_payload(path.name, path.read_text())


def resolve_url_column(fieldnames: list[str], url_column: str | None) -> str:
    if url_column is not None:
        if url_column not in fieldnames:
            raise AnnotateError(
                f"Column {url_column!r} not in CSV (have: {', '.join(fieldnames)})"
            )
        return url_column
    for candidate in URL_COLUMN_FALLBACKS:
        if candidate in fieldnames:
            return candidate
    raise AnnotateError(
        f"No URL column found. Tried {', '.join(URL_COLUMN_FALLBACKS)}. "
        f"Have: {', '.join(fieldnames)}"
    )


def annotate_row(index: dict[str, dict], url: str) -> tuple[str, str]:
    path = govuk_path(url)
    hit = index.get(path) if path else None
    if not hit:
        return NOT_IN_CORPUS, NOT_IN_CORPUS_REASON
    return str(hit.get("stage") or NOT_IN_CORPUS), drop_reason(hit)


def annotate_rows(
    rows: list[dict],
    fieldnames: list[str],
    index: dict[str, dict],
    url_column: str,
) -> tuple[list[dict], list[str], Counter]:
    out_fields = list(fieldnames)
    for col in (FUNNEL_STAGE_COL, FUNNEL_REASON_COL):
        if col not in out_fields:
            out_fields.append(col)
    counts: Counter = Counter()
    annotated: list[dict] = []
    for row in rows:
        stage, reason = annotate_row(index, row.get(url_column) or "")
        counts[stage] += 1
        annotated.append({**row, FUNNEL_STAGE_COL: stage, FUNNEL_REASON_COL: reason})
    return annotated, out_fields, counts


def read_csv_text(text: str) -> tuple[list[dict], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise AnnotateError("CSV has no header row")
    return list(reader), list(reader.fieldnames)


def read_csv(path: Path) -> tuple[list[dict], list[str]]:
    return read_csv_text(path.read_text(encoding="utf-8-sig"))


def write_csv_string(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(write_csv_string(rows, fieldnames), encoding="utf-8")


def default_output_path(csv_path: Path) -> Path:
    return csv_path.with_name(f"{csv_path.stem}-funnel.csv")


def explain_csv(
    csv_path: Path,
    run_path: Path,
    output_path: Path | None = None,
    url_column: str | None = None,
) -> tuple[Path, Counter]:
    rows, fieldnames = read_csv(csv_path)
    column = resolve_url_column(fieldnames, url_column)
    index = load_run(run_path)
    annotated, out_fields, counts = annotate_rows(rows, fieldnames, index, column)
    dest = output_path or default_output_path(csv_path)
    write_csv(dest, annotated, out_fields)
    return dest, counts


def format_histogram(counts: Counter) -> str:
    order = (NOT_IN_CORPUS, *STAGE_KEYS)
    parts = [f"{stage}={counts[stage]}" for stage in order if counts.get(stage)]
    extras = [f"{stage}={n}" for stage, n in sorted(counts.items()) if stage not in order]
    return " ".join(parts + extras)
