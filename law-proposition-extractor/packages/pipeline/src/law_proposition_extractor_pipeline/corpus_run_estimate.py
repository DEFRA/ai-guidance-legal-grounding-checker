"""Dry-run extraction load estimates (no LLM calls)."""

from __future__ import annotations

from typing import Any, Literal

from law_proposition_extractor_domain import SourceFragment, SourceRecord
from law_proposition_extractor_llm.settings import LLMSettings

from .extract import (
    _estimate_extract_prompt_tokens,
    _max_body_chars_for_extract_budget,
    _plan_llm_text_chunks,
)
from .intake import create_cluster, create_topic, slugify
from .source_fragmentation import (
    expand_monolithic_source_fragment,
    max_fragment_body_chars_for_llm_budget,
)
from .sources.service import SourceIngestionService


def _append_unique(notes: list[str], message: str) -> None:
    if message not in notes:
        notes.append(message)


def _build_recommendations(
    *,
    max_estimated_input_tokens_per_call: int,
    jobs_over_context_budget: int,
    estimated_llm_invocations: int,
    cost_class: str,
) -> list[str]:
    notes: list[str] = []
    if max_estimated_input_tokens_per_call > 100_000:
        _append_unique(notes, "Run with caution: at least one extraction call is very large.")
    if jobs_over_context_budget > 0:
        _append_unique(notes, "Do not run until oversized jobs are split or skipped.")
    if cost_class == "large":
        _append_unique(notes, "Run with caution: this profile may make many model calls.")
    if cost_class == "very_large":
        _append_unique(notes, "Split this profile or run staged subsets before frontier extraction.")
    if estimated_llm_invocations > 50:
        _append_unique(notes, "Run with caution: this profile may make many model calls.")
    if estimated_llm_invocations > 150:
        _append_unique(
            notes,
            "Staged run strongly recommended: estimated model invocation count is very high.",
        )
        _append_unique(
            notes,
            "Batch mode may reduce provider token cost for async workloads.",
        )
    return notes


def _cost_class(
    *,
    n_sources: int,
    n_jobs: int,
    max_tokens: int,
    over_budget_jobs: int,
) -> str:
    if over_budget_jobs > 0 or n_jobs >= 48 or max_tokens >= 180_000 or n_sources >= 18:
        return "very_large"
    if n_jobs >= 24 or max_tokens >= 120_000 or n_sources >= 12:
        return "large"
    if n_jobs >= 12 or max_tokens >= 80_000 or n_sources >= 6:
        return "medium"
    return "small"


