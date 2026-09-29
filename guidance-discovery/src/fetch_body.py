"""
Fetch full gov.uk page body text for pipeline-format items.

Stage 2 of Guidance Discovery: body fetch. Reads pipeline JSON (list of {url, content_id,
meta_data}) and fetches the gov.uk content API for each item, adding body_text
to meta_data. Restartable: URLs already present in the output file with a
non-empty body_text are skipped — that output file doubles as the run cache.
Empty bodies are retried (collections/manuals used to extract as empty).

HTML-attachment chapters (`html_publication`) are not in the Search API. After
each successful parent fetch, stage 2 reads `links.children` (falling back to
`details.attachments`) and enqueues those chapters as extra corpus items —
same Content API, same page contract, not concatenated into the parent.

A failed fetch is recorded as body_text=None (not dropped) so a re-run retries
it; the final summary counts and reports those failures loudly.

Usage:
    python fetch_body.py [input.json] [output.json]

Optional:
    --concurrency 3       Max concurrent requests (default: from config)
    --rate 10.0           Max requests per second (default: from config)
"""

import asyncio
import html
import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx
import typer

# Resolve sibling modules explicitly from this file's directory, rather than
# relying on the implicit current-working-directory entry on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    CONTENT_API_BASE,
    DEFAULT_BODY_OUTPUT,
    DEFAULT_CONCURRENCY,
    DEFAULT_RATE,
    DEFAULT_SEARCH_OUTPUT,
    INITIAL_BACKOFF,
    MAX_BACKOFF,
    MAX_RETRIES,
    PROGRESS_EVERY,
    REQUEST_TIMEOUT,
)
from funnel import journal as funnel_journal  # noqa: E402
from page import (  # noqa: E402
    PageItem,
    organisation_slugs,
    primary_organisation_slug,
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "li", "h1", "h2", "h3", "h4", "td", "th"):
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.chunks.append(data)


def _html_to_text(raw_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html.unescape(raw_html))
    text = "".join(parser.chunks)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _html_segment(raw: str | None) -> str:
    """HTML → text, treating missing/whitespace as empty so we fall through to other fields."""
    if not raw or not str(raw).strip():
        return ""
    return _html_to_text(str(raw))


def _collection_text(content: dict) -> str:
    """Index text for a document_collection: group headings + member titles.

    Collections put their visible content in ``details.collection_groups`` and
    ``links.documents``, not ``details.body`` (which is often ``" \\n "``).
    """
    details = content.get("details") or {}
    docs_by_id = {
        d["content_id"]: d
        for d in (content.get("links") or {}).get("documents") or []
        if d.get("content_id")
    }
    chunks: list[str] = []
    seen_ids: set[str] = set()
    for group in details.get("collection_groups") or []:
        title = (group.get("title") or "").strip()
        if title:
            chunks.append(title)
        group_body = _html_segment(group.get("body"))
        if group_body:
            chunks.append(group_body)
        for doc_id in group.get("documents") or []:
            seen_ids.add(doc_id)
            doc_title = (docs_by_id.get(doc_id) or {}).get("title") or ""
            if doc_title.strip():
                chunks.append(doc_title.strip())
    if not chunks:
        for doc in (content.get("links") or {}).get("documents") or []:
            title = (doc.get("title") or "").strip()
            if title:
                chunks.append(title)
    return "\n".join(chunks)


def _manual_toc_text(details: dict) -> str:
    """TOC text for a manual: section titles + descriptions.

    Manual parents put their visible content in ``details.child_section_groups``;
    the prose lives on ``manual_section`` children.
    """
    chunks: list[str] = []
    for group in details.get("child_section_groups") or []:
        group_title = (group.get("title") or "").strip()
        if group_title:
            chunks.append(group_title)
        for section in group.get("child_sections") or []:
            title = (section.get("title") or "").strip()
            description = (section.get("description") or "").strip()
            if title:
                chunks.append(title)
            if description:
                chunks.append(description)
    return "\n".join(chunks)


def _extract_body_text(content: dict) -> str:
    details = content.get("details") or {}
    segments: list[str] = []
    body = _html_segment(details.get("body"))
    if body:
        segments.append(body)
    parts = [
        _html_segment(p.get("body"))
        for p in details.get("parts") or []
    ]
    segments.extend(p for p in parts if p)
    collection = _collection_text(content)
    if collection:
        segments.append(collection)
    toc = _manual_toc_text(details)
    if toc:
        segments.append(toc)
    return "\n\n".join(segments)


