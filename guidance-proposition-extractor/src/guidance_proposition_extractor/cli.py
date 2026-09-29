"""Guidance Proposition Extractor CLI.

``guidance-proposition-extractor run <pages.json> <out_dir>`` extracts propositions for every page
and writes the validator-compatible run artefacts to ``out_dir``. Extraction
goes through the Message Batches API by default (50% cost, async); ``--sync``
falls back to the page-by-page synchronous path.

Resumable: if ``out_dir/output.json`` already has entries, those URLs are
skipped on the next invocation.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import typer
from dotenv import load_dotenv

from .cost import add_usage, cost_usd, new_usage
from .extract import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    ExtractionError,
    build_request_params,
    extract_with_usage,
    parse_message,
)
from .fetch import fetch
from .funnel import prepare_journal, run_journal
from .prompt import PROMPT
from .provenance import attach_provenance


def _producer_fields() -> dict:
    return {
        "producer_component": "guidance-proposition-extractor",
        "source_kind": "guidance",
        "component_id": "guidance-proposition-extractor",
    }


load_dotenv()

app = typer.Typer(help="Guidance Proposition Extractor — atomic proposition extraction from GOV.UK guidance.")

CANDIDATE_ID = "susan-default"
CANDIDATE_NAME = "guidance-proposition-extractor production (sonnet-4-6 + tightened + metadata)"


def _load_pages(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    if isinstance(raw, dict) and "pages" in raw:
        return raw["pages"]
    if isinstance(raw, list):
        return raw
    raise typer.BadParameter(
        f"{path} is not a recognised pages.json shape "
        "(expected {'pages': [...]} or a flat list)"
    )


def _relevance_filter_to_pages(rows: list[dict], category: str) -> tuple[list[dict], list[dict]]:
    """Split an upstream filter run into on-topic pages vs dropped-not-on-topic records.

    A row is kept iff ``meta_data.labels[category]`` is exactly ``True``.
    Dropped records keep the upstream funnel stage and both-pass reasons so a
    miss can be attributed without re-joining ``output.json``.
    """
    pages: list[dict] = []
    dropped: list[dict] = []
    for r in rows:
        meta = r.get("meta_data") or {}
        url = r.get("url") or ""
        title = meta.get("title") or ""
        content_id = r.get("content_id") or ""
        if (meta.get("labels") or {}).get(category) is True:
            pages.append({"url": url, "title": title, "content_id": content_id})
            continue
        funnel = meta.get("funnel") or {}
        dropped.append({
            "url": url,
            "title": title,
            "content_id": content_id,
            "label": (meta.get("labels") or {}).get(category),
            "stage": funnel.get("stage"),
            "reason": (meta.get("reasons") or {}).get(category, ""),
            "pass1_reason": funnel.get("pass1_reason"),
            "pass2_reason": funnel.get("pass2_reason"),
            "exclusion_hit": funnel.get("exclusion_hit"),
        })
    return pages, dropped


def _existing(out_path: Path) -> dict[str, dict]:
    if not out_path.exists():
        return {}
    try:
        return {row["url"]: row for row in json.loads(out_path.read_text())}
    except (json.JSONDecodeError, KeyError):
        return {}


def _load_excluded(out_path: Path) -> list[dict]:
    if not out_path.exists():
        return []
    try:
        return json.loads(out_path.read_text())
    except Exception:
        return []


def _excluded_entry(url: str, title: str, reason: str) -> dict:
    category = "too_big" if "truncat" in reason.lower() else "error"
    return {"url": url, "title": title, "category": category, "reason": reason}


def _write_output(out_path: Path, rows: dict[str, dict], page_order: list[str]) -> None:
    ordered = [rows[u] for u in page_order if u in rows]
    out_path.write_text(json.dumps(ordered, indent=2))


def _prior_usage(metrics_path: Path) -> dict[str, int]:
    """Token totals already recorded for this run, so a resume adds to them
    rather than overwriting — a multi-pass run reports its full spend."""
    usage = new_usage()
    if not metrics_path.exists():
        return usage
    try:
        prior = json.loads(metrics_path.read_text()).get("tokens", {})
    except (json.JSONDecodeError, OSError):
        return usage
    for k in usage:
        usage[k] = int(prior.get(k, 0))
    return usage


def _prompt_hash() -> str:
    return hashlib.sha256(PROMPT.encode()).hexdigest()[:12]


def _write_model_card(
    out_dir: Path, *, model: str, started_at: str, n_pages: int, n_propositions: int,
    n_excluded: int = 0, mode: str = "batch", metrics: dict | None = None,
) -> None:
    body = f"""# guidance-proposition-extractor — {out_dir.name}

