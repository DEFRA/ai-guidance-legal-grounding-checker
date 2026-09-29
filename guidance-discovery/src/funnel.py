"""Discovery funnel: every URL the body-fetch stage added, emptied, or failed.

Stage 1 does not drop URLs (it aborts on a truncated Search API response).
Stage 2 can: a Content API failure leaves ``body_text=None``, a page with no
body leaves ``body_text=""``, and HTML chapters appear that the Search API
never returned. ``funnel.json`` sits next to ``with_body.json`` and lists
those URLs so a miss can be attributed without grepping stdout.
"""
from __future__ import annotations

from typing import Any


def page_ref(item: dict, **extra: Any) -> dict[str, Any]:
    md = item.get("meta_data") or {}
    rec: dict[str, Any] = {
        "url": item.get("url"),
        "title": md.get("title") or "",
        "document_type": md.get("document_type") or "",
    }
    rec.update(extra)
    return rec


def journal(input_items: list[dict], output: list[dict]) -> dict:
    """Build ``funnel.json`` from stage-1 input and stage-2 assembled output."""
    input_urls = {i["url"] for i in input_items}
    parent_of: dict[str, str] = {}
    for item in output:
        for child_url in (item.get("meta_data") or {}).get("html_publication_urls") or []:
            parent_of[child_url] = item["url"]

    fetch_failed: list[dict] = []
    body_empty: list[dict] = []
    body_present: list[dict] = []
    chapters: list[dict] = []
    output_urls: set[str] = set()

    for item in output:
        url = item["url"]
        output_urls.add(url)
        md = item.get("meta_data") or {}
        body = md.get("body_text")
        extra: dict[str, Any] = {}
        if url in parent_of:
            extra["parent_url"] = parent_of[url]
        rec = page_ref(item, **extra)
        if url not in input_urls:
            chapters.append(rec)
        if body is None:
            if md.get("fetch_error"):
                rec = {**rec, "fetch_error": md["fetch_error"]}
            fetch_failed.append(rec)
        elif body == "":
            body_empty.append(rec)
        else:
            body_present.append(page_ref(item))

    search_hits_missing = [
        page_ref(i) for i in input_items if i["url"] not in output_urls
    ]

    return {
        "counts": {
            "search_hits": len(input_items),
            "chapters_expanded": len(chapters),
            "output_pages": len(output),
            "body_present": len(body_present),
            "body_empty": len(body_empty),
            "fetch_failed": len(fetch_failed),
            "search_hits_missing_from_output": len(search_hits_missing),
        },
        "fetch_failed": fetch_failed,
        "body_empty": body_empty,
        "chapters_expanded": chapters,
        "search_hits_missing_from_output": search_hits_missing,
    }