def _govuk_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return f"https://www.gov.uk{path}"


def _child_item(*, url: str, content_id: str = "", title: str = "", updated_at: str = "") -> dict:
    return {
        "url": url,
        "content_id": content_id,
        "meta_data": {
            "title": title,
            "description": "",
            "updated_at": updated_at,
            "document_type": "html_publication",
            "view_count": 0,
            "organisations": [],
            "primary_publishing_organisation": "",
            "is_withdrawn": False,
        },
    }


def _organisations_from_content(content: dict) -> tuple[list[str], str]:
    links = content.get("links") or {}
    return (
        organisation_slugs(links.get("organisations")),
        primary_organisation_slug(links.get("primary_publishing_organisation")),
    )


def _fill_organisations(md: dict, content: dict) -> None:
    """Backfill org slugs from Content API links when stage 1 didn't stamp them."""
    orgs, primary = _organisations_from_content(content)
    if not md.get("organisations"):
        md["organisations"] = orgs
    if not md.get("primary_publishing_organisation"):
        md["primary_publishing_organisation"] = primary


def _fill_withdrawn(md: dict, content: dict) -> None:
    """Stamp is_withdrawn from Content API notice; never clear a Search API True."""
    notice = content.get("withdrawn_notice") or {}
    if isinstance(notice, dict) and (
        notice.get("withdrawn_at") or notice.get("explanation")
    ):
        md["is_withdrawn"] = True
    elif "is_withdrawn" not in md:
        md["is_withdrawn"] = False


def _inherit_organisations(parent_md: dict, children: list[dict]) -> None:
    """Copy parent org slugs onto children that still have empty fields.

    html_publication chapters often have no organisations of their own on the
    Content API. Never overwrite a value the child already has.
    """
    orgs = list(parent_md.get("organisations") or [])
    primary = parent_md.get("primary_publishing_organisation") or ""
    for child in children:
        child_md = child["meta_data"]
        if not child_md.get("organisations"):
            child_md["organisations"] = list(orgs)
        if not child_md.get("primary_publishing_organisation"):
            child_md["primary_publishing_organisation"] = primary


def _inherit_organisations_from_parents(items: list[dict]) -> None:
    """Fill empty chapter org fields from each parent in `html_publication_urls`.

    Applied at assemble time so it covers a fresh fetch, a restart (children
    fetched as stubs without the parent in-flight), and a cache-only re-run.
    """
    by_url = {item["url"]: item for item in items}
    for item in items:
        children = [
            by_url[url]
            for url in (item.get("meta_data") or {}).get("html_publication_urls") or []
            if url in by_url
        ]
        if children:
            _inherit_organisations(item["meta_data"], children)


def _html_publication_children(content: dict) -> list[dict]:
    """HTML-attachment chapters on a parent publication, as pipeline items.

    Prefer `links.children` (has content_id). Fall back to HTML entries in
    `details.attachments` when the links block is missing. Deduped by URL.
    """
    by_url: dict[str, dict] = {}

    for link in (content.get("links") or {}).get("children") or []:
        if (link.get("document_type") or "") != "html_publication":
            continue
        base_path = link.get("base_path") or ""
        if not base_path:
            continue
        item = _child_item(
            url=_govuk_url(base_path),
            content_id=link.get("content_id") or "",
            title=link.get("title") or "",
            updated_at=link.get("public_updated_at") or "",
        )
        by_url[item["url"]] = item

    if not by_url:
        for att in (content.get("details") or {}).get("attachments") or []:
            if (att.get("attachment_type") or "") != "html":
                continue
            path = att.get("url") or ""
            if not path:
                continue
            item = _child_item(
                url=_govuk_url(path),
                title=att.get("title") or "",
            )
            by_url.setdefault(item["url"], item)

    return list(by_url.values())


def _is_publication_parent(url: str) -> bool:
    """True for `/government/publications/{slug}` — not a chapter, not a collection."""
    parts = [p for p in urlparse(url).path.rstrip("/").split("/") if p]
    return len(parts) == 3 and parts[0] == "government" and parts[1] == "publications"


def _should_fetch(url: str, cached: dict | None) -> bool:
    """Fetch if uncached, failed/empty last time, or an old publication parent never expanded."""
    if cached is None:
        return True
    body = cached.get("meta_data", {}).get("body_text")
    if body is None or not str(body).strip():
        return True
    if "html_publication_urls" in cached.get("meta_data", {}):
        return False
    return _is_publication_parent(url)


