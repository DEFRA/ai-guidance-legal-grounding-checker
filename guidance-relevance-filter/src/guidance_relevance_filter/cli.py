"""Guidance Relevance Filter CLI — narrow a guidance corpus to the pages on-topic for the category.

    guidance-relevance-filter run <input.json> <output_dir/> [--shard-name s1] [--model ...]
    guidance-relevance-filter explain <urls.csv> <run/> [-o out.csv] [--url-column url]
    guidance-relevance-filter serve

Guidance Relevance Filter runs two passes on Anthropic: a recall-maximising
classifier (pass 1) followed by a precision adjudicator (pass 2) that drops the
false positives pass 1 over-includes. Default transport is the Message Batches
API (0.5×); ``--sync`` uses the standard Messages API instead (full price, faster). Input is Guidance Discovery's output page shape: a list
of ``{url, content_id, meta_data: {title, body_text, ...}}`` objects (pages must
carry ``body_text``). Output is written to ``<output_dir>/output.json`` plus
``adjudication.json`` (the pass-1-vs-pass-2 audit trail), ``funnel.json``
    (URL list for every drop stage), and a ``MODEL.md``.

``explain`` joins a URL CSV against a finished run (``output.json`` or
``funnel.json``) and appends ``funnel_stage`` / ``funnel_reason``. ``serve``
opens the same join as a Streamlit upload UI.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from ._batch import _fmt_elapsed, log
from .adjudicate import DEFAULT_ADJUDICATOR_MODEL, adjudicate
from .checkpoint import CHECKPOINT_NAME, Checkpoint, ResumeIncompatible, fingerprint_for
from .classify import DEFAULT_MODEL, classify
from .completions import (
    DEFAULT_SYNC_CONCURRENCY,
    LLM_MODE_BATCH,
    LLM_MODE_SYNC,
    anthropic_completions,
)
from .cost import cost_usd
from .funnel import journal
from .narrowing import (
    DEFAULT_COSINE_THRESHOLD,
    DEFAULT_EMBED_MODEL,
    ROUTER_COSINE,
    ROUTER_WORDSEARCH,
    CosineRouterUnavailable,
    StemIndex,
    embed_index_path,
    embed_model_slug,
    extract_items_by_url,
    iter_json_items,
    load_or_build_embed_cache,
    load_or_build_stem_index,
    resolve_stem_index_path,
    sha256_file,
)


def _producer_fields() -> dict:
    return {
        "producer_component": "guidance-relevance-filter",
        "source_kind": "guidance",
        "component_id": "guidance-relevance-filter",
    }


load_dotenv()

app = typer.Typer(add_completion=False, help=__doc__)


@app.callback()
def _main() -> None:
    """Guidance Relevance Filter — narrow a guidance corpus to the pages on-topic for the category."""


def load_category_data(
    categories_path: Path | None = None,
    lexicon_path: Path | None = None,
    *,
    router: str = ROUTER_WORDSEARCH,
) -> tuple[list[dict], dict[str, list[str]]]:
    """Load category + lexicon data from paths or the packaged defaults.

    Wordsearch requires a lexicon (packaged, or ``--lexicon``). Cosine does not;
    ``--categories`` can be passed on its own.
    """
    data = files("guidance_relevance_filter.data")
    if categories_path is None:
        categories = json.loads((data / "categories.json").read_text())
    else:
        categories = json.loads(categories_path.read_text())

    if router == ROUTER_COSINE:
        if lexicon_path is None:
            lexicons: dict[str, list[str]] = (
                {} if categories_path is not None
                else json.loads((data / "lexicon.json").read_text())
            )
        else:
            lexicons = json.loads(lexicon_path.read_text())
        return categories, lexicons

    if lexicon_path is None:
        if categories_path is not None:
            raise typer.BadParameter(
                "--lexicon is required with --categories for wordsearch routing "
                "(or pass --router cosine)."
            )
        lexicons = json.loads((data / "lexicon.json").read_text())
    else:
        lexicons = json.loads(lexicon_path.read_text())
    return categories, lexicons


@app.command()
def run(
    input_path: Annotated[Path, typer.Argument(help="Pages JSON (list with meta_data.body_text)")],
    output_dir: Annotated[Path, typer.Argument(help="Directory to write output.json + MODEL.md")],
    model: Annotated[str, typer.Option(help="Pass-1 classifier model id")] = DEFAULT_MODEL,
    adjudicator_model: Annotated[
        str, typer.Option(help="Pass-2 adjudicator model id")
    ] = DEFAULT_ADJUDICATOR_MODEL,
    max_words: Annotated[
        int, typer.Option(help="Body-truncation budget for oversized pages")
    ] = 60000,
    shard_name: Annotated[
        str | None, typer.Option(help="Optional per-row source_shard provenance tag")
    ] = None,
    categories_path: Annotated[
        Path | None,
        typer.Option("--categories", exists=True, help="Category JSON (list); default: packaged data"),
    ] = None,
    lexicon_path: Annotated[
        Path | None,
        typer.Option("--lexicon", exists=True, help="Lexicon JSON (name -> terms); default: packaged data"),
    ] = None,
    router: Annotated[
        str,
        typer.Option("--router", help="Cheap gate: wordsearch (default) or cosine"),
    ] = ROUTER_WORDSEARCH,
    cosine_threshold: Annotated[
        float,
        typer.Option("--cosine-threshold", help="Min cosine score to route (cosine router only)"),
    ] = DEFAULT_COSINE_THRESHOLD,
    embed_model: Annotated[
        str,
        typer.Option("--embed-model", help="SentenceTransformer id (cosine router only)"),
    ] = DEFAULT_EMBED_MODEL,
    score_only: Annotated[
        bool,
        typer.Option(
            "--score-only",
            help="Run the cheap gate only; skip both Anthropic passes",
        ),
    ] = False,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help=(
                "Ignore a leftover checkpoint and submit new batches "
                "(does not cancel the old Anthropic batch)"
            ),
        ),
    ] = False,
    max_routed: Annotated[
        int | None,
        typer.Option(
            "--max-routed",
            help=(
                "Abort before the LLM if the cheap gate routes more "
                "than this many pages (writes funnel/metrics, exit 1). Ignored "
                "with --score-only and when resuming a pass-1 run."
            ),
        ),
    ] = None,
    sync: Annotated[
        bool,
        typer.Option(
            "--sync",
            help=(
                "Use the synchronous Messages API (full price, faster) instead "
                "of the Message Batches API (0.5×)."
            ),
        ),
    ] = False,
    concurrency: Annotated[
        int,
        typer.Option(
            "--concurrency",
            help="Parallel Messages API calls (--sync only; ignored for batch).",
        ),
    ] = DEFAULT_SYNC_CONCURRENCY,
    stem_index: Annotated[
        Path | None,
        typer.Option(
            "--stem-index",
            help=(
                "Directory or .sqlite file for the Porter-stem inverted index, "
                "keyed by sha256 of the input JSON. Default: <input-dir>/stem_index/. "
                "A .sqlite file from another corpus (full snapshot vs a slice) is "
                "matched by URL."
            ),
        ),
    ] = None,
    embed_index: Annotated[
        Path | None,
        typer.Option(
            "--embed-index",
            help=(
                "Directory or .pkl file for the page-embedding cache, keyed by "
                "sha256 of the input JSON + embed model. Default: "
                "<input-dir>/embed_index/"
            ),
        ),
    ] = None,
) -> None:
    if router not in {ROUTER_WORDSEARCH, ROUTER_COSINE}:
        raise typer.BadParameter("--router must be 'wordsearch' or 'cosine'")
    if concurrency < 1:
        raise typer.BadParameter("--concurrency must be >= 1")
    llm_mode = LLM_MODE_SYNC if sync else LLM_MODE_BATCH
    t0 = time.monotonic()
    categories, lexicons = load_category_data(
        categories_path, lexicon_path, router=router,
    )
    cat = categories[0]["name"]
    stem_index_db = None
    embed_cache = None
    load_bodies = None
    body_by_url: dict[str, dict] = {}
    if router == ROUTER_WORDSEARCH:
        corpus_sha = sha256_file(input_path)
        cache_path = resolve_stem_index_path(input_path, corpus_sha, stem_index)
        explicit_sqlite = (
            stem_index is not None
            and stem_index.suffix == ".sqlite"
            and cache_path.is_file()
        )
        if explicit_sqlite:
            stem_index_db = StemIndex.open(cache_path)
            if stem_index_db is None:
                log(f"Invalid stem index {cache_path}")
                raise typer.Exit(code=1)
            log(f"Stem index ({len(stem_index_db)} pages): {cache_path}")
        else:
            stem_index_db = load_or_build_stem_index(
                input_path, corpus_sha256=corpus_sha, path=cache_path, log=log,
            )
        if stem_index_db.corpus_sha256 != corpus_sha:
            urls = [str(item.get("url") or "") for item in iter_json_items(input_path)]
            items = stem_index_db.items_for_urls(urls)
        else:
            items = stem_index_db.catalog_items()
        log(
            f"Loaded {len(items)} pages from stem index; category={cat!r}; "
            f"router={router}; pass1={model}; pass2={adjudicator_model}; "
            f"llm={llm_mode}"
            + (" [score-only]" if score_only else "")
        )

        body_by_url.clear()

        def load_bodies(urls: list[str]) -> dict[str, dict]:
            found = extract_items_by_url(input_path, set(urls))
            body_by_url.update(found)
            return found
    else:
        items = json.loads(input_path.read_text())
        log(
            f"Loaded {len(items)} pages from {input_path.name}; category={cat!r}; "
            f"router={router}; pass1={model}; pass2={adjudicator_model}; llm={llm_mode}"
            + (" [score-only]" if score_only else "")
        )
        corpus_sha = sha256_file(input_path)
        if embed_index is None:
            cache_path = embed_index_path(input_path, corpus_sha, embed_model)
        elif embed_index.suffix == ".pkl":
            cache_path = embed_index
        else:
            cache_path = (
                embed_index / f"{corpus_sha}__{embed_model_slug(embed_model)}.pkl"
            )
        try:
            embed_cache = load_or_build_embed_cache(
                items,
                corpus_sha256=corpus_sha,
                embed_model=embed_model,
                path=cache_path,
                log=log,
            )
        except CosineRouterUnavailable as e:
            log(str(e))
            raise typer.Exit(code=1) from e

    started = datetime.now().isoformat(timespec="seconds")
    fp = fingerprint_for(
        input_path=input_path,
        n_pages=len(items),
        category=cat,
        model=model,
        adjudicator_model=adjudicator_model,
        max_words=max_words,
        shard_name=shard_name,
        categories=categories,
        lexicons=lexicons,
        router=router,
        cosine_threshold=cosine_threshold,
        embed_model=embed_model,
        llm_mode=llm_mode,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = Checkpoint(output_dir / CHECKPOINT_NAME)
    resumed = False
    audit: list = []
    try:
        if score_only:
            results, stats = classify(
                items, categories, lexicons,
                model=model, max_words=max_words, shard_name=shard_name,
                router=router, cosine_threshold=cosine_threshold,
                embed_model=embed_model, score_only=True,
                stem_index_db=stem_index_db, embed_cache=embed_cache,
                load_bodies=load_bodies,
            )
            adj = {
                "n_positives": 0, "n_kept": 0, "n_dropped": 0, "n_unadjudicated": 0,
                "model": adjudicator_model, "batch": None, "resumed": False,
                "usage": {"model": adjudicator_model, "batch": {"input": 0, "output": 0}},
            }
        else:
            if fresh and checkpoint.exists:
                log(
                    "`--fresh`: discarding checkpoint and starting a new LLM pass"
                    + (
                        " (the old Anthropic batch is NOT cancelled)"
                        if llm_mode == LLM_MODE_BATCH else ""
                    )
                )
                checkpoint.init(fp, started)
            elif checkpoint.exists:
                checkpoint.assert_fingerprint(fp)
                started = checkpoint.started_at
                resumed = bool(
                    checkpoint.pass1_batch_id
                    or checkpoint.pass2_batch_id
                    or checkpoint.pass1_replies
                    or checkpoint.pass2_replies
                )
                log(
                    f"Resuming from {checkpoint.path.name} "
                    f"(started {started}; pass1={checkpoint.pass1_batch_id or 'not submitted'} "
                    f"pass2={checkpoint.pass2_batch_id or 'not submitted'})"
                )
            else:
                checkpoint.init(fp, started)

            completions = anthropic_completions(
                llm_mode, concurrency=concurrency,
            )
            results, stats = classify(
                items, categories, lexicons,
                model=model, max_words=max_words, shard_name=shard_name,
                checkpoint=checkpoint, router=router,
                cosine_threshold=cosine_threshold, embed_model=embed_model,
                max_routed=max_routed, stem_index_db=stem_index_db,
                embed_cache=embed_cache, completions=completions,
                load_bodies=load_bodies,
            )
            if stats.get("capped"):
                adj = {
                    "n_positives": 0, "n_kept": 0, "n_dropped": 0, "n_unadjudicated": 0,
                    "model": adjudicator_model, "batch": None, "resumed": False,
                    "usage": {"model": adjudicator_model, "batch": {"input": 0, "output": 0}},
                }
            else:
                log(
                    f"Pass 1 done: {stats.get('n_pass1_true', 0)}/{len(results)} "
                    f"labelled {cat}=true"
                )
                results, adj, audit = adjudicate(
                    [body_by_url.get(it["url"], it) for it in items] if body_by_url else items,
                    results, categories, model=adjudicator_model, max_words=max_words,
                    checkpoint=checkpoint, completions=completions,
                )
    except ResumeIncompatible as e:
        log(str(e))
        raise typer.Exit(code=1) from e
    except CosineRouterUnavailable as e:
        log(str(e))
        raise typer.Exit(code=1) from e

    n_pass1 = stats.get("n_pass1_true", 0)

    (output_dir / "output.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n"
    )
    (output_dir / "adjudication.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    )

    # Token cost — recorded per pass (Haiku pass 1 + Sonnet pass 2). Batch mode
    # is 0.5×; sync and oversized-page rescue are full price. Written after the
    # run's real outputs so a pricing gap can never cost the results.
    bulk_batch = llm_mode == LLM_MODE_BATCH
    p1u, p2u = stats["usage"], adj["usage"]
    c1_batch = cost_usd(
        p1u["batch"]["input"], p1u["batch"]["output"], p1u["model"], batch=bulk_batch,
    )
    c1_rescue = cost_usd(p1u["rescue"]["input"], p1u["rescue"]["output"], p1u["model"], batch=False)
    c2 = cost_usd(
        p2u["batch"]["input"], p2u["batch"]["output"], p2u["model"], batch=bulk_batch,
    )

    def _sum(*vals: float | None) -> float | None:
        return None if any(v is None for v in vals) else round(sum(vals), 4)

    c1 = _sum(c1_batch, c1_rescue)
    total = _sum(c1, c2)
    p1_in = p1u["batch"]["input"] + p1u["rescue"]["input"]
    p1_out = p1u["batch"]["output"] + p1u["rescue"]["output"]
    p2_in, p2_out = p2u["batch"]["input"], p2u["batch"]["output"]
    _usd = lambda v: f"${v}" if v is not None else "not priced (unrecognised model)"  # noqa: E731

    n_true = sum(1 for r in results if r["meta_data"]["labels"].get(cat))
    n_pages = stats.get("n_pages", len(results))
    n_empty = stats.get("n_empty_body", 0)
    n_missing = stats.get("n_missing_body", 0)
    n_skipped = stats["n_skipped"]
    n_routed = stats["n_routed"]
    n_rescued = stats["n_rescued"]
    n_batch_missing = stats.get("n_batch_missing", 0)
    n_pass1_false = stats.get("n_pass1_false", max(n_routed - n_pass1, 0))
    p1_batch = stats.get("batch")
    p2_batch = adj.get("batch")

    funnel_doc = journal(
        results, cat,
        n_pages=n_pages, n_routed=n_routed, n_pass1_true=n_pass1,
    )
    (output_dir / "funnel.json").write_text(
        json.dumps(funnel_doc, indent=2, ensure_ascii=False) + "\n"
    )

    def _n(n: int, meaning: str) -> dict:
        return {"n": n, "meaning": meaning}

    by_hit = funnel_doc["counts"]["pass2_dropped_by_exclusion_hit"]
    hit_line = ", ".join(f"{tag} {n}" for tag, n in by_hit.items() if n) or "none"

    n_lexicon_miss = funnel_doc["counts"]["lexicon_miss"]
    n_cosine_miss = funnel_doc["counts"]["cosine_miss"]
    n_routing_miss = funnel_doc["counts"]["routing_miss"]
    cosine = router == ROUTER_COSINE
    miss_label = "Cosine-miss" if cosine else "Lexicon-miss"
    hit_label = "Cosine-hit" if cosine else "Lexicon-hit"
    pass_label = "batch" if bulk_batch else "sync API"
    if cosine:
        gate_meaning_hit = f"cosine ≥ threshold; sent to the pass-1 classify {pass_label}"
        gate_meaning_false = f"cosine hit, pass 1 labelled {cat}=false; never reached pass 2"
        routing_note = (
            f"routing uses cosine similarity (`{embed_model}`, threshold {cosine_threshold})"
        )
        strategy_note = (
            f"`cosine_body` — cosine ≥ {cosine_threshold} against the category embedding "
            f"query routes the page to the LLM, otherwise it is recorded `{cat}: false` "
            f"(`cosine_miss`) without an LLM call."
        )
        pass1_desc = (
            f"cosine similarity prunes the corpus to pages scoring ≥ {cosine_threshold} "
            "against the category query text, and only those reach the LLM, whose"
        )
    else:
        gate_meaning_hit = f"sent to the pass-1 classify {pass_label}"
        gate_meaning_false = f"lexicon hit, pass 1 labelled {cat}=false; never reached pass 2"
        routing_note = "routing uses an NLTK Porter-stemmed inclusion lexicon (no model)"
        strategy_note = (
            f"`wordsearch_binary` — a lexicon hit routes the page to the "
            f"LLM, otherwise it is recorded `{cat}: false` without an LLM call."
        )
        pass1_desc = (
            "word-search prunes the corpus to pages that hit the inclusion lexicon, "
            "those pages reach the LLM as windows around the hits (not the full body), "
            "and the LLM is a homonym gate whose"
        )
    score_only_note = (
        " **Score-only:** the cheap gate ran; both Anthropic passes were skipped."
        if score_only else ""
    )
    capped = bool(stats.get("capped"))
    capped_note = (
        f" **Capped:** {n_routed} pages routed exceeds `--max-routed {max_routed}`; "
        "neither Anthropic pass ran."
        if capped else ""
    )

    elapsed_seconds = int(time.monotonic() - t0)
    finished_at = datetime.now().isoformat(timespec="seconds")

    (output_dir / "metrics.json").write_text(json.dumps({
        **_producer_fields(),
        "category": cat,
        "router": router,
        "score_only": score_only,
        "capped": capped,
        "max_routed": max_routed,
        "input": {"file": input_path.name, "n_pages": n_pages},
        "funnel": {
            "input_pages": _n(n_pages, "pages in the input JSON"),
            "missing_body": _n(
                n_missing, f"body_text was null (upstream fetch failed) → {cat}=false; LLM not called"
            ),
            "empty_body": _n(n_empty, f"page has no body → {cat}=false; LLM not called"),
            "lexicon_miss": _n(
                n_lexicon_miss, f"no inclusion-lexicon hit → {cat}=false; LLM not called"
            ),
            "cosine_miss": _n(
                n_cosine_miss,
                f"cosine < {cosine_threshold} vs category query → {cat}=false; LLM not called",
            ),
            "routing_miss": _n(
                n_routing_miss, "cheap-gate miss (lexicon_miss + cosine_miss)"
            ),
            "lexicon_hit": _n(n_routed, gate_meaning_hit),
            "pass1_batch_missing": _n(
                n_batch_missing,
                "routed pages with no succeeded LLM reply (rescued one-by-one)",
            ),
            "pass1_rescued": _n(
                n_rescued, "dropped or unparseable pages retried on the Messages API",
            ),
            "pass1_false": _n(n_pass1_false, gate_meaning_false),
            "pass1_true": _n(n_pass1, f"pass 1 labelled {cat}=true; these go to pass 2"),
            "pass2_positives": _n(
                adj["n_positives"], f"pass-1 trues submitted to the adjudicate {pass_label}",
            ),
            "pass2_kept": _n(adj["n_kept"], f"pass 2 confirmed {cat}=true"),
            "pass2_dropped": _n(adj["n_dropped"], f"pass 2 turned {cat} true→false"),
            "pass2_dropped_by_exclusion_hit": by_hit,
            "pass2_unadjudicated": _n(
                adj["n_unadjudicated"], "verdict unparseable; kept as pass 1 labelled them"
            ),
            "final_true": _n(n_true, f"final {cat}=true after both passes"),
        },
        "pass1": {
            "model": p1u["model"],
            "n_pages": n_pages,
            "n_empty_body": n_empty,
            "n_missing_body": n_missing,
            "n_skipped": n_skipped,
            "n_routed": n_routed,
            "n_batch_missing": n_batch_missing,
            "n_rescued": n_rescued,
            "n_true": n_pass1,
            "n_false": n_pass1_false,
            "batch": p1u["batch"],
            "batch_meta": p1_batch,
            "rescue": p1u["rescue"],
            "cost_usd": c1,
        },
        "pass2": {
            "model": p2u["model"],
            "n_positives": adj["n_positives"],
            "n_kept": adj["n_kept"],
            "n_dropped": adj["n_dropped"],
            "n_unadjudicated": adj["n_unadjudicated"],
            "n_true": n_true,
            "batch": p2u["batch"],
            "batch_meta": p2_batch,
            "cost_usd": c2,
        },
        "tokens": {"input": p1_in + p2_in, "output": p1_out + p2_out},
        "cost_usd": total,
        "started_at": started,
        "finished_at": finished_at,
        "elapsed_seconds": elapsed_seconds,
        "resumed": resumed,
        "llm_mode": llm_mode,
    }, indent=2) + "\n")

    base_rate = (n_true / len(results) * 100) if results else 0.0

    def _batch_line(meta: dict | None, empty: str) -> str:
        if not meta:
            return empty
        counts = meta.get("request_counts") or {}
        errored = counts.get("errored", 0)
        ident = meta.get("id")
        head = f"`{ident}`" if ident else "sync"
        extra = ""
        if meta.get("concurrency"):
            extra = f", concurrency {meta['concurrency']}"
        return (
            f"{head} — submitted {meta['submitted']}, collected {meta['collected']}"
            f"{f', {errored} errored' if errored else ''}"
            f" in {meta.get('elapsed_seconds', 0)}s{extra}"
        )

    transport = (
        "Anthropic batch API"
        if bulk_batch else "Anthropic Messages API (sync)"
    )
    cost_note = (
        "Both passes bill on the Anthropic batch API at 0.5×; an oversized-page "
        "rescue (if any) is the one full-price call."
        if bulk_batch else
        "Both passes bill on the Anthropic Messages API at full (1×) on-demand rates."
    )
    cost_tag = "batch-discounted" if bulk_batch else "on-demand"

    model_card = f"""# guidance-relevance-filter — {output_dir.name}

