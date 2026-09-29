r"""Guidance Relevance Filter pass 1: cheap-gate routing + Claude Haiku.

    title + body --cheap gate?--> no  --> recorded FALSE, no LLM call
                            \-> yes --> Claude Haiku 4.5 (batch or sync API)

The cheap gate is ``wordsearch`` (inclusion lexicon, default) or ``cosine``
(nomic embeddings of title + body vs the category query text). Pass 1 is a
homonym gate: TRUE if any lexicon hit is in the intended sense of the category
(a single table cell counts); FALSE only for a different sense of the word.
Incidental-but-right-sense mentions are pass 2's job. The prompt is the
category description with the Exclusion Criteria section removed. Wordsearch
pages are sent as windows around lexicon hits, not the full body.

No silent fallbacks anywhere:
- A page the gate routes away is recorded FALSE with an explicit reason.
- A page the bulk pass drops is rescued via a one-off Messages API call
  with its body truncated, and the truncation is stamped into the reason.
- A page that cannot be classified even after rescue is collected and raised
  loudly — never quietly defaulted to FALSE.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence

from ._batch import log
from .checkpoint import Checkpoint
from .completions import CompletionRequest, Completions
from .funnel import (
    COSINE_MISS,
    EMPTY_BODY,
    LEXICON_MISS,
    MISSING_BODY,
    PASS1_FALSE,
    PASS1_TRUE,
    stamp,
)
from .narrowing import (
    DEFAULT_COSINE_THRESHOLD,
    DEFAULT_EMBED_MODEL,
    ROUTER_COSINE,
    ROUTER_WORDSEARCH,
    CompiledLexicon,
    EmbedCache,
    StemIndex,
    _encode_documents,
    compile_lexicon,
    hit_windows,
    match_compiled,
    searchable_text,
    select_by_cosine,
    stem_index,
)

DEFAULT_MODEL = os.getenv("LLM_MODEL_ANTHROPIC", "claude-haiku-4-5-20251001")
MAX_TOKENS = 512
_PROGRESS_EVERY = 100


def _emit_progress(
    on_progress: Callable[[str, int, int], None] | None,
    phase: str,
    done: int,
    total: int,
) -> None:
    if on_progress is not None:
        on_progress(phase, done, total)


class ClassificationIncomplete(RuntimeError):
    """Raised when one or more routed pages could not be honestly classified."""


def build_prompt(
    title: str,
    body_text: str,
    categories: list[dict],
    *,
    lexicon_hits: list[str] | None = None,
    excerpts: bool = False,
) -> str:
    category_list = "\n".join(f"- {c['name']}: {c['description']}" for c in categories)
    title_line = f"Page title: {title}\n" if title else ""
    hits = ", ".join(lexicon_hits) if lexicon_hits else ""
    hits_line = f"Lexicon hits on this page: {hits}\n" if hits else ""
    body_label = (
        "Page excerpts (windows around lexicon hits; the rest of the page is omitted):\n"
        if excerpts
        else "Page content:\n"
    )
    return (
        "You are a homonym gate for a DEFRA guidance filter.\n\n"
        "A cheap word-search already found an inclusion-lexicon hit on this page. "
        "Your only job is to decide whether that hit is in the intended sense of "
        "the category — not whether the page is 'about' the topic, and not how "
        "central or detailed the mention is. Pass 2 drops incidental mentions.\n\n"
        "TRUE — any hit refers to the category as defined below. A single table "
        "cell, bullet, capital-item code, or aside in a long manual is enough. "
        "Do not require handling, storage, processing, or any other substance bar.\n\n"
        "FALSE — only when every hit is a different sense of the word (a homonym) "
        "or a clearly different domain than the category defines "
        "(e.g. bentonite/construction slurry vs animal slurry; ornamental aquarium "
        "fish vs fishery products).\n\n"
        "The category text below defines WHAT COUNTS as this category (the intended "
        "sense). Ignore any language in it about how much of the page must be on-"
        "topic or that a keyword must appear in a particular processing context.\n\n"
        f"Categories:\n{category_list}\n\n"
        f"{hits_line}{title_line}\n"
        f"{body_label}{body_text}\n\n"
        "Scoring guidance (amount, not the boolean):\n"
        "- 0.1–0.3: mentioned once or in passing — still TRUE if the sense is right\n"
        "- 0.4–0.6: discussed to a moderate extent\n"
        "- 0.7–1.0: a major focus of the page\n"
        "- 0.0: every hit is the wrong sense — the only case for FALSE\n\n"
        "Return ONLY a valid JSON object.\n\n"
        "For each category return:\n"
        "{\n"
        '  "<category>": true|false,\n'
        '  "<category>_score": float,\n'
        '  "<category>_reason": "1-2 sentence explanation"\n'
        "}\n\n"
        'Set "<category>" to true if any hit is in the intended sense, even briefly.\n'
        'Set "<category>" to false only for homonym / wrong-sense hits.'
    )


TITLE_HIT_ONLY_BODY = (
    "(No inclusion-lexicon hit in the body; the hit was in the title. "
    "Classify from the title.)"
)


def _lexicon_hit_terms(sel_meta: dict) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for terms in (sel_meta.get("hits_per_cat") or {}).values():
        for term in terms:
            if term not in seen:
                seen.add(term)
                hits.append(term)
    return hits


def _pass1_body(
    body: str,
    compiled: CompiledLexicon,
    sel_meta: dict,
) -> tuple[str, dict]:
    """Wordsearch pages → hit windows; cosine (empty compiled) → full body."""
    if not compiled:
        return body, {"pass1_input": "full_body"}
    excerpt, meta = hit_windows(body, compiled, hits_per_cat=sel_meta.get("hits_per_cat"))
    if not excerpt:
        return TITLE_HIT_ONLY_BODY, {"pass1_input": "hit_windows", "title_hit_only": True, **meta}
    return excerpt, {"pass1_input": "hit_windows", **meta}


def _repair_truncated_json(text: str) -> str:
    """Close a JSON object cut off mid-string or mid-value."""
    if not text.startswith("{"):
        return text
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and in_string:
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        i += 1
    if in_string:
        text += '"'
    if not text.rstrip().endswith("}"):
        text = text.rstrip().rstrip(",") + "}"
    return text


def parse_response(
    text: str, categories: list[dict]
) -> tuple[dict[str, bool], dict[str, float], dict[str, str]] | None:
    """Parse a model reply into (labels, scores, reasons), or None if unparseable."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        try:
            parsed = json.loads(_repair_truncated_json(text))
        except (json.JSONDecodeError, ValueError):
            return None
    labels = {c["name"]: bool(parsed.get(c["name"], False)) for c in categories}
    scores = {
        c["name"]: float(parsed.get(f"{c['name']}_score", 1.0 if labels[c["name"]] else 0.0))
        for c in categories
    }
    reasons = {
        c["name"]: parsed.get(f"{c['name']}_reason", parsed.get("reason", ""))
        for c in categories
    }
    return labels, scores, reasons