def _child_stub(url: str, existing: dict[str, dict]) -> dict:
    if url in existing:
        return existing[url]
    return _child_item(url=url)


def _items_to_fetch(input_items: list[dict], existing: dict[str, dict]) -> list[dict]:
    """Input pages (and cached parents' known chapters) that still need a Content API call."""
    work: list[dict] = []
    seen: set[str] = set()

    def add(item: dict) -> None:
        url = item["url"]
        if url in seen:
            return
        seen.add(url)
        cached = existing.get(url)
        if _should_fetch(url, cached):
            work.append(item)
            return
        if cached is None:
            return
        for child_url in cached.get("meta_data", {}).get("html_publication_urls") or []:
            add(_child_stub(child_url, existing))

    for item in input_items:
        add(item)
    return work


def _assemble_output(input_items: list[dict], existing: dict[str, dict]) -> list[dict]:
    """Input order, then discovered html_publication chapters (parent order, then links order)."""
    input_urls = [i["url"] for i in input_items]
    input_set = set(input_urls)
    child_order: list[str] = []
    seen: set[str] = set()

    def walk(url: str) -> None:
        item = existing.get(url)
        if not item:
            return
        for child_url in item.get("meta_data", {}).get("html_publication_urls") or []:
            if child_url in input_set or child_url in seen:
                continue
            seen.add(child_url)
            child_order.append(child_url)
            walk(child_url)

    for url in input_urls:
        walk(url)

    output = [existing[url] for url in input_urls + child_order if url in existing]
    _inherit_organisations_from_parents(output)
    return output


def _record_fetch_failure(
    result: dict,
    counters: dict,
    *,
    http_status: int | None = None,
    error: str | None = None,
) -> None:
    """Stamp a failed fetch onto the page (body_text=None + fetch_error)."""
    md = result["meta_data"]
    md["body_text"] = None
    fail: dict = {}
    if http_status is not None:
        fail["http_status"] = http_status
    if error is not None:
        fail["error"] = error
    md["fetch_error"] = fail
    counters["errors"] += 1


def _url_to_api_url(url: str) -> str:
    path = urlparse(url).path
    return f"{CONTENT_API_BASE}/api/content{path}"


class RateLimiter:
    def __init__(self, rate: float) -> None:
        self.rate = rate
        self.tokens = rate
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(self.rate, self.tokens + (now - self.last_refill) * self.rate)
            self.last_refill = now
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1


