"""Wordsearch-only score-only preview against the frozen corpus."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from guidance_relevance_filter.narrowing import compile_lexicon

from .category import lexicon_warnings, unmatched_scope_warnings_index
from .corpus import Corpus
from .cost_estimate import estimate_usd
from .funnel_view import (
    DOCUMENT_TYPE_MISS,
    DOCUMENT_TYPE_PASS,
    ORGANISATION_MISS,
    ORGANISATION_PASS,
    build_funnel_view,
)
from .settings import Settings
from .store import Store

URL_SAMPLE = 100
ROUTED_URL_CAP = 2000


def _hit_terms(meta: dict[str, Any], cat: str) -> list[str]:
    return list(((meta.get("hits_per_cat") or {}).get(cat)) or [])


def _term_hits(
    routed_ids: list[int],
    hits: dict[int, dict[str, Any]],
    cat: str,
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for pid in routed_ids:
        counts.update(_hit_terms(hits.get(pid) or {}, cat))
    return [{"term": term, "n": n} for term, n in counts.most_common()]


def _attach_hits(
    sample: dict[str, Any],
    page_ids: list[int],
    hits: dict[int, dict[str, Any]],
    cat: str,
) -> None:
    for row, pid in zip(sample["urls"], page_ids, strict=False):
        row["lexicon_hits"] = _hit_terms(hits.get(pid) or {}, cat)


def _sample_routed(
    index: Any,
    routed_ids: list[int],
    hits: dict[int, dict[str, Any]],
    cat: str,
) -> dict[str, Any]:
    """Every routed URL (capped), plus any term that would otherwise be missing.

    The unfiltered table still shows a short sample in the UI. Filter-by-term
    needs the actual pages, including rare terms that sit outside the head sample.
    """
    term_hits = _term_hits(routed_ids, hits, cat)
    sample = index.sample_pages(routed_ids, ROUTED_URL_CAP)
    head = list(routed_ids[:ROUTED_URL_CAP])
    _attach_hits(sample, head, hits, cat)

    covered = {row["term"] for row in term_hits}
    seen: set[str] = set()
    for row in sample["urls"]:
        seen.update(row.get("lexicon_hits") or [])
    missing = covered - seen
    if missing:
        head_set = set(head)
        extra_ids = [
            pid for pid in routed_ids
            if pid not in head_set
            and missing.intersection(_hit_terms(hits.get(pid) or {}, cat))
        ]
        extra = index.sample_pages(extra_ids, len(extra_ids))
        _attach_hits(extra, extra_ids, hits, cat)
        sample["urls"].extend(extra["urls"])

    sample["term_hits"] = term_hits
    sample["n"] = len(routed_ids)
    sample["truncated"] = len(sample["urls"]) < len(routed_ids)
    return sample


def _assemble(
    *,
    counts: dict[str, int],
    stages: list[dict],
    funnel_counts: dict[str, Any],
    terms: list[str],
    settings: Settings,
    cached: bool,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    would_route = int(counts["would_route"])
    over_run_cap = would_route > settings.grf_max_routed
    warnings = lexicon_warnings(terms) + list(extra_warnings or [])
    if over_run_cap:
        noun = "page" if would_route == 1 else "pages"
        warnings.append(
            f"{would_route:,} {noun} would go to the model — over the run cap of "
            f"{settings.grf_max_routed:,}. Wordsearch is not truncated; "
            "Run filter is blocked."
        )
    view = build_funnel_view(stages, counts)
    return {
        "counts": counts,
        **view,
        "warnings": warnings,
        "cap": {
            "max_routed": settings.grf_max_routed,
            "ok": not over_run_cap,
        },
        "funnel_counts": funnel_counts,
        "cached": cached,
        "cost_estimate": estimate_usd(would_route, batch=True),
        "cost_estimate_sync": estimate_usd(would_route, batch=False),
    }


def run_preview(
    *,
    corpus: Corpus,
    categories: list[dict],
    lexicons: dict[str, list[str]],
    settings: Settings,
    store: Store | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    organisations: list[str] | None = None,
    document_types: list[str] | None = None,
) -> dict[str, Any]:
    cat = categories[0]["name"]
    terms = lexicons.get(cat) or []
    orgs = organisations or []
    types = document_types or []
    index = corpus.ensure_stem_index(on_progress=on_progress)
    extra_warnings = unmatched_scope_warnings_index(
        index, organisations=orgs, document_types=types,
    )
    corpus_sha = corpus.require().with_body_sha256
    cache_key = (
        Store.wordsearch_cache_key(
            corpus_sha, cat, lexicons,
            organisations=orgs, document_types=types,
        ) if store else None
    )
    if store is not None and cache_key is not None:
        hit = store.load_wordsearch_cache(cache_key)
        if hit is not None:
            return _assemble(
                counts=hit["counts"],
                stages=hit["stages"],
                funnel_counts=hit["funnel_counts"],
                terms=terms,
                settings=settings,
                cached=True,
                extra_warnings=extra_warnings,
            )

    all_ids = index.all_page_ids()
    n_scan = len(all_ids)
    if on_progress is not None:
        on_progress("scan", 0, n_scan)
    if orgs:
        org_ok = index.matching_organisation_ids(orgs)
        after_org = [i for i in all_ids if i in org_ok]
        org_dropped = [i for i in all_ids if i not in org_ok]
    else:
        after_org = all_ids
        org_dropped = []
    if types:
        type_ok = index.matching_document_type_ids(types)
        page_ids = [i for i in after_org if i in type_ok]
        type_dropped = [i for i in after_org if i not in type_ok]
    else:
        page_ids = after_org
        type_dropped = []
    if on_progress is not None:
        on_progress("scan", n_scan, n_scan)

    compiled = compile_lexicon(categories, lexicons)
    by_state = index.ids_by_body_state(page_ids)
    ok_ids = by_state.get("ok") or []
    empty_ids = by_state.get("empty") or []
    missing_ids = by_state.get("missing") or []
    if on_progress is not None:
        on_progress("wordsearch", 0, len(ok_ids))
    hits = index.match(compiled, page_ids=set(ok_ids))
    routed_ids = [i for i in ok_ids if i in hits]
    miss_ids = [i for i in ok_ids if i not in hits]
    if on_progress is not None:
        on_progress("wordsearch", len(ok_ids), len(ok_ids))

    would_route = len(routed_ids)
    funnel_counts = {
        "input_pages": len(page_ids),
        "missing_body": len(missing_ids),
        "empty_body": len(empty_ids),
        "lexicon_miss": len(miss_ids),
        "cosine_miss": 0,
        "routing_miss": len(miss_ids),
        "lexicon_hit": would_route,
        "pass1_false": 0,
        "pass1_true": 0,
        "pass2_dropped": 0,
        "pass2_dropped_by_exclusion_hit": {},
        "pass2_kept": 0,
        "pass2_unadjudicated": 0,
        "final_true": 0,
    }
    stages: list[dict[str, Any]] = []
    if orgs:
        stages.append({
            "stage": ORGANISATION_MISS,
            "label": "Wrong organisation",
            **index.sample_pages(org_dropped, URL_SAMPLE),
        })
        stages.append({
            "stage": ORGANISATION_PASS,
            "label": "Matching organisation",
            **index.sample_pages(after_org, URL_SAMPLE),
        })
    if types:
        stages.append({
            "stage": DOCUMENT_TYPE_MISS,
            "label": "Wrong document type",
            **index.sample_pages(type_dropped, URL_SAMPLE),
        })
        stages.append({
            "stage": DOCUMENT_TYPE_PASS,
            "label": "Matching document type",
            **index.sample_pages(page_ids, URL_SAMPLE),
        })
    stages.extend([
        {
            "stage": "missing_body",
            "label": "Couldn't download the page",
            **index.sample_pages(missing_ids, URL_SAMPLE),
        },
        {
            "stage": "empty_body",
            "label": "Page has no text",
            **index.sample_pages(empty_ids, URL_SAMPLE),
        },
        {
            "stage": "lexicon_miss",
            "label": "No topic keywords",
            **index.sample_pages(miss_ids, URL_SAMPLE),
        },
        {
            "stage": "would_route",
            "label": "Would go to the model",
            **_sample_routed(index, routed_ids, hits, cat),
        },
    ])
    counts = {
        "corpus_pages": len(all_ids),
        "input_pages": len(page_ids),
        "organisation_filter": bool(orgs),
        "document_type_filter": bool(types),
        "organisation_miss": len(org_dropped),
        "document_type_miss": len(type_dropped),
        "missing_body": len(missing_ids),
        "empty_body": len(empty_ids),
        "lexicon_miss": len(miss_ids),
        "would_route": would_route,
    }
    payload = {
        "counts": counts,
        "stages": stages,
        "funnel_counts": funnel_counts,
    }
    if store is not None and cache_key is not None:
        store.save_wordsearch_cache(cache_key, payload)
    return _assemble(
        counts=counts,
        stages=stages,
        funnel_counts=funnel_counts,
        terms=terms,
        settings=settings,
        cached=False,
        extra_warnings=extra_warnings,
    )