def _meta(
    item: dict,
    labels: dict[str, bool],
    scores: dict[str, float],
    reasons: dict[str, str],
    sel_meta: dict,
    selected_names: list[str],
    shard_name: str | None,
    *,
    funnel_stage: str,
    funnel_fields: dict | None = None,
) -> dict:
    """Build the output meta_data for a page (drops body_text)."""
    base = {k: v for k, v in item["meta_data"].items() if k != "body_text"}
    meta = {
        **base,
        "labels": labels,
        "scores": scores,
        "reasons": reasons,
        "selection_strategy_body": sel_meta.get("strategy", "wordsearch_binary"),
        "selected_categories_body": selected_names,
        "selection_meta_body": sel_meta,
    }
    stamp(meta, funnel_stage, **(funnel_fields or {}))
    if shard_name:
        meta["source_shard"] = shard_name
    return {**item, "meta_data": meta}


def _body_text(item: dict) -> str:
    """Normalize body_text; treat missing/None as empty."""
    return (item.get("meta_data") or {}).get("body_text") or ""


def _title(item: dict) -> str:
    return ((item.get("meta_data") or {}).get("title") or "").strip()


def _searchable_text(item: dict, body: str) -> str:
    """Title then body — the cheap gate searches both."""
    return searchable_text(_title(item), body)