async def _fetch_one(
    client: httpx.AsyncClient,
    item: dict,
    rate_limiter: RateLimiter,
    counters: dict,
) -> tuple[dict, list[dict]]:
    await rate_limiter.acquire()
    api_url = _url_to_api_url(item["url"])
    result = {**item, "meta_data": dict(item.get("meta_data", {}))}
    children: list[dict] = []
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.get(api_url)
            if response.status_code == 200:
                content = response.json()
                children = _html_publication_children(content)
                md = result["meta_data"]
                md["body_text"] = _extract_body_text(content)
                md.pop("fetch_error", None)
                md["html_publication_urls"] = [c["url"] for c in children]
                _fill_organisations(md, content)
                _fill_withdrawn(md, content)
                if not md.get("title"):
                    md["title"] = content.get("title") or ""
                if not md.get("description"):
                    md["description"] = content.get("description") or ""
                if not md.get("updated_at"):
                    md["updated_at"] = content.get("public_updated_at") or ""
                if not md.get("document_type"):
                    md["document_type"] = content.get("document_type") or ""
                if not result.get("content_id"):
                    result["content_id"] = content.get("content_id") or ""
                counters["ok"] += 1
                break
            elif response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", backoff))
                print(f"  429 rate limited: {item['url']} — waiting {retry_after:.0f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                await asyncio.sleep(retry_after)
                backoff = min(backoff * 2, MAX_BACKOFF)
            else:
                _record_fetch_failure(result, counters, http_status=response.status_code)
                print(f"  HTTP {response.status_code}: {item['url']}")
                break
        except httpx.HTTPError as e:
            _record_fetch_failure(result, counters, error=str(e))
            print(f"  Network error: {item['url']} — {e}")
            break
    else:
        _record_fetch_failure(result, counters, http_status=429, error="max retries")
        print(f"  Gave up after {MAX_RETRIES} retries: {item['url']}")

    counters["done"] += 1
    if counters["done"] % PROGRESS_EVERY == 0:
        print(f"  Progress: {counters['done']}/{counters['total']} "
              f"(ok={counters['ok']}, errors={counters['errors']})")
    return result, children


_STOP = object()


async def _fetch_all(
    items: list[dict],
    concurrency: int,
    rate: float,
    skip_urls: set[str],
) -> list[dict]:
    """Fetch `items`, enqueueing html_publication children as they appear.

    `skip_urls` are already-cached bodies — listed on the parent but not fetched
    again. Result order is irrelevant; run() reassembles.
    """
    if not items:
        return []

    rate_limiter = RateLimiter(rate)
    counters = {"done": 0, "ok": 0, "errors": 0, "total": len(items)}
    results: list[dict] = []
    queue: asyncio.Queue = asyncio.Queue()
    enqueued: set[str] = set()
    enqueued_lock = asyncio.Lock()

    for item in items:
        enqueued.add(item["url"])
        queue.put_nowait(item)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        async def worker() -> None:
            while True:
                item = await queue.get()
                try:
                    if item is _STOP:
                        return
                    result, children = await _fetch_one(client, item, rate_limiter, counters)
                    results.append(result)
                    for child in children:
                        if child["url"] in skip_urls:
                            continue
                        async with enqueued_lock:
                            if child["url"] in enqueued:
                                continue
                            enqueued.add(child["url"])
                            counters["total"] += 1
                            queue.put_nowait(child)
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await queue.join()
        for _ in workers:
            queue.put_nowait(_STOP)
        await asyncio.gather(*workers)

    return results


def _report(output: list[PageItem], output_path: str) -> None:
    """Final summary — loudly counts pages that have no usable body text."""
    failed = sum(1 for i in output if i["meta_data"].get("body_text") is None)
    empty = sum(1 for i in output if i["meta_data"].get("body_text") == "")
    present = len(output) - failed - empty
    chapters = sum(
        1 for i in output if i["meta_data"].get("document_type") == "html_publication"
    )

    print(f"\nDone. {len(output)} items → {output_path}")
    print(f"  body_text present: {present}")
    if chapters:
        print(f"  html_publication chapters expanded: {chapters}")
    if empty:
        print(f"  body_text empty (page has no body): {empty}")
    if failed:
        print(
            f"  ⚠ body_text MISSING ({failed}) — these fetches failed and are "
            f"invisible to Guidance Relevance Filter. Re-run to retry them."
        )
    print("  funnel: see sibling funnel.json (fetch_failed / body_empty / chapters_expanded)")


def run(input_path: str, output_path: str, concurrency: int, rate: float) -> None:
    all_items = json.loads(Path(input_path).read_text())
    print(f"Input items: {len(all_items)}")

    out_path = Path(output_path)
    existing: dict[str, dict] = {}
    if out_path.exists():
        try:
            for item in json.loads(out_path.read_text()):
                if item.get("meta_data", {}).get("body_text") is not None:
                    existing[item["url"]] = item
        except (json.JSONDecodeError, KeyError):
            pass
    print(f"Already fetched: {len(existing)}")

    to_fetch = _items_to_fetch(all_items, existing)
    print(f"To fetch:        {len(to_fetch)}")

    if to_fetch:
        print(f"Concurrency: {concurrency}, Rate limit: {rate} req/sec")
        fetched = asyncio.run(_fetch_all(to_fetch, concurrency, rate, set(existing)))
        for item in fetched:
            existing[item["url"]] = item

    output = _assemble_output(all_items, existing)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    funnel_path = out_path.with_name("funnel.json")
    funnel_path.write_text(json.dumps(funnel_journal(all_items, output), indent=2) + "\n")
    _report(output, output_path)


def main(
    input_path: str = typer.Argument(
        DEFAULT_SEARCH_OUTPUT, help="Path to pipeline-format input JSON (stage 1 output)"
    ),
    output_path: str = typer.Argument(
        DEFAULT_BODY_OUTPUT, help="Path to output JSON (Guidance Relevance Filter input)"
    ),
    concurrency: int = typer.Option(DEFAULT_CONCURRENCY, help="Max concurrent requests"),
    rate: float = typer.Option(DEFAULT_RATE, help="Max requests per second"),
) -> None:
    run(input_path, output_path, concurrency, rate)


if __name__ == "__main__":
    typer.run(main)