## Description

Guidance Relevance Filter run from the standalone `guidance-relevance-filter` package: two passes on the {transport}.
**Pass 1** (`{model}`) is a homonym gate — {pass1_desc}
prompt uses the category description with the Exclusion Criteria removed and
labels TRUE if any hit is in the intended sense (a single table cell counts).
Incidental-but-right-sense mentions are left for pass 2. **Pass 2**
(`{adjudicator_model}`) re-reads each page pass 1 labelled `{cat}: true` and, with
the Exclusion Criteria re-introduced, drops the false positives (homonyms,
wrong-domain mentions, incidental-only references). Pass 2 can only turn a TRUE into a FALSE, so it costs pass 1
no recall.{score_only_note}{capped_note}

## Started

{started}{" (resumed from checkpoint)" if resumed else ""}
Elapsed (this process): {_fmt_elapsed(elapsed_seconds)}

## Provenance

- **Input:** {input_path.name}{f" (shard `{shard_name}`)" if shard_name else ""}
- **Category:** `{cat}`{f" (from `{categories_path.name}`)" if categories_path else " (packaged defaults)"}
- **Router:** `{router}`
- **Models used:** pass 1 `{model}`, pass 2 `{adjudicator_model}`, both via the
  {transport}; {routing_note}.
- **LLM mode:** `{llm_mode}`