def _page_embeddings_from_cache(
    scorable: list[tuple[dict, str]],
    bodies: list[str],
    embed_cache: EmbedCache | None,
    *,
    embed_model: str,
    embed_device: str | None,
) -> list[list[float]] | None:
    """Cached document vectors aligned with ``bodies``, or None to encode fresh.

    Missing URLs are encoded and ``put`` on the in-memory cache (not flushed).
    """
    if embed_cache is None:
        return None
    page_embeddings: list[list[float] | None] = []
    missing_at: list[int] = []
    missing_bodies: list[str] = []
    for i, (it, _body) in enumerate(scorable):
        hit = embed_cache.get(it["url"])
        if hit is None:
            missing_at.append(i)
            missing_bodies.append(bodies[i])
            page_embeddings.append(None)
        else:
            page_embeddings.append(hit)
    if missing_bodies:
        fresh = _encode_documents(
            missing_bodies, model=embed_model, device=embed_device,
        )
        for j, vec in zip(missing_at, fresh, strict=True):
            page_embeddings[j] = vec
            embed_cache.put(scorable[j][0]["url"], vec)
    filled: list[list[float]] = []
    for vec in page_embeddings:
        if vec is None:
            raise RuntimeError("embed cache fill missed a page")
        filled.append(vec)
    return filled


def _exclude_reason(sel_meta: dict, cat: str) -> str:
    strategy = sel_meta.get("strategy", "wordsearch_binary")
    if strategy == "cosine_body":
        score = (sel_meta.get("scores") or {}).get(cat, 0.0)
        threshold = sel_meta.get("threshold", DEFAULT_COSINE_THRESHOLD)
        return f"excluded by cosine_body (score {score} < {threshold}; LLM not called)"
    return "excluded by wordsearch_binary (no cats selected; LLM not called)"


def _excluded_meta(
    item: dict,
    categories: list[dict],
    sel_meta: dict,
    shard_name: str | None,
    *,
    funnel_stage: str,
) -> dict:
    names = [c["name"] for c in categories]
    cosine_scores = sel_meta.get("scores") or {}
    scores = {n: float(cosine_scores.get(n, 0.0)) for n in names}
    return _meta(
        item,
        labels={n: False for n in names},
        scores=scores,
        reasons={n: _exclude_reason(sel_meta, n) for n in names},
        sel_meta=sel_meta,
        selected_names=[],
        shard_name=shard_name,
        funnel_stage=funnel_stage,
    )


def _empty_body_meta(
    item: dict, categories: list[dict], shard_name: str | None
) -> dict:
    names = [c["name"] for c in categories]
    return _meta(
        item,
        labels={n: False for n in names},
        scores={n: 0.0 for n in names},
        reasons={
            n: "skipped: empty body_text (page has no body; LLM not called)"
            for n in names
        },
        sel_meta={"strategy": "empty_body"},
        selected_names=[],
        shard_name=shard_name,
        funnel_stage=EMPTY_BODY,
        funnel_fields={"body_status": "empty"},
    )


def _missing_body_meta(
    item: dict, categories: list[dict], shard_name: str | None
) -> dict:
    names = [c["name"] for c in categories]
    fetch_error = (item.get("meta_data") or {}).get("fetch_error")
    fields: dict = {"body_status": "missing"}
    if fetch_error:
        fields["fetch_error"] = fetch_error
    return _meta(
        item,
        labels={n: False for n in names},
        scores={n: 0.0 for n in names},
        reasons={
            n: "skipped: missing body_text (fetch failed upstream; LLM not called)"
            for n in names
        },
        sel_meta={"strategy": "missing_body"},
        selected_names=[],
        shard_name=shard_name,
        funnel_stage=MISSING_BODY,
        funnel_fields=fields,
    )