def estimate_corpus_run_from_case(
    case_data: dict[str, Any],
    *,
    extraction_mode: Literal["frontier", "local"] = "frontier",
    fetch_xml: Any | None = None,
    offline_chars_per_instrument: int | None = None,
    llm_settings: LLMSettings | None = None,
) -> dict[str, Any]:
    """
    Estimate sources, expanded fragments, chunk-level LLM invocations, and token exposure.

    Does not call model providers. With fetch_xml=None uses real network fetch via
    LegislationGovUkAuthorityAdapter; tests should inject fetch_xml.
    If offline_chars_per_instrument is set, skips ingest and uses synthetic bodies of that size.
    """
    topic_cfg = case_data["topic"]
    cluster_cfg = case_data["cluster"]
    topic = create_topic(
        name=topic_cfg["name"],
        description=topic_cfg.get("description", ""),
        subject_tags=topic_cfg.get("subject_tags", []),
    )
    cluster = create_cluster(topic=topic, name=cluster_cfg["name"], description=cluster_cfg.get("description", ""))

    raw_sources = list(case_data.get("sources") or [])
    if not raw_sources and case_data.get("case_analysis_mode") == "candidate_universe":
        recommendations = _build_recommendations(
            max_estimated_input_tokens_per_call=0,
            jobs_over_context_budget=0,
            estimated_llm_invocations=0,
            cost_class="small",
        )
        return {
            "source_count": 0,
            "base_fragment_count": 0,
            "expanded_fragment_count": 0,
            "estimated_llm_invocations": 0,
            "max_estimated_input_tokens_per_call": 0,
            "jobs_over_context_budget": 0,
            "largest_fragment_source_id": None,
            "largest_fragment_title": None,
            "largest_fragment_locator": None,
            "largest_fragment_chars": 0,
            "largest_fragment_estimated_input_tokens": 0,
            "estimated_input_tokens_total": 0,
            "average_estimated_input_tokens_per_call": 0.0,
            "top_large_fragments": [],
            "top_contributing_sources": [],
            "recommendations": recommendations,
            "cost_class": "small",
            "mode": "candidate_universe_no_sources",
            "note": "No legislation sources queued for fetch — discovery candidates only.",
        }

    settings = llm_settings or LLMSettings()
    max_input = int(getattr(settings, "max_extract_input_tokens", 150_000))
    overlap = min(8192, max(512, max_input // 40))

    raw_list = raw_sources
    if offline_chars_per_instrument is not None and offline_chars_per_instrument > 0:
        synth: list[dict[str, Any]] = []
        for i, raw in enumerate(raw_list, start=1):
            r = dict(raw)
            body = "x" * int(offline_chars_per_instrument)
            r["authority"] = "case_file"
            r["title"] = str(r.get("title") or f"synthetic-{i}")
            r["jurisdiction"] = str(r.get("jurisdiction") or "UK")
            r["citation"] = str(r.get("citation") or "SYNTH")
            r["kind"] = str(r.get("kind") or "instrument")
            r["text"] = body
            r["provenance"] = "estimate.offline_heuristic"
            synth.append(r)
        raw_list = synth

    adapters: dict[str, Any] = {}
    if fetch_xml is not None:
        from law_proposition_extractor_pipeline.sources.adapters import LegislationGovUkAuthorityAdapter

        adapters["legislation_gov_uk"] = LegislationGovUkAuthorityAdapter(fetch_xml=fetch_xml)

    intake = SourceIngestionService(adapters=adapters if adapters else None)
    ingested = intake.ingest_sources(raw_list)

    scopes, limit = _scopes_and_limit(case_data)

    expanded_frags: list[SourceFragment] = []
    for frag in ingested.fragments:
        max_body = max_fragment_body_chars_for_llm_budget(
            max_extract_input_tokens=settings.max_extract_input_tokens
        )
        overlap_f = min(8192, max(512, settings.max_extract_input_tokens // 40))
        expanded_frags.extend(
            expand_monolithic_source_fragment(
                frag,
                max_body_chars=max_body,
                overlap_chars=overlap_f,
                slugify=slugify,
            )
        )

    total_llm = 0
    max_tok = 0
    over_budget = 0
    largest = 0
    largest_fragment_source_id: str | None = None
    largest_fragment_title: str | None = None
    largest_fragment_locator: str | None = None
    largest_fragment_estimated_input_tokens = 0
    large_fragments: list[dict[str, Any]] = []
    source_totals: dict[str, dict[str, Any]] = {}
    estimated_input_tokens_total = 0
    llm_mode: Literal["frontier", "local"] = extraction_mode

    for frag in expanded_frags:
        src = _record_by_id(ingested.sources, frag.source_record_id)
        work = src.model_copy(
            deep=True,
            update={
                "authoritative_text": frag.fragment_text,
                "authoritative_locator": frag.locator,
                "metadata": {
                    **(dict(src.metadata) if isinstance(src.metadata, dict) else {}),
                    "extraction_fragment_id": frag.id,
                },
            },
        )
        body = work.authoritative_text.strip()
        frag_chars = len(body)
        prev_largest = largest
        largest = max(largest, frag_chars)
        initial = _estimate_extract_prompt_tokens(
            source=work,
            topic=topic,
            cluster=cluster,
            extraction_mode=llm_mode,
            max_propositions=limit,
            focus_scopes=scopes,
            prompt_source_text=body,
            fragment_locator_hint=None,
        )
        large_fragments.append(
            {
                "source_id": work.id,
                "title": work.title,
                "locator": frag.locator,
                "chars": frag_chars,
                "estimated_input_tokens": initial,
                "over_budget": initial > max_input,
            }
        )
        if (
            frag_chars > prev_largest
            or (frag_chars == prev_largest and initial > largest_fragment_estimated_input_tokens)
            or largest_fragment_source_id is None
        ):
            largest_fragment_source_id = work.id
            largest_fragment_title = work.title
            largest_fragment_locator = frag.locator
            largest_fragment_estimated_input_tokens = initial
        max_tok = max(max_tok, initial)
        if initial <= max_input:
            chunks = 1
            estimated_input_tokens_total += initial
            source_row = source_totals.setdefault(
                work.id,
                {
                    "source_id": work.id,
                    "title": work.title,
                    "estimated_input_tokens_total": 0,
                    "estimated_llm_invocations": 0,
                },
            )
            source_row["estimated_input_tokens_total"] += int(initial)
            source_row["estimated_llm_invocations"] += 1
        else:
            max_body_chars = _max_body_chars_for_extract_budget(
                source=work,
                topic=topic,
                cluster=cluster,
                extraction_mode=llm_mode,
                max_propositions=limit,
                focus_scopes=scopes,
                token_budget=max_input,
            )
            planned = _plan_llm_text_chunks(
                work,
                max_body_chars=max_body_chars,
                overlap_chars=overlap,
            )
            chunks = max(1, len(planned))
            for ch in planned:
                est = _estimate_extract_prompt_tokens(
                    source=work,
                    topic=topic,
                    cluster=cluster,
                    extraction_mode=llm_mode,
                    max_propositions=limit,
                    focus_scopes=scopes,
                    prompt_source_text=ch.text,
                    fragment_locator_hint=None,
                )
                max_tok = max(max_tok, est)
                estimated_input_tokens_total += est
                source_row = source_totals.setdefault(
                    work.id,
                    {
                        "source_id": work.id,
                        "title": work.title,
                        "estimated_input_tokens_total": 0,
                        "estimated_llm_invocations": 0,
                    },
                )
                source_row["estimated_input_tokens_total"] += int(est)
                source_row["estimated_llm_invocations"] += 1
                if est > max_input:
                    over_budget += 1
        total_llm += chunks

    average_estimated_input_tokens_per_call = (
        float(estimated_input_tokens_total) / float(total_llm) if total_llm > 0 else 0.0
    )
    large_fragments_sorted = sorted(
        large_fragments,
        key=lambda row: int(row.get("estimated_input_tokens") or 0),
        reverse=True,
    )
    top_contributing_sources = sorted(
        source_totals.values(),
        key=lambda row: int(row.get("estimated_input_tokens_total") or 0),
        reverse=True,
    )[:5]
    cost_class = _cost_class(
        n_sources=len(ingested.sources),
        n_jobs=total_llm,
        max_tokens=max_tok,
        over_budget_jobs=over_budget,
    )
    recommendations = _build_recommendations(
        max_estimated_input_tokens_per_call=max_tok,
        jobs_over_context_budget=over_budget,
        estimated_llm_invocations=total_llm,
        cost_class=cost_class,
    )
    n_sources = len(ingested.sources)
    return {
        "source_count": n_sources,
        "base_fragment_count": len(ingested.fragments),
        "expanded_fragment_count": len(expanded_frags),
        "estimated_llm_invocations": total_llm,
        "max_estimated_input_tokens_per_call": max_tok,
        "jobs_over_context_budget": over_budget,
        "largest_fragment_source_id": largest_fragment_source_id,
        "largest_fragment_title": largest_fragment_title,
        "largest_fragment_locator": largest_fragment_locator,
        "largest_fragment_chars": largest,
        "largest_fragment_estimated_input_tokens": largest_fragment_estimated_input_tokens,
        "estimated_input_tokens_total": estimated_input_tokens_total,
        "average_estimated_input_tokens_per_call": average_estimated_input_tokens_per_call,
        "top_large_fragments": large_fragments_sorted[:5],
        "top_contributing_sources": top_contributing_sources,
        "recommendations": recommendations,
        "configured_max_extract_input_tokens": max_input,
        "cost_class": cost_class,
        "mode": "offline_synthetic" if offline_chars_per_instrument else "ingest_and_plan_chunks",
    }


def _scopes_and_limit(case_data: dict[str, Any]) -> tuple[list[str], int]:
    raw = case_data.get("extraction")
    cx = raw if isinstance(raw, dict) else {}
    scopes_raw = cx.get("focus_scopes")
    scopes: list[str] = []
    if isinstance(scopes_raw, list):
        scopes = [str(s).strip() for s in scopes_raw if str(s).strip()]
    max_p = cx.get("max_propositions_per_source")
    limit = 8
    if isinstance(max_p, int) and max_p > 0:
        limit = max_p
    elif isinstance(max_p, str) and max_p.strip().isdigit():
        v = int(max_p.strip())
        if v > 0:
            limit = v
    return scopes, limit


def _record_by_id(records: list[SourceRecord], rid: str) -> SourceRecord:
    for r in records:
        if r.id == rid:
            return r
    raise KeyError(rid)