## Notes on settings

- **Pass 1 strategy:** {strategy_note}
- **Pass 2:** decisive keep/drop over the pass-1 positives; an unparseable verdict
  leaves the page as pass 1 labelled it (kept), counted as `unadjudicated`.
- **Pass 1 body:** wordsearch sends windows around lexicon hits so a capital-item
  table in a long manual is visible; cosine still sends the full body. Rescue
  truncates that payload if it still exceeds {max_words} words; the trim is
  stamped into the reason, never silent.
- **Output shape:** `meta_data.labels.{cat}` (final, post-pass-2 bool), plus
  `scores`, `reasons`, `meta_data.funnel` (per-page drop stage + both passes'
  reasons), and `selection_*_body` provenance. `body_text` is dropped.
  The pass-1-vs-pass-2 trail is in `adjudication.json`; every drop stage's
  URL list (missing-body, empty-body, lexicon-miss, cosine-miss, pass-1 false, pass-2
  drop/keep) is in `funnel.json`.

## Funnel

- **Input:** {n_pages} pages (`{input_path.name}`)
- **Missing-body:** {n_missing} → `{cat}: false`, fetch failed upstream, LLM not called
- **Empty-body:** {n_empty} → `{cat}: false`, page has no body, LLM not called
- **{miss_label}:** {n_skipped} → `{cat}: false`, LLM not called
- **{hit_label}:** {n_routed} → pass-1 classify {pass_label} {_batch_line(p1_batch, "(no LLM — nothing routed)")}
- **Pass 1 `{cat}: false`:** {n_pass1_false} (gate hit, Haiku said no)
- **Pass 1 `{cat}: true`:** {n_pass1} (rescued {n_rescued}; {n_batch_missing} missing from the LLM pass)
- **Pass 2:** {adj['n_positives']} pass-1 positives → adjudicate {pass_label} {_batch_line(p2_batch, "(no LLM — no pass-1 positives)")} — kept {adj['n_kept']}, dropped {adj['n_dropped']}, unadjudicated {adj['n_unadjudicated']}
- **Pass 2 drops by exclusion:** {hit_line}
- **Final `{cat}: true`:** {n_true} ({base_rate:.2f}% of {n_pages} input)