def classify(
    items: list[dict],
    categories: list[dict],
    lexicons: dict[str, list[str]],
    *,
    model: str = DEFAULT_MODEL,
    max_words: int = 60000,
    shard_name: str | None = None,
    checkpoint: Checkpoint | None = None,
    router: str = ROUTER_WORDSEARCH,
    cosine_threshold: float = DEFAULT_COSINE_THRESHOLD,
    embed_model: str = DEFAULT_EMBED_MODEL,
    embed_device: str | None = None,
    score_only: bool = False,
    max_routed: int | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    stem_index_db: StemIndex | None = None,
    embed_cache: EmbedCache | None = None,
    completions: Completions | None = None,
    load_bodies: Callable[[Sequence[str]], dict[str, dict]] | None = None,
) -> tuple[list[dict], dict]:
    """Classify every page. Returns (results, stats).

    Pages with empty or missing body_text are kept in the output as FALSE with an
    explicit skip reason (not silently dropped). ``body_text is None`` (upstream
    fetch failed) is stamped ``missing_body``; a genuine empty string is
    ``empty_body``. Catalog items from ``StemIndex`` omit ``body_text`` when the
    page has a body. The cheap gate (wordsearch or cosine) routes the rest; hits
    go to the LLM (batch or sync, via ``completions``), misses are recorded
    FALSE. Pages missing from the bulk pass are rescued one-by-one with a
    truncated body. Raises ClassificationIncomplete if any routed page is still
    unclassified after rescue. ``score_only`` runs the gate and records routing
    decisions without calling the LLM. ``max_routed`` (ignored for ``score_only``
    and when a checkpoint already holds a pass-1 batch id or replies) aborts
    before the LLM if more pages routed than allowed; ``stats["capped"]`` is
    then True. ``on_progress(phase, done, total)`` is called during the cheap
    gate (``scan``, then ``wordsearch``) so a UI can show a bar; ignored if None.
    ``stem_index_db`` is the disk-backed inverted Porter-stem index; when set,
    wordsearch does not re-stem. ``embed_cache`` is a URL-keyed page-embedding
    index; hits skip re-encoding. ``load_bodies(urls)`` returns full page dicts
    (with ``body_text``) for routed URLs when items themselves have no body.
    ``completions`` is required when pages route to the LLM.
    """
    routed: list[dict] = []
    routed_meta: dict[str, dict] = {}
    results: dict[str, dict] = {}
    n_empty_body = 0
    n_missing_body = 0
    n_pages = len(items)
    cosine = router == ROUTER_COSINE
    miss_stage = COSINE_MISS if cosine else LEXICON_MISS
    gate_label = (
        f"cosine (threshold={cosine_threshold}, model={embed_model})"
        if cosine
        else "word-search against the inclusion lexicon"
    )
    log(f"Pass 1: {gate_label} routing {n_pages} pages (no LLM yet)…")

    _emit_progress(on_progress, "scan", 0, n_pages)
    scorable: list[tuple[dict, str]] = []
    catalog_ok = stem_index_db is not None
    for i, it in enumerate(items, start=1):
        md = it.get("meta_data") or {}
        if "body_text" not in md and catalog_ok:
            scorable.append((it, ""))
        else:
            raw_body = md.get("body_text")
            if raw_body is None:
                n_missing_body += 1
                results[it["url"]] = _missing_body_meta(it, categories, shard_name)
            elif not str(raw_body).strip():
                n_empty_body += 1
                results[it["url"]] = _empty_body_meta(it, categories, shard_name)
            else:
                scorable.append((it, str(raw_body)))
        if i % 500 == 0 or i == n_pages:
            log(f"  scanned bodies {i}/{n_pages}…")
        if i == 1 or i % _PROGRESS_EVERY == 0 or i == n_pages:
            _emit_progress(on_progress, "scan", i, n_pages)

    compiled: CompiledLexicon = []
    if cosine:
        bodies = [_searchable_text(it, body) for it, body in scorable]
        page_embeddings = _page_embeddings_from_cache(
            scorable, bodies, embed_cache,
            embed_model=embed_model, embed_device=embed_device,
        )
        decisions = select_by_cosine(
            bodies,
            categories,
            model=embed_model,
            threshold=cosine_threshold,
            device=embed_device,
            page_embeddings=page_embeddings,
        )
    else:
        n_score = len(scorable)
        compiled = compile_lexicon(categories, lexicons)
        log(f"  wordsearch {n_score} pages (stem + lexicon match)…")
        _emit_progress(on_progress, "wordsearch", 0, n_score)
        if stem_index_db is not None:
            id_by_url = stem_index_db.url_ids()
            indexed_ids = {
                id_by_url[it["url"]]
                for it, _body in scorable
                if it["url"] in id_by_url
            }
            hits = stem_index_db.match(compiled, page_ids=indexed_ids)
            empty_meta = {"strategy": "wordsearch_binary", "hits_per_cat": {}}
            decisions = []
            for it, body in scorable:
                pid = id_by_url.get(it["url"])
                if pid is not None and pid in hits:
                    sel_meta = hits[pid]
                    sel_cats = [
                        c for c in categories if c["name"] in sel_meta["hits_per_cat"]
                    ]
                    decisions.append((sel_cats, sel_meta))
                elif pid is not None:
                    decisions.append(([], empty_meta))
                elif body:
                    unigrams, bigrams = stem_index(_searchable_text(it, body))
                    decisions.append(match_compiled(unigrams, bigrams, compiled))
                else:
                    decisions.append(([], empty_meta))
            _emit_progress(on_progress, "wordsearch", n_score, n_score)
        else:
            decisions = []
            for i, (it, body) in enumerate(scorable, start=1):
                unigrams, bigrams = stem_index(_searchable_text(it, body))
                decisions.append(match_compiled(unigrams, bigrams, compiled))
                if i % 500 == 0 or i == n_score:
                    log(f"  wordsearch {i}/{n_score}…")
                if i == 1 or i % _PROGRESS_EVERY == 0 or i == n_score:
                    _emit_progress(on_progress, "wordsearch", i, n_score)

    for (it, _body), (sel_cats, sel_meta) in zip(scorable, decisions, strict=True):
        if sel_cats:
            routed.append(it)
            routed_meta[it["url"]] = sel_meta
        else:
            results[it["url"]] = _excluded_meta(
                it, categories, sel_meta, shard_name, funnel_stage=miss_stage,
            )

    if routed and load_bodies is not None:
        need = [
            it["url"]
            for it in routed
            if not str((it.get("meta_data") or {}).get("body_text") or "").strip()
        ]
        if need:
            loaded = load_bodies(need)
            routed = [loaded.get(it["url"], it) for it in routed]

    n_skipped = n_pages - len(routed) - n_empty_body - n_missing_body
    miss_name = "cosine-miss" if cosine else "lexicon-miss"
    hit_name = "cosine-hit" if cosine else "lexicon-hit"
    log(
        f"Pass 1: {n_pages} input → {n_missing_body} missing-body, "
        f"{n_empty_body} empty-body, "
        f"{n_skipped} {miss_name} (FALSE, no LLM), "
        f"{len(routed)} {hit_name} (sent to LLM)"
        + (" — score-only, LLM skipped" if score_only else "")
    )
    stats: dict = {
        "n_pages": n_pages,
        "n_routed": len(routed),
        "n_skipped": n_skipped,
        "n_empty_body": n_empty_body,
        "n_missing_body": n_missing_body,
        "n_rescued": 0,
        "n_batch_missing": 0,
        "model": model,
        "batch": None,
        "resumed": False,
        "router": router,
        "score_only": score_only,
        "capped": False,
        "max_routed": max_routed,
    }

    raw: dict[str, str] = {}
    batch_usage = {"input": 0, "output": 0}
    rescue_usage = {"input": 0, "output": 0}
    cat = categories[0]["name"] if categories else ""

    resume_pass1 = bool(
        checkpoint is not None
        and (
            checkpoint.pass1_batch_id
            or checkpoint.pass1_replies
            or checkpoint.pass1_routed_urls
        )
    )
    cap_hit = (
        not score_only
        and max_routed is not None
        and not resume_pass1
        and len(routed) > max_routed
    )
    skip_llm = score_only or cap_hit
    if skip_llm:
        names = [c["name"] for c in categories]
        if cap_hit:
            reason = (
                f"max-routed: {len(routed)} pages routed, cap {max_routed}; LLM not called"
            )
            stats["capped"] = True
            log(
                f"Pass 1: aborting before Anthropic — {len(routed)} routed exceeds "
                f"--max-routed {max_routed}"
            )
        else:
            reason = "score-only: routed; LLM not called"
        for it in routed:
            sel_meta = routed_meta[it["url"]]
            cosine_scores = sel_meta.get("scores") or {}
            scores = {n: float(cosine_scores.get(n, 0.0)) for n in names}
            results[it["url"]] = _meta(
                it,
                labels={n: False for n in names},
                scores=scores,
                reasons={n: reason for n in names},
                sel_meta=sel_meta,
                selected_names=names,
                shard_name=shard_name,
                funnel_stage=PASS1_TRUE,
                funnel_fields={
                    "pass1_label": False,
                    "pass1_reason": reason,
                },
            )
        stats["usage"] = {"model": model, "batch": batch_usage, "rescue": rescue_usage}
        ordered = [results[it["url"]] for it in items]
        stats["n_pass1_false"] = 0
        stats["n_pass1_true"] = 0
        return ordered, stats

    if routed and completions is None:
        raise RuntimeError("completions is required when pages are routed to the LLM")

    if routed:
        assert completions is not None
        requests: list[CompletionRequest] = []
        for i, it in enumerate(routed):
            sel_meta = routed_meta[it["url"]]
            excerpt, win_meta = _pass1_body(_body_text(it), compiled, sel_meta)
            routed_meta[it["url"]] = {**sel_meta, **win_meta}
            requests.append(
                CompletionRequest(
                    custom_id=str(i),
                    model=model,
                    max_tokens=MAX_TOKENS,
                    messages=[
                        {
                            "role": "user",
                            "content": build_prompt(
                                it["meta_data"].get("title", ""),
                                excerpt,
                                categories,
                                lexicon_hits=_lexicon_hit_terms(sel_meta),
                                excerpts=bool(compiled),
                            ),
                        }
                    ],
                )
            )
        if checkpoint is not None:
            checkpoint.record_pass1_routing([it["url"] for it in routed])
        resume_id = checkpoint.pass1_batch_id if checkpoint is not None else None
        already = checkpoint.pass1_replies if checkpoint is not None else None
        stats["resumed"] = bool(resume_id or already)

        def _remember(batch_id: str) -> None:
            if checkpoint is not None:
                checkpoint.record_pass1_batch(batch_id)

        def _on_result(custom_id: str, text: str, usage: dict) -> None:
            if checkpoint is not None:
                checkpoint.record_pass1_reply(custom_id, text, usage)

        raw, batch_usage, stats["batch"] = completions.complete_many(
            requests, label="classify",
            resume_id=resume_id, already=already,
            on_submitted=_remember, on_result=_on_result,
        )
        n_missing = len(routed) - len(raw)
        stats["n_batch_missing"] = n_missing
        if n_missing:
            log(
                f"Pass 1: {n_missing} routed pages missing from the LLM pass; "
                "rescuing one-by-one…"
            )

    unclassified: list[dict] = []
    for i, it in enumerate(routed):
        sel_meta = routed_meta[it["url"]]
        selected_names = [c["name"] for c in categories]
        text = raw.get(str(i), "")
        parsed = parse_response(text, categories) if text else None

        if parsed is None:
            # Bulk pass dropped or unparseable — rescue with a truncated body.
            assert completions is not None
            rescued = _rescue(
                completions, it, categories, model, max_words, compiled, sel_meta,
            )
            if rescued is None:
                unclassified.append(it)
                continue
            stats["n_rescued"] += 1
            labels, scores, reasons, rescue_meta, ru = rescued
            sel_meta = {**sel_meta, **rescue_meta}
            rescue_usage["input"] += ru["input"]
            rescue_usage["output"] += ru["output"]
        else:
            labels, scores, reasons = parsed

        labelled_true = bool(labels.get(cat))
        results[it["url"]] = _meta(
            it, labels, scores, reasons, sel_meta, selected_names, shard_name,
            funnel_stage=PASS1_TRUE if labelled_true else PASS1_FALSE,
            funnel_fields={
                "pass1_label": labelled_true,
                "pass1_score": scores.get(cat),
                "pass1_reason": reasons.get(cat, ""),
            },
        )

    if unclassified:
        urls = "\n".join(f"  - {it['url']}" for it in unclassified)
        raise ClassificationIncomplete(
            f"{len(unclassified)} routed page(s) could not be classified even "
            f"after rescue — refusing to default them to FALSE:\n{urls}"
        )

    if stats["n_rescued"]:
        log(f"Pass 1: rescued {stats['n_rescued']} pages")

    stats["usage"] = {"model": model, "batch": batch_usage, "rescue": rescue_usage}

    ordered = [results[it["url"]] for it in items]
    stats["n_pass1_false"] = sum(
        1 for r in ordered if r["meta_data"].get("funnel", {}).get("stage") == PASS1_FALSE
    )
    stats["n_pass1_true"] = sum(1 for r in ordered if r["meta_data"]["labels"].get(cat))
    return ordered, stats


