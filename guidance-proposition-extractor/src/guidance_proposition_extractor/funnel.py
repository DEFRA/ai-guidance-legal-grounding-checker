"""URL drop journals for prepare (off-topic filter) and extract (excluded pages)."""
from __future__ import annotations

from collections import Counter
from typing import Any


def page_ref(
    url: str,
    *,
    title: str = "",
    content_id: str = "",
    **extra: Any,
) -> dict[str, Any]:
    rec: dict[str, Any] = {"url": url, "title": title, "content_id": content_id}
    rec.update({k: v for k, v in extra.items() if v is not None})
    return rec


def prepare_journal(
    *,
    category: str,
    source_n: int,
    kept: list[dict],
    dropped: list[dict],
) -> dict:
    by_stage = dict(Counter(d.get("stage") or "unstamped" for d in dropped))
    return {
        "category": category,
        "counts": {
            "source_rows": source_n,
            "kept": len(kept),
            "dropped_not_on_topic": len(dropped),
            "dropped_by_stage": by_stage,
        },
        "kept": [
            page_ref(p["url"], title=p.get("title") or "", content_id=p.get("content_id") or "")
            for p in kept
        ],
        "dropped_not_on_topic": dropped,
    }


def run_journal(
    *,
    pages: list[dict],
    extracted: dict[str, dict],
    excluded: list[dict],
) -> dict:
    extracted_urls = set(extracted)
    excluded_urls = {e["url"] for e in excluded}
    extracted_rows = [
        page_ref(
            url,
            title=(row.get("meta_data") or {}).get("title") or "",
            content_id=row.get("content_id") or "",
            n_propositions=len((row.get("meta_data") or {}).get("propositions") or []),
        )
        for url, row in extracted.items()
    ]
    not_yet = [
        page_ref(p["url"], title=p.get("title") or "", content_id=p.get("content_id") or "")
        for p in pages
        if p["url"] not in extracted_urls and p["url"] not in excluded_urls
    ]
    return {
        "counts": {
            "input_pages": len(pages),
            "extracted": len(extracted),
            "excluded": len(excluded),
            "not_yet_processed": len(not_yet),
        },
        "extracted": extracted_rows,
        "excluded": excluded,
        "not_yet_processed": not_yet,
    }