Machine-readable copy of this funnel (each count with a `meaning`) is in `metrics.json`.
Per-page `meta_data.funnel.stage` on every row of `output.json`. URL lists for
every stage in `funnel.json`.

```
jq '[.[] | .meta_data.funnel.stage] | group_by(.) | map([.[0], length])' output.json
jq '.counts' funnel.json
jq --arg u "$URL" '.. | objects | select(.url == $u)' funnel.json
jq '[.pass2_drop[] | .exclusion_hit] | group_by(.) | map([.[0], length])' funnel.json
```

## Cost

{cost_note} Full machine-readable breakdown in `metrics.json`.

- **Pass 1** (`{model}`): {p1_in:,} in / {p1_out:,} out → {_usd(c1)}
- **Pass 2** (`{adjudicator_model}`): {p2_in:,} in / {p2_out:,} out → {_usd(c2)}
- **Total: {_usd(total)}** ({cost_tag})
"""
    (output_dir / "MODEL.md").write_text(model_card)
    checkpoint.clear()

    typer.echo(
        f"Wrote {output_dir}\n"
        f"{len(results)} pages; pass1 {cat}-true={n_pass1} "
        f"(routed={stats['n_routed']} skipped={stats['n_skipped']} "
        f"missing-body={stats.get('n_missing_body', 0)} "
        f"empty-body={stats.get('n_empty_body', 0)} rescued={stats['n_rescued']}); "
        f"pass2 kept={adj['n_kept']} dropped={adj['n_dropped']} "
        f"unadjudicated={adj['n_unadjudicated']}; final {cat}-true={n_true} ({base_rate:.2f}%); "
        f"cost={_usd(total)}; elapsed={_fmt_elapsed(elapsed_seconds)}"
        + (f"; CAPPED routed={n_routed} max={max_routed}" if capped else "")
    )
    if capped:
        raise typer.Exit(code=1)


@app.command()
def explain(
    csv_path: Annotated[Path, typer.Argument(help="CSV with a URL column")],
    run: Annotated[
        Path,
        typer.Argument(help="GRF run directory, output.json, or funnel.json"),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Annotated CSV path (default: <csv-stem>-funnel.csv)",
        ),
    ] = None,
    url_column: Annotated[
        str | None,
        typer.Option(
            "--url-column",
            help="URL column name (default: url, then Original URL, then clened-urls)",
        ),
    ] = None,
) -> None:
    """Join a URL CSV against a finished run and append funnel_stage / funnel_reason."""
    from .annotate import AnnotateError, explain_csv, format_histogram

    try:
        dest, counts = explain_csv(csv_path, run, output, url_column)
    except AnnotateError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Wrote {dest}", err=True)
    hist = format_histogram(counts)
    if hist:
        typer.echo(hist, err=True)


@app.command()
def serve() -> None:
    """Launch the Streamlit upload UI for explain."""
    import subprocess
    import sys

    try:
        import streamlit  # noqa: F401
    except ImportError:
        typer.echo("Streamlit is not installed. Run: uv sync --group web", err=True)
        raise typer.Exit(code=1) from None
    viewer = Path(__file__).resolve().parent / "viewer.py"
    raise typer.Exit(
        subprocess.call([sys.executable, "-m", "streamlit", "run", str(viewer)])
    )


if __name__ == "__main__":
    app()