## Description

A Guidance Proposition Extractor run. Reads the body of each gov.uk page in the input and decomposes it
into atomic propositions carrying contextual metadata (subject_area,
instrument, actor).

## Provenance

- **Models used:** Anthropic `{model}`, hosted on the Anthropic API.
- **Execution:** {mode} ({"Message Batches API, 50% cost" if mode == "batch" else "synchronous Messages API"})
- **Prompt hash:** `{_prompt_hash()}`
- **Candidate:** `{CANDIDATE_ID}` — {CANDIDATE_NAME}

## Started

{started_at}

## Output shape

A list keyed by page URL, each with top-level `content_id` (when known) and
`meta_data.propositions[]`. Each proposition has derived `proposition_text`,
citation `source_paragraphs[]`, post-hoc `section_locators[]`, plus
`subject_area`, `instrument`, `actor`, `regulatory_kind`, `derives_from`.
Scorable by the property-checks and pairwise-judgement validators at
`draft-pipelines/guidance-proposition-extractor/validation/`.

## Headline

- **Pages:** {n_pages}
- **Propositions:** {n_propositions}
- **Excluded (too big / errored):** {n_excluded} — see `excluded.json` and `funnel.json`
"""
    if metrics is not None:
        t = metrics["tokens"]
        discount = " (batch-discounted)" if metrics["mode"] == "batch" else ""
        body += f"""
## Cost

Cumulative across every invocation that wrote to this run (resumes included);
full machine-readable breakdown in `metrics.json`.

