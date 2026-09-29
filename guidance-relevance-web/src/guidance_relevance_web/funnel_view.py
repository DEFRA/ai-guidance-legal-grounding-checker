"""Sankey payload for the operator UI.

Drop leftovers (wrong org/type, no-keyword ~96%) crush every other bar.
The diagram is the surviving count at each gate; leftovers are chips.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from guidance_relevance_filter.annotate import STAGE_GUIDE
from guidance_relevance_filter.funnel import (
    COSINE_MISS,
    EMPTY_BODY,
    LEXICON_MISS,
    MISSING_BODY,
    PASS1_FALSE,
    PASS2_DROP,
    PASS2_KEEP,
    PASS2_UNADJUDICATED,
)

from .store import URL_SAMPLE

ORGANISATION_MISS = "organisation_miss"
DOCUMENT_TYPE_MISS = "document_type_miss"
ORGANISATION_PASS = "organisation_pass"
DOCUMENT_TYPE_PASS = "document_type_pass"
CORPUS_IN = "corpus_in"

# Keyword-miss is ~96% of a typical corpus; cosine is unused in this app.
# Org/type misses are the same shape of leftover — chips, not bars.
OMIT_FROM_SANKEY = frozenset({LEXICON_MISS, COSINE_MISS})
SCOPE_MISS = frozenset({ORGANISATION_MISS, DOCUMENT_TYPE_MISS})
SCOPE_PASS = frozenset({ORGANISATION_PASS, DOCUMENT_TYPE_PASS})
SCOPE_STAGES = SCOPE_MISS | SCOPE_PASS | {CORPUS_IN}

CHEAP_STAGES = (MISSING_BODY, EMPTY_BODY, LEXICON_MISS, COSINE_MISS)

FINISHED_STAGES = (
    MISSING_BODY,
    EMPTY_BODY,
    LEXICON_MISS,
    COSINE_MISS,
    PASS1_FALSE,
    PASS2_DROP,
    PASS2_KEEP,
    PASS2_UNADJUDICATED,
)

_GUIDE = {stage: (label, meaning) for stage, label, meaning in STAGE_GUIDE}

_SHORT = {
    MISSING_BODY: "Couldn't download",
    EMPTY_BODY: "No text",
    LEXICON_MISS: "No topic keywords",
    COSINE_MISS: "Below similarity",
    "would_route": "Would go to the model",
    "lexicon_hit": "Input Shortlist",
    "preview_in": "Still in play",
    CORPUS_IN: "Frozen index",
    ORGANISATION_MISS: "Wrong organisation",
    ORGANISATION_PASS: "Matching organisation",
    DOCUMENT_TYPE_MISS: "Wrong document type",
    DOCUMENT_TYPE_PASS: "Matching document type",
    PASS1_FALSE: "Dropped",
    "pass1_true": "Filtered by LLM Inclusion Rules",
    PASS2_DROP: "Dropped",
    PASS2_KEEP: "Filtered by LLM Exclusion Rules",
    PASS2_UNADJUDICATED: "Kept (pass 2 failed)",
}

_MEANING = {
    "would_route": "These pages mention a word from your topic list. They would be read if you run the filter.",
    "lexicon_hit": "These pages mention a word from your topic list. We sent them for a first read.",
    "preview_in": "Pages still in play after setting aside those with no topic words.",
    CORPUS_IN: "Every page on the frozen index, before organisation and document-type filters.",
    ORGANISATION_MISS: "Published by a different organisation than the ones you chose.",
    ORGANISATION_PASS: "Published by an organisation you chose.",
    DOCUMENT_TYPE_MISS: "Wrong kind of page — not one of the document types you chose.",
    DOCUMENT_TYPE_PASS: "The kind of page you asked for (for example guidance).",
    MISSING_BODY: "We could not download the page, so there was nothing to read.",
    EMPTY_BODY: "The page had no text to read.",
    LEXICON_MISS: "None of your topic words appeared, so we did not read it. There are so many of these they would squash the diagram.",
    PASS1_FALSE: "A first read decided this is not about your topic. Stopped here.",
    "pass1_true": "A first read thought this looks relevant, so it got a second, stricter read.",
    PASS2_DROP: "A closer read decided the topic is only mentioned in passing, or the page is really about something else.",
    PASS2_KEEP: "Both reads agreed: this page is about your topic.",
    PASS2_UNADJUDICATED: "The second read failed, so we kept it rather than dropping it by accident.",
}


def _n(row: dict[str, Any] | None) -> int:
    if not row:
        return 0
    return int(row.get("n") or 0)


def _guide(stage: str) -> tuple[str, str]:
    label = _SHORT.get(stage) or (_GUIDE[stage][0] if stage in _GUIDE else stage)
    meaning = _MEANING.get(stage) or (_GUIDE[stage][1] if stage in _GUIDE else "")
    return label, meaning


def _hits(src: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (src or {}).get("term_hits") or []
    return list(rows) if rows else []


def _merge_term_hits(*srcs: dict[str, Any] | None) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for src in srcs:
        for row in _hits(src):
            term = str(row.get("term") or "")
            if term:
                counts[term] += int(row.get("n") or 0)
    return [{"term": term, "n": n} for term, n in counts.most_common()]


def _term_hits_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        hits = row.get("lexicon_hits") or []
        if isinstance(hits, list):
            counts.update(str(t) for t in hits if t)
    return [{"term": term, "n": n} for term, n in counts.most_common()]


def _url_row(row: dict[str, Any]) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "url": row.get("url") or "",
        "title": row.get("title") or "",
        "reason": row.get("pass2_reason") or row.get("pass1_reason") or "",
    }
    hits = row.get("lexicon_hits") or []
    if isinstance(hits, list) and hits:
        rec["lexicon_hits"] = [str(t) for t in hits if t]
    return rec


def _node(
    node_id: str,
    n: int,
    column: int,
    *,
    stage: str | None,
    urls: list[dict] | None = None,
    truncated: bool = False,
    term_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    label, meaning = _guide(stage or node_id)
    rec: dict[str, Any] = {
        "id": node_id,
        "label": _SHORT.get(node_id, _SHORT.get(stage or "", label)),
        "meaning": _MEANING.get(node_id) or meaning,
        "n": n,
        "column": column,
        "stage": stage,
        "urls": urls or [],
        "truncated": truncated,
    }
    if term_hits:
        rec["term_hits"] = term_hits
    return rec


def _chip(stage: str, n: int, src: dict[str, Any] | None, *, hidden: bool) -> dict[str, Any]:
    label, meaning = _guide(stage)
    rec: dict[str, Any] = {
        "stage": stage,
        "label": _SHORT.get(stage, label),
        "meaning": meaning,
        "n": n,
        "hidden": hidden,
        "urls": (src or {}).get("urls") or [],
        "truncated": bool((src or {}).get("truncated")),
    }
    hits = _hits(src)
    if hits:
        rec["term_hits"] = hits
    return rec


def _union_urls(*rows: dict[str, Any] | None) -> tuple[list[dict], bool]:
    urls: list[dict] = []
    truncated = False
    for row in rows:
        if not row:
            continue
        truncated = truncated or bool(row.get("truncated"))
        urls.extend(row.get("urls") or [])
    if len(urls) > URL_SAMPLE and not any((row or {}).get("term_hits") for row in rows):
        return urls[:URL_SAMPLE], True
    return urls, truncated


def _count(counts: dict[str, Any], *keys: str, fallback: int = 0) -> int:
    for key in keys:
        if counts.get(key) is not None:
            return int(counts[key] or 0)
    return fallback


def _applied(
    counts: dict[str, Any],
    by: dict[str, dict[str, Any]],
    *,
    flag: str,
    stages: tuple[str, ...],
) -> bool:
    if flag in counts:
        return bool(counts[flag])
    return any(s in by for s in stages)


def _scope_columns(
    counts: dict[str, Any],
    by: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, int, list[str]] | None:
    """Survivor chain: matching org → matching type. Index volume stays off the bars."""
    org_on = _applied(
        counts, by, flag="organisation_filter",
        stages=(ORGANISATION_MISS, ORGANISATION_PASS),
    )
    type_on = _applied(
        counts, by, flag="document_type_filter",
        stages=(DOCUMENT_TYPE_MISS, DOCUMENT_TYPE_PASS),
    )
    if not org_on and not type_on:
        return None

    n_org_miss = _n(by.get(ORGANISATION_MISS)) or _count(counts, ORGANISATION_MISS)
    n_type_miss = _n(by.get(DOCUMENT_TYPE_MISS)) or _count(counts, DOCUMENT_TYPE_MISS)
    n_input = _count(counts, "input_pages")
    n_corpus = _count(counts, "corpus_pages")
    if n_corpus <= 0:
        n_corpus = n_org_miss + n_type_miss + n_input

    n_after_org = _n(by.get(ORGANISATION_PASS))
    if org_on and not n_after_org and ORGANISATION_PASS not in by:
        n_after_org = n_corpus - n_org_miss
    elif not org_on:
        n_after_org = n_corpus

    n_after_type = _n(by.get(DOCUMENT_TYPE_PASS))
    if type_on and not n_after_type and DOCUMENT_TYPE_PASS not in by:
        n_after_type = n_input
    elif not type_on:
        n_after_type = n_after_org

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    parts = [f"{n_corpus:,} on the index"]
    source: str | None = None
    col = -1

    if org_on:
        col += 1
        src = by.get(ORGANISATION_PASS) or {}
        nodes.append(_node(
            ORGANISATION_PASS, n_after_org, col, stage=ORGANISATION_PASS,
            urls=src.get("urls") or [], truncated=bool(src.get("truncated")),
        ))
        if source is not None and n_after_org:
            links.append({"source": source, "target": ORGANISATION_PASS, "n": n_after_org})
        source = ORGANISATION_PASS
        parts.append(f"{n_after_org:,} matching organisation")

    if type_on:
        col += 1
        src = by.get(DOCUMENT_TYPE_PASS) or {}
        nodes.append(_node(
            DOCUMENT_TYPE_PASS, n_after_type, col, stage=DOCUMENT_TYPE_PASS,
            urls=src.get("urls") or [], truncated=bool(src.get("truncated")),
        ))
        if source is not None and n_after_type:
            links.append({"source": source, "target": DOCUMENT_TYPE_PASS, "n": n_after_type})
        source = DOCUMENT_TYPE_PASS
        parts.append(f"{n_after_type:,} matching document type")

    if source is None:
        return None
    return nodes, links, source, col, parts


def _append_cheap(
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    source: str,
    col: int,
    cheap: list[dict[str, Any]],
) -> int:
    if not cheap:
        return col
    col += 1
    for s in cheap:
        n = _n(s)
        nodes.append(_node(
            s["stage"], n, col, stage=s["stage"],
            urls=s.get("urls") or [], truncated=bool(s.get("truncated")),
            term_hits=_hits(s),
        ))
        if n:
            links.append({"source": source, "target": s["stage"], "n": n})
    return col


def build_funnel_view(
    stages: list[dict[str, Any]],
    counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Chips + Sankey. Zero-count stages and drop leftovers stay off the diagram."""
    counts = dict(counts or {})
    by = {s["stage"]: s for s in stages if s.get("stage")}

    n_p1_false = _count(counts, "pass1_false", fallback=_n(by.get(PASS1_FALSE)))
    n_p2_drop = _count(counts, "pass2_dropped", "pass2_drop", fallback=_n(by.get(PASS2_DROP)))
    n_p2_keep = _count(counts, "pass2_kept", "pass2_keep", fallback=_n(by.get(PASS2_KEEP)))
    n_p2_unadj = _count(
        counts, "pass2_unadjudicated", fallback=_n(by.get(PASS2_UNADJUDICATED))
    )
    n_p1_true = _count(
        counts, "pass1_true", fallback=n_p2_drop + n_p2_keep + n_p2_unadj
    )
    n_hit = _count(counts, "lexicon_hit", "would_route", fallback=n_p1_false + n_p1_true)
    n_would = _count(counts, "would_route", fallback=_n(by.get("would_route")))

    has_llm = bool(n_p1_false or n_p1_true)
    scoped = _scope_columns(counts, by)

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    caption = ""

    if has_llm:
        p1_urls, p1_trunc = _union_urls(
            by.get(PASS2_DROP), by.get(PASS2_KEEP), by.get(PASS2_UNADJUDICATED)
        )
        hit_urls, hit_trunc = _union_urls(by.get(PASS1_FALSE), {
            "urls": p1_urls, "truncated": p1_trunc,
        })
        hit_col = 0
        source = "lexicon_hit"
        parts: list[str] = []
        if scoped is not None:
            nodes, links, source, col, parts = scoped
            hit_col = col + 1
            if n_hit:
                links.append({"source": source, "target": "lexicon_hit", "n": n_hit})
        nodes.append(_node(
            "lexicon_hit", n_hit, hit_col, stage=None, urls=hit_urls, truncated=hit_trunc,
            term_hits=_merge_term_hits(
                by.get(PASS1_FALSE),
                by.get(PASS2_DROP),
                by.get(PASS2_KEEP),
                by.get(PASS2_UNADJUDICATED),
            ),
        ))
        if n_p1_false:
            src = by.get(PASS1_FALSE) or {}
            nodes.append(_node(
                PASS1_FALSE, n_p1_false, hit_col + 1, stage=PASS1_FALSE,
                urls=src.get("urls") or [], truncated=bool(src.get("truncated")),
                term_hits=_hits(src),
            ))
            links.append({"source": "lexicon_hit", "target": PASS1_FALSE, "n": n_p1_false})
        if n_p1_true:
            nodes.append(_node(
                "pass1_true", n_p1_true, hit_col + 1, stage=None, urls=p1_urls, truncated=p1_trunc,
                term_hits=_merge_term_hits(
                    by.get(PASS2_DROP), by.get(PASS2_KEEP), by.get(PASS2_UNADJUDICATED),
                ),
            ))
            links.append({"source": "lexicon_hit", "target": "pass1_true", "n": n_p1_true})
            for sid, n in (
                (PASS2_DROP, n_p2_drop),
                (PASS2_KEEP, n_p2_keep),
                (PASS2_UNADJUDICATED, n_p2_unadj),
            ):
                if not n:
                    continue
                src = by.get(sid) or {}
                nodes.append(_node(
                    sid, n, hit_col + 2, stage=sid,
                    urls=src.get("urls") or [], truncated=bool(src.get("truncated")),
                    term_hits=_hits(src),
                ))
                links.append({"source": "pass1_true", "target": sid, "n": n})
        kept = n_p2_keep + n_p2_unadj
        llm_caption = f"{n_hit:,} keyword hits → {n_p1_true:,} first-pass yes → {kept:,} kept"
        caption = " → ".join(parts + [llm_caption]) if parts else llm_caption
    else:
        shown = [
            s for s in stages
            if _n(s) and s["stage"] not in OMIT_FROM_SANKEY | SCOPE_STAGES
        ]
        if n_hit and not any(s["stage"] in {"would_route", "lexicon_hit"} for s in shown):
            src = by.get("would_route") or {}
            shown.append({
                "stage": "would_route",
                "label": _SHORT["would_route"],
                "n": n_hit,
                "urls": src.get("urls") or [],
                "truncated": bool(src.get("truncated")),
                "term_hits": _hits(src),
            })
        if scoped is not None:
            nodes, links, feeder, col, parts = scoped
            _append_cheap(nodes, links, feeder, col, shown)
            focus = n_would or n_hit
            caption = " → ".join(
                parts + ([f"{focus:,} would go to the model"] if focus else [])
            )
        else:
            total = sum(_n(s) for s in shown)
            if len(shown) > 1 and total:
                in_urls, in_trunc = _union_urls(*shown)
                nodes.append(_node(
                    "preview_in", total, 0, stage=None, urls=in_urls, truncated=in_trunc,
                ))
                for s in shown:
                    nodes.append(_node(
                        s["stage"], _n(s), 1, stage=s["stage"],
                        urls=s.get("urls") or [], truncated=bool(s.get("truncated")),
                        term_hits=_hits(s),
                    ))
                    links.append({"source": "preview_in", "target": s["stage"], "n": _n(s)})
            elif shown:
                s = shown[0]
                nodes.append(_node(
                    s["stage"], _n(s), 0, stage=s["stage"],
                    urls=s.get("urls") or [], truncated=bool(s.get("truncated")),
                    term_hits=_hits(s),
                ))
            focus = n_would or n_hit
            if focus:
                caption = f"{focus:,} would go to the model"

    sankey_ids = {n["id"] for n in nodes}
    chips: list[dict[str, Any]] = []
    for sid in (ORGANISATION_MISS, DOCUMENT_TYPE_MISS, *CHEAP_STAGES):
        src = by.get(sid)
        n = _n(src) or _count(counts, sid)
        if not n:
            continue
        hidden = sid in OMIT_FROM_SANKEY
        if hidden or sid not in sankey_ids:
            chips.append(_chip(sid, n, src, hidden=hidden))

    nonzero = [s for s in stages if _n(s)]
    return {
        "stages": nonzero,
        "chips": chips,
        "sankey": {"nodes": nodes, "links": links},
        "caption": caption,
    }


