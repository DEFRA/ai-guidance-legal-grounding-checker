"""
Fetch GOV.UK guidance pages via the Search API and write pipeline-format JSON.

Stage 1 of Guidance Discovery: discovery. Returns metadata only — body_text is added later by
stage 2 (fetch_body.py). The two static filters that decide the entire corpus
live in filters.py (ORGANISATIONS, DOCUMENT_TYPES); tuning lives in config.py.

No retry: any non-200 response aborts the run loudly rather than returning a
silently truncated corpus.

Output format matches the categorisation pipeline (Guidance Relevance Filter's input shape):
    [{"url": "...", "content_id": "...", "meta_data": {"title": ..., ...}}]

Usage:
    python get_defra_guidance_pages.py [output.json]
"""

import json
import sys
from pathlib import Path

import httpx
import typer

# Resolve sibling modules explicitly from this file's directory, rather than
# relying on the implicit current-working-directory entry on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    DEFAULT_SEARCH_OUTPUT,
    PAGE_SIZE,
    REQUEST_TIMEOUT,
    SEARCH_API_URL,
    SEARCH_DEBUG,
    SEARCH_FIELDS,
)
from filters import DOCUMENT_TYPES, ORGANISATIONS  # noqa: E402
from page import PageItem, organisation_slugs, primary_organisation_slug  # noqa: E402


def search_request_params(*, start: int = 0) -> dict:
    """Query string for one Search API page. Includes withdrawn documents."""
    return {
        "filter_organisations[]": ORGANISATIONS,
        "filter_content_store_document_type[]": DOCUMENT_TYPES,
        "fields": SEARCH_FIELDS,
        "count": PAGE_SIZE,
        "start": start,
        "debug": SEARCH_DEBUG,
    }


def search_all_pages() -> list[dict]:
    """Page through the GOV.UK Search API and return every in-scope raw result.

    Pure offset pagination over the two filters — no query, no ranking. Fails
    loudly: a non-200 aborts, and a final count that disagrees with the API's
    reported total raises rather than silently returning a short list.
    Withdrawn pages are included (``debug=include_withdrawn``); they are
    excluded from public search by default.
    """
    params = search_request_params()

    all_results: list[dict] = []
    total: int | None = None

    print("Fetching data from GOV.UK Search API...")
    while total is None or params["start"] < total:
        response = httpx.get(
            SEARCH_API_URL, params=params, timeout=REQUEST_TIMEOUT, follow_redirects=True
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Search API returned HTTP {response.status_code} at start="
                f"{params['start']} — aborting (no retry)."
            )

        data = response.json()
        total = data.get("total", 0)
        all_results.extend(data.get("results", []))
        print(f"Retrieved {len(all_results)} of {total} pages...")

        params["start"] += PAGE_SIZE

    if len(all_results) != total:
        raise RuntimeError(
            f"Incomplete discovery: collected {len(all_results)} results but the "
            f"Search API reported {total} — refusing to write a truncated corpus."
        )

    return all_results


def to_pipeline_item(result: dict) -> PageItem:
    """Reshape one Search API hit into Guidance Discovery's page contract (metadata only)."""
    link = result.get("link", "")
    return {
        "url": f"https://www.gov.uk{link}",
        "content_id": result.get("content_id", ""),
        "meta_data": {
            "title":         result.get("title", ""),
            "description":   result.get("description", ""),
            "updated_at":    result.get("public_timestamp", ""),
            "document_type": result.get("content_store_document_type", ""),
            "view_count":    result.get("view_count", 0),
            "organisations": organisation_slugs(result.get("organisations")),
            "primary_publishing_organisation": primary_organisation_slug(
                result.get("primary_publishing_organisation")
            ),
            "is_withdrawn": result.get("is_withdrawn") is True,
        },
    }


def run(output_path: str) -> None:
    items = [to_pipeline_item(r) for r in search_all_pages()]

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, indent=2))
    print(f"Saved {len(items)} items to '{output_path}'.")


def main(
    output_path: str = typer.Argument(
        DEFAULT_SEARCH_OUTPUT, help="Path to write the discovery JSON"
    ),
) -> None:
    run(output_path)


if __name__ == "__main__":
    typer.run(main)
