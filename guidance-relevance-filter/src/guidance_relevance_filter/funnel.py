"""Per-page funnel stamps and the drop journal.

Every page in ``output.json`` carries ``meta_data.funnel.stage`` so a drop can
be sliced with jq without joining files. Pass-1 reasons live on
``meta_data.funnel`` so they survive pass 2 overwriting ``reasons``.
``funnel.json`` lists every URL at every stage — including missing-body,
empty-body, and cheap-gate misses (lexicon-miss / cosine-miss), not just the
LLM stages.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

MISSING_BODY = "missing_body"
EMPTY_BODY = "empty_body"
LEXICON_MISS = "lexicon_miss"
COSINE_MISS = "cosine_miss"
PASS1_FALSE = "pass1_false"
PASS1_TRUE = "pass1_true"
PASS2_DROP = "pass2_drop"
PASS2_KEEP = "pass2_keep"
PASS2_UNADJUDICATED = "pass2_unadjudicated"

# Cheap-gate misses: wordsearch still writes lexicon_miss; cosine writes cosine_miss.
ROUTING_MISS_STAGES = (LEXICON_MISS, COSINE_MISS)

LLM_STAGES = (PASS1_FALSE, PASS2_DROP, PASS2_KEEP, PASS2_UNADJUDICATED)

EXCLUSION_HITS = ("incidental", "homonym", "wrong_domain")


def stamp(meta: dict, stage: str, **fields: Any) -> None:
    """Set ``meta['funnel'].stage`` and merge extra fields (mutates)."""
    funnel = dict(meta.get("funnel") or {})
    funnel["stage"] = stage
    funnel.update(fields)
    meta["funnel"] = funnel


def stage_of(page: dict) -> str | None:
    return (page.get("meta_data") or {}).get("funnel", {}).get("stage")


def stage_counts(results: list[dict]) -> dict[str, int]:
    return dict(Counter(s for r in results if (s := stage_of(r)) is not None))


def lexicon_hits(meta: dict, cat: str) -> list[str]:
    hits = ((meta.get("selection_meta_body") or {}).get("hits_per_cat") or {}).get(cat) or []
    return list(hits)


def exclusion_hit_counts(results: list[dict]) -> dict[str, int]:
    counts = {tag: 0 for tag in EXCLUSION_HITS}
    counts.update(
        Counter(
            (r.get("meta_data") or {}).get("funnel", {}).get("exclusion_hit")
            for r in results
            if stage_of(r) == PASS2_DROP
        )
    )
    return {k: v for k, v in counts.items() if k}  # drop a None key if it appears


def page_ref(page: dict) -> dict[str, Any]:
    """Compact URL record for any funnel stage."""
    md = page.get("meta_data") or {}
    funnel = md.get("funnel") or {}
    rec: dict[str, Any] = {
        "url": page.get("url"),
        "title": md.get("title") or "",
        "document_type": md.get("document_type") or "",
        "is_withdrawn": bool(md.get("is_withdrawn")),
        "stage": funnel.get("stage"),
    }
    if funnel.get("body_status"):
        rec["body_status"] = funnel["body_status"]
    if funnel.get("fetch_error"):
        rec["fetch_error"] = funnel["fetch_error"]
    return rec


def _llm_record(page: dict, cat: str) -> dict:
    rec = page_ref(page)
    md = page["meta_data"]
    funnel = md.get("funnel") or {}
    rec["pass1_score"] = funnel.get("pass1_score", (md.get("scores") or {}).get(cat))
    rec["pass1_reason"] = funnel.get("pass1_reason", (md.get("reasons") or {}).get(cat, ""))
    rec["lexicon_hits"] = lexicon_hits(md, cat)
    if funnel.get("pass2_keep") is not None or funnel.get("stage") in {
        PASS2_DROP,
        PASS2_KEEP,
        PASS2_UNADJUDICATED,
    }:
        rec["pass2_keep"] = funnel.get("pass2_keep")
        rec["pass2_reason"] = funnel.get("pass2_reason")
        rec["exclusion_hit"] = funnel.get("exclusion_hit")
    return rec


def journal(
    results: list[dict],
    cat: str,
    *,
    n_pages: int,
    n_routed: int,
    n_pass1_true: int,
) -> dict:
    """Build ``funnel.json``: counts and a URL list for every drop stage."""

    def _pages(stage: str) -> list[dict]:
        build = _llm_record if stage in LLM_STAGES else lambda r, _c=None: page_ref(r)
        return [build(r, cat) for r in results if stage_of(r) == stage]

    missing = _pages(MISSING_BODY)
    empty = _pages(EMPTY_BODY)
    miss_lex = _pages(LEXICON_MISS)
    miss_cos = _pages(COSINE_MISS)
    p1_false = _pages(PASS1_FALSE)
    p2_drop = _pages(PASS2_DROP)
    p2_keep = _pages(PASS2_KEEP)
    p2_unadj = _pages(PASS2_UNADJUDICATED)
    stamped = any(stage_of(r) is not None for r in results)
    n_p1_false = (
        len(p1_false) if (p1_false or stamped) else max(n_routed - n_pass1_true, 0)
    )
    by_hit = exclusion_hit_counts(results)

    return {
        "category": cat,
        "counts": {
            "input_pages": n_pages,
            "missing_body": len(missing),
            "empty_body": len(empty),
            "lexicon_miss": len(miss_lex),
            "cosine_miss": len(miss_cos),
            "routing_miss": len(miss_lex) + len(miss_cos),
            "lexicon_hit": n_routed,
            "pass1_false": n_p1_false,
            "pass1_true": n_pass1_true,
            "pass2_dropped": len(p2_drop),
            "pass2_dropped_by_exclusion_hit": by_hit,
            "pass2_kept": len(p2_keep),
            "pass2_unadjudicated": len(p2_unadj),
            "final_true": len(p2_keep) + len(p2_unadj),
        },
        MISSING_BODY: missing,
        EMPTY_BODY: empty,
        LEXICON_MISS: miss_lex,
        COSINE_MISS: miss_cos,
        PASS1_FALSE: p1_false,
        PASS2_DROP: p2_drop,
        PASS2_KEEP: p2_keep,
        PASS2_UNADJUDICATED: p2_unadj,
    }
