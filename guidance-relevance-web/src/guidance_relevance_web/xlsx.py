"""Kept/dropped workbook and GPE pages.json round-trip."""

from __future__ import annotations

import io
from typing import Any

from guidance_relevance_filter.funnel import stage_of
from openpyxl import Workbook, load_workbook

from .urls import normalize_govuk_url, require_govuk_url

COLUMNS = (
    "url", "title", "content_id", "is_withdrawn",
    "funnel_stage", "pass1_reason", "pass2_reason",
)


def _row(page: dict[str, Any]) -> dict[str, Any]:
    md = page.get("meta_data") or {}
    funnel = md.get("funnel") or {}
    return {
        "url": page.get("url") or "",
        "title": md.get("title") or "",
        "content_id": page.get("content_id") or "",
        "is_withdrawn": bool(md.get("is_withdrawn")),
        "funnel_stage": funnel.get("stage") or stage_of(page) or "",
        "pass1_reason": funnel.get("pass1_reason") or "",
        "pass2_reason": funnel.get("pass2_reason") or "",
    }


def split_kept_dropped(pages: list[dict], category: str) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    dropped: list[dict] = []
    for page in pages:
        md = page.get("meta_data") or {}
        if (md.get("labels") or {}).get(category) is True:
            kept.append(_row(page))
        else:
            dropped.append(_row(page))
    return kept, dropped


def workbook_bytes(kept: list[dict], dropped: list[dict]) -> bytes:
    wb = Workbook()
    kept_sheet = wb.active
    kept_sheet.title = "kept"
    dropped_sheet = wb.create_sheet("dropped")
    for sheet, rows in ((kept_sheet, kept), (dropped_sheet, dropped)):
        sheet.append(list(COLUMNS))
        for row in rows:
            sheet.append([row.get(c, "") for c in COLUMNS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _read_sheet(ws) -> list[dict[str, str]]:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(c or "").strip() for c in rows[0]]
    index = {name: i for i, name in enumerate(header)}
    if "url" not in index:
        raise ValueError(f"sheet {ws.title!r} has no url column")
    out: list[dict[str, str]] = []
    for raw in rows[1:]:
        if not raw or all(c is None or str(c).strip() == "" for c in raw):
            continue
        cells: dict[str, str] = {}
        for name in COLUMNS:
            i = index.get(name)
            if i is None or i >= len(raw) or raw[i] is None:
                cells[name] = ""
            else:
                cells[name] = str(raw[i]).strip()
        out.append(cells)
    return out


def parse_workbook(data: bytes) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        names = set(wb.sheetnames)
        if "kept" not in names:
            raise ValueError("workbook has no 'kept' sheet")
        kept = _read_sheet(wb["kept"])
        dropped = _read_sheet(wb["dropped"]) if "dropped" in names else []
        return kept, dropped
    finally:
        wb.close()


def pages_from_kept(
    kept_rows: list[dict[str, str]],
    original_kept_urls: set[str],
) -> dict[str, Any]:
    pages: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in kept_rows:
        url = require_govuk_url(row.get("url") or "")
        path_key = url
        if path_key in seen:
            continue
        seen.add(path_key)
        pages.append({
            "url": url,
            "title": row.get("title") or "",
            "content_id": row.get("content_id") or "",
        })
    original = {normalize_govuk_url(u) or u for u in original_kept_urls}
    current = {p["url"] for p in pages}
    added = len(current - original)
    removed = len(original - current)
    return {
        "producer_component": "guidance-relevance-web",
        "source_kind": "guidance",
        "component_id": "guidance-relevance-web",
        "category": "guidance-pages",
        "pages": pages,
        "accounting": {
            "n_pages": len(pages),
            "n_added": added,
            "n_removed": removed,
        },
    }


def original_kept_urls(pages: list[dict], category: str) -> set[str]:
    kept, _dropped = split_kept_dropped(pages, category)
    return {r["url"] for r in kept}