def _scope_stage(stage: str, n: int, src: dict[str, Any] | None) -> dict[str, Any]:
    label, meaning = _guide(stage)
    return {
        "stage": stage,
        "label": _SHORT.get(stage, label),
        "meaning": meaning,
        "n": n,
        "urls": (src or {}).get("urls") or [],
        "truncated": bool((src or {}).get("truncated")),
    }


def view_from_journal(
    doc: dict[str, Any],
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Job-page view from a written ``funnel.json`` plus optional preview scope."""
    counts = dict(doc.get("counts") or {})
    stages: list[dict[str, Any]] = []
    if scope:
        sc = scope.get("counts") or {}
        for key in (
            "corpus_pages",
            "input_pages",
            "organisation_miss",
            "document_type_miss",
            "organisation_filter",
            "document_type_filter",
        ):
            if sc.get(key) is not None:
                counts[key] = sc[key]
        if "organisation_filter" not in counts:
            counts["organisation_filter"] = bool(scope.get("organisations"))
        if "document_type_filter" not in counts:
            counts["document_type_filter"] = bool(scope.get("document_types"))
        by_scope = {s["stage"]: s for s in scope.get("stages") or [] if s.get("stage")}
        if counts.get("organisation_filter"):
            stages.append(_scope_stage(
                ORGANISATION_MISS,
                _count(counts, ORGANISATION_MISS),
                by_scope.get(ORGANISATION_MISS),
            ))
            stages.append(_scope_stage(
                ORGANISATION_PASS,
                _n(by_scope.get(ORGANISATION_PASS)) or (
                    _count(counts, "corpus_pages") - _count(counts, ORGANISATION_MISS)
                ),
                by_scope.get(ORGANISATION_PASS),
            ))
        if counts.get("document_type_filter"):
            stages.append(_scope_stage(
                DOCUMENT_TYPE_MISS,
                _count(counts, DOCUMENT_TYPE_MISS),
                by_scope.get(DOCUMENT_TYPE_MISS),
            ))
            stages.append(_scope_stage(
                DOCUMENT_TYPE_PASS,
                _n(by_scope.get(DOCUMENT_TYPE_PASS)) or _count(counts, "input_pages"),
                by_scope.get(DOCUMENT_TYPE_PASS),
            ))
    for stage in FINISHED_STAGES:
        rows = doc.get(stage) or []
        label, meaning = _guide(stage)
        n = _count(counts, stage, fallback=len(rows))
        if stage == PASS2_DROP:
            n = _count(counts, "pass2_dropped", "pass2_drop", fallback=len(rows))
        elif stage == PASS2_KEEP:
            n = _count(counts, "pass2_kept", "pass2_keep", fallback=len(rows))
        term_hits = _term_hits_from_rows(rows)
        cheap = stage in CHEAP_STAGES
        url_rows = rows[:URL_SAMPLE] if cheap else rows
        stages.append({
            "stage": stage,
            "label": label,
            "meaning": meaning,
            "n": n,
            "urls": [_url_row(r) for r in url_rows],
            "truncated": cheap and len(rows) > URL_SAMPLE,
            **({"term_hits": term_hits} if term_hits else {}),
        })
    return build_funnel_view(stages, counts)