def _rescue(
    completions: Completions,
    item: dict,
    categories: list[dict],
    model: str,
    max_words: int,
    compiled: CompiledLexicon,
    sel_meta: dict,
) -> tuple[dict[str, bool], dict[str, float], dict[str, str], dict, dict[str, int]] | None:
    """Re-classify one dropped page with a truncated body. None on failure.

    Only an API failure from ``complete_one`` counts as a recoverable miss (the
    page ends up in ``ClassificationIncomplete``, never a silent FALSE). Any
    other exception is a bug and propagates loudly rather than being mistaken
    for "unclassifiable". Wordsearch rescue uses the same hit windows as the
    bulk pass, so a hit in an annex is not dropped by truncating from the start
    of the full body.
    """
    body, win_meta = _pass1_body(_body_text(item), compiled, sel_meta)
    words = body.split()
    orig_n = len(words)
    truncated = orig_n > max_words
    if truncated:
        body = " ".join(words[:max_words])
    prompt = build_prompt(
        item["meta_data"].get("title", ""),
        body,
        categories,
        lexicon_hits=_lexicon_hit_terms(sel_meta),
        excerpts=bool(compiled),
    )
    got = completions.complete_one(
        CompletionRequest(
            custom_id="rescue",
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    )
    if got is None:
        return None
    text, usage = got
    parsed = parse_response(text, categories)
    if parsed is None:
        return None
    labels, scores, reasons = parsed
    if truncated:
        for c in categories:
            reasons[c["name"]] = (
                f"[body truncated to {max_words} words from {orig_n}] "
                + reasons[c["name"]]
            )
    sel_meta = {
        **win_meta,
        "strategy": "rescue_oversized",
        "max_words": max_words,
        "original_words": orig_n,
    }
    return labels, scores, reasons, sel_meta, usage