- **Tokens:** {t['input']:,} in / {t['output']:,} out
- **Cost:** **${metrics['cost_usd']}**{discount}
"""
    (out_dir / "MODEL.md").write_text(body)


def _row(url: str, page_meta: dict, fetched_title: str, propositions: list) -> dict:
    return {
        "url": url,
        "content_id": page_meta.get("content_id") or "",
        "meta_data": {
            "title": page_meta.get("title") or fetched_title,
            "candidate_id": CANDIDATE_ID,
            "candidate_name": CANDIDATE_NAME,
            "propositions": [p.model_dump() for p in propositions],
        },
    }


def _run_sync(todo, rows, out_json, page_order, *, model, max_tokens, timeout, cache, usage):
    """Extract page-by-page on the synchronous Messages API."""
    failures: list[tuple[str, str]] = []
    verbatim_misses = 0
    for i, page_meta in enumerate(todo, 1):
        url = page_meta["url"]
        print(f"[{i}/{len(todo)}] fetching + extracting: {url}")
        try:
            fetched = fetch(url, cache_dir=cache)
            propositions, message = extract_with_usage(
                fetched, model=model, max_tokens=max_tokens, timeout=timeout
            )
            propositions, misses = attach_provenance(propositions, fetched)
            verbatim_misses += misses
            add_usage(usage, message)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            print(f"[FAILED] {url} -- {msg}", file=sys.stderr)
            failures.append((url, msg))
            continue
        rows[url] = _row(url, page_meta, fetched.title, propositions)
        _write_output(out_json, rows, page_order)
    return failures, verbatim_misses


def _run_batch(todo, rows, out_json, page_order, *, model, max_tokens, cache, poll_seconds, usage):
    """Extract every page via the Message Batches API (50% cost, async, and
    no per-page client timeout — so large pages can't be billed-then-dropped)."""
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    failures: list[tuple[str, str]] = []
    verbatim_misses = 0
    if not todo:
        return failures, verbatim_misses

    client = anthropic.Anthropic()
    by_id: dict[str, tuple] = {}
    requests: list[Request] = []
    print(f"fetching pages + building {len(todo)} batch requests…")
    for i, page_meta in enumerate(todo):
        url = page_meta["url"]
        try:
            fetched = fetch(url, cache_dir=cache)
        except Exception as e:
            print(f"[FAILED fetch] {url} -- {type(e).__name__}: {e}", file=sys.stderr)
            failures.append((url, f"{type(e).__name__}: {e}"))
            continue
        cid = f"page-{i}"
        by_id[cid] = (url, page_meta, fetched)
        requests.append(
            Request(
                custom_id=cid,
                params=MessageCreateParamsNonStreaming(
                    **build_request_params(fetched, model=model, max_tokens=max_tokens)
                ),
            )
        )

    if not requests:
        return failures, verbatim_misses

    batch = client.messages.batches.create(requests=requests)
    print(f"submitted batch {batch.id} ({len(requests)} requests) — polling every {poll_seconds}s")
    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        c = b.request_counts
        print(
            f"  {b.processing_status}: processing={c.processing} "
            f"succeeded={c.succeeded} errored={c.errored}",
            flush=True,
        )
        time.sleep(poll_seconds)

    for result in client.messages.batches.results(batch.id):
        url, page_meta, fetched = by_id[result.custom_id]
        if result.result.type != "succeeded":
            failures.append((url, f"batch result: {result.result.type}"))
            continue
        # A succeeded message is billed even if its propositions fail to parse.
        add_usage(usage, result.result.message)
        try:
            propositions = parse_message(result.result.message)
        except ExtractionError as e:
            failures.append((url, f"ExtractionError: {e}"))
            continue
        propositions, misses = attach_provenance(propositions, fetched)
        verbatim_misses += misses
        rows[url] = _row(url, page_meta, fetched.title, propositions)

    _write_output(out_json, rows, page_order)
    return failures, verbatim_misses


@app.command()
def run(
    pages_path: Path = typer.Argument(..., exists=True, help="JSON of pages to extract"),
    out_dir: Path = typer.Argument(..., help="Output directory for output.json and MODEL.md"),
    model: str = typer.Option(DEFAULT_MODEL, help="Anthropic model name"),
    max_tokens: int = typer.Option(DEFAULT_MAX_TOKENS, help="Max output tokens"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT_SECONDS, help="Per-page timeout seconds (--sync only)"),
    cache: Path | None = typer.Option(None, help="Optional disk cache dir for fetched pages"),
    sync: bool = typer.Option(
        False, "--sync", help="Extract page-by-page on the synchronous API instead of the Batch API."
    ),
    poll_seconds: int = typer.Option(30, help="Batch poll interval in seconds (batch mode)."),
    retry_excluded: bool = typer.Option(
        False, "--retry-excluded",
        help="Re-attempt pages previously written to excluded.json (e.g. at a higher --max-tokens).",
    ),
) -> None:
    """Extract propositions for every page; write a validator-compatible run.

    Defaults to the Message Batches API — 50% cheaper and async. Pass
    ``--sync`` to extract page-by-page on the synchronous API instead.
    Resumable either way: URLs already in ``out_dir/output.json`` are skipped.
    """
    pages = _load_pages(pages_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "output.json"
    rows = _existing(out_json)
    page_order = [p["url"] for p in pages]
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    excluded_prev = _load_excluded(out_dir / "excluded.json")
    excluded_prev_urls = {e["url"] for e in excluded_prev}
    skip = set(rows) if retry_excluded else set(rows) | excluded_prev_urls
    todo = [p for p in pages if p["url"] not in skip]
    mode = "sync" if sync else "batch"
    print(
        f"{len(pages)} pages | {len(rows)} extracted | "
        f"{0 if retry_excluded else len(excluded_prev_urls)} previously excluded | "
        f"{len(todo)} to process ({mode} mode)"
    )

    metrics_path = out_dir / "metrics.json"
    usage = _prior_usage(metrics_path)
    if sync:
        failures, verbatim_misses = _run_sync(
            todo, rows, out_json, page_order,
            model=model, max_tokens=max_tokens, timeout=timeout, cache=cache, usage=usage,
        )
    else:
        failures, verbatim_misses = _run_batch(
            todo, rows, out_json, page_order,
            model=model, max_tokens=max_tokens, cache=cache, poll_seconds=poll_seconds, usage=usage,
        )

    _write_output(out_json, rows, page_order)

    # Everything not extracted — too big to process (truncated at the token cap)
    # or errored — is recorded explicitly, never silently dropped. Prior
    # exclusions are carried forward unless they were extracted this pass.
    title_by_url = {p["url"]: p.get("title", "") for p in pages}
    new_excluded = [_excluded_entry(url, title_by_url.get(url, ""), msg) for url, msg in failures]
    new_urls = {e["url"] for e in new_excluded}
    excluded = [
        e for e in excluded_prev if e["url"] not in rows and e["url"] not in new_urls
    ] + new_excluded
    (out_dir / "excluded.json").write_text(json.dumps(excluded, indent=2))

    total_props = sum(
        len(r["meta_data"].get("propositions", [])) for r in rows.values()
    )

    metrics = {
        "model": model,
        "mode": mode,
        "pages": len(rows),
        "propositions": total_props,
        "excluded": len(excluded),
        "source_paragraph_verbatim_misses": verbatim_misses,
        "tokens": dict(usage),
        "cost_usd": round(cost_usd(usage, model, batch=not sync), 4),
        "updated_at": started_at,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2))

    (out_dir / "funnel.json").write_text(
        json.dumps(run_journal(pages=pages, extracted=rows, excluded=excluded), indent=2)
        + "\n"
    )

    _write_model_card(
        out_dir,
        model=model,
        started_at=started_at,
        n_pages=len(rows),
        n_propositions=total_props,
        n_excluded=len(excluded),
        mode=mode,
        metrics=metrics,
    )

    print()
    print(
        f"Done. {len(rows)} pages, {total_props} propositions, {len(excluded)} excluded "
        f"| ${metrics['cost_usd']} -> {out_json}"
    )
    if excluded:
        print(f"  {len(excluded)} pages not processed -> {out_dir / 'excluded.json'}")


@app.command()
def prepare(
    source: Path = typer.Argument(..., exists=True, help="Upstream run output, e.g. guidance-relevance-filter's output.json"),
    pages_out: Path = typer.Argument(..., help="Where to write Guidance Proposition Extractor's pages.json input"),
    category: str = typer.Option("slurry", help="guidance-relevance-filter category label that must be true to keep a page"),
) -> None:
    """Map an upstream guidance-relevance-filter run's output into Guidance Proposition Extractor's ``pages.json`` input.

    Keeps only pages guidance-relevance-filter labelled on-topic for ``category`` and projects them
    to ``{url, title, content_id}``. The source path is a parameter (so the input
    can move or change); this mapping is committed so its shape is visible over time.
    """
    raw = json.loads(source.read_text())
    rows = raw if isinstance(raw, list) else (raw.get("pages") or raw.get("records") or [])
    pages, dropped = _relevance_filter_to_pages(rows, category)
    pages_out.parent.mkdir(parents=True, exist_ok=True)
    pages_out.write_text(json.dumps({**_producer_fields(), "category": "guidance-pages", "pages": pages}, indent=2))
    funnel_path = pages_out.with_name("funnel.json")
    funnel_path.write_text(
        json.dumps(
            prepare_journal(category=category, source_n=len(rows), kept=pages, dropped=dropped),
            indent=2,
        )
        + "\n"
    )
    print(
        f"{len(rows)} source rows -> {len(pages)} {category!r} pages "
        f"({len(dropped)} dropped) -> {pages_out} + {funnel_path.name}"
    )


if __name__ == "__main__":
    app()
