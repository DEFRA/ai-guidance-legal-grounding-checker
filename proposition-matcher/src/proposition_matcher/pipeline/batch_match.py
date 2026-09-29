"""Proposition Matcher batch matching runner (phase 2 of Guidance Relevance Filter -> Guidance Proposition Extractor -> Proposition Matcher).

Reads a Guidance Proposition Extractor run (guidance) and a Law Proposition Extractor export (law) BY PATH, embeds + retrieves
locally (Ollama), then group-reranks each guidance proposition via the Anthropic
Message Batches API (50% cost, async): a SINGLE request per guidance proposition
sees all of its surviving law candidates and labels each one. Records exact
tokens, cost, and wall-clock time into ``MODEL.md`` (human) and ``metrics.json``
(machine).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

from proposition_matcher.matching.embeddings import find_candidates
from proposition_matcher.matching.match_summary import (
    build_match_processing,
    classify_processing,
    summarise_guidance_proposition_match,
)
from proposition_matcher.matching.prompts import (
    GROUP_RERANK_SYSTEM,
    LABEL_PRIORITY,
    SUMMARISE_SYSTEM,
    build_group_rerank_prompt,
    build_summarise_prompt,
    law_citation,
    parse_group_rerank_json,
)

from .law_loading import law_display_text, load_law_units
from .mapping import guidance_from_guidance_proposition_extractor_output


def _producer_fields() -> dict:
    return {
        "producer_component": "proposition-matcher",
        "source_kind": "pipeline",
        "component_id": "proposition-matcher",
    }


# Per-1M-token rates (input, output), full price; the Batch API bills at 0.5x.
RATES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
BATCH_DISCOUNT = 0.5
CLASSIFY_MAX_TOKENS = 2048
SUMMARISE_MAX_TOKENS = 512

# Retrieval geometry — fixed across the whole benchmark ladder (alice-omar →
# harvey-iris); the winning candidate never varied these, so they are config,
# not knobs.
TOP_K = 15            # hard cap on survivors per guidance proposition
THRESHOLD = 0.65      # minimum cosine similarity for a survivor
SCORE_GAP = 0.04      # adaptive-size window below the top score


# ── local embeddings (Ollama, reuses proposition-matcher's cosine matcher) ─────────────────

def _embed(texts: list[str], base_url: str, model: str) -> list[list[float]]:
    client = OpenAI(base_url=base_url, api_key="ollama", max_retries=3, timeout=120)
    out: list[list[float]] = []
    for i in range(0, len(texts), 128):
        resp = client.embeddings.create(model=model, input=texts[i : i + 128])
        out.extend(d.embedding for d in sorted(resp.data, key=lambda x: x.index))
    return out


# ── batch helper ────────────────────────────────────────────────────────────────

def _collect_batch_results(client, batch_id: str, label: str):
    """Download results from a completed batch. Returns (id, {custom_id: message},
    usage totals, errored count)."""
    messages: dict = {}
    usage = {"input": 0, "output": 0, "cache_read": 0}
    errored = 0
    for r in client.messages.batches.results(batch_id):
        if r.result.type != "succeeded":
            errored += 1
            continue
        msg = r.result.message
        usage["input"] += msg.usage.input_tokens
        usage["output"] += msg.usage.output_tokens
        usage["cache_read"] += getattr(msg.usage, "cache_read_input_tokens", 0) or 0
        messages[r.custom_id] = msg
    print(f"[{label}] fetched {batch_id}: ok={len(messages)} err={errored}", flush=True)
    return batch_id, messages, usage, errored


def _submit_and_collect(client, requests, poll_seconds: int, label: str):
    """Submit one batch, poll to completion, return (id, {custom_id: message},
    usage totals, errored count, wall-clock seconds)."""
    t0 = time.time()
    batch = client.messages.batches.create(requests=requests)
    print(f"[{label}] submitted {batch.id} ({len(requests)} requests)", flush=True)
    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        c = b.request_counts
        print(f"[{label}] {b.processing_status}: proc={c.processing} ok={c.succeeded} err={c.errored}", flush=True)
        time.sleep(poll_seconds)

    batch_id, messages, usage, errored = _collect_batch_results(client, batch.id, label)
    return batch_id, messages, usage, errored, time.time() - t0


def _text(message) -> str:
    return next((b.text for b in message.content if getattr(b, "type", None) == "text"), "")


def _cost(usage: dict, model: str) -> float:
    rin, rout = RATES.get(model, RATES["claude-sonnet-4-6"])
    billable_in = usage["input"] + usage["cache_read"] * 0.1
    return (billable_in / 1e6 * rin + usage["output"] / 1e6 * rout) * BATCH_DISCOUNT


# ── CSV (mirrors the explorer export) ────────────────────────────────────────────

CSV_HEADERS = [
    "URL", "Guidance Proposition", "Summary", "Law Proposition", "Law Citation",
    "Relationship", "Explanation", "Confidence", "Correctness Score",
]


def _write_csv(records: list[dict], path: Path) -> None:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_HEADERS)
        for rec in records:
            url, gp_text, summary = rec["url"], rec["proposition_text"], rec.get("summary", "")
            if not rec["matches"]:
                w.writerow([url, gp_text, summary, "", "", "", "", "", ""])
            for m in rec["matches"]:
                lp = m["law_proposition"]
                w.writerow([
                    url, gp_text, summary, law_display_text(lp), law_citation(lp),
                    m["relationship"], m["explanation"], m["confidence"], f"{m['correctness_score']:.2f}",
                ])


def main() -> None:
    ap = argparse.ArgumentParser(description="Proposition Matcher batch matching: Guidance Proposition Extractor guidance vs Law Proposition Extractor law (group-rerank).")
    ap.add_argument("--guidance", type=Path, required=True, help="Guidance Proposition Extractor run output.json")
    ap.add_argument(
        "--law",
        type=Path,
        required=True,
        help="Law Proposition Extractor propositions.json or proposition_matcher_law_candidates.json",
    )
    ap.add_argument(
        "--law-source",
        choices=("auto", "propositions", "candidates"),
        default="auto",
        help="How to interpret --law (default: auto-detect from JSON shape).",
    )
    ap.add_argument("--out", type=Path, required=True, help="Output run directory")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--embed-base-url", default=os.getenv("EMBED_BASE_URL", "http://127.0.0.1:11434/v1"))
    ap.add_argument("--embed-model", default=os.getenv("EMBED_MODEL", "nomic-embed-text:v1.5"))
    ap.add_argument("--poll-seconds", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true", help="Embed + retrieve + build requests, but do not submit batches.")
    ap.add_argument(
        "--rerank-batch-id",
        help="Reuse a completed group-rerank batch (skip re-submit; still embeds locally to rebuild survivor mapping).",
    )
    args = ap.parse_args()

    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming as Params
    from anthropic.types.messages.batch_create_params import Request

    args.out.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    # ── load inputs (by path) ───────────────────────────────────────────────────
    g_raw = json.loads(args.guidance.read_text())
    guidance = guidance_from_guidance_proposition_extractor_output(g_raw if isinstance(g_raw, list) else g_raw.get("pages", []))
    law_units, law_source = load_law_units(args.law, source=args.law_source)
    law_by_id = {lu.id: lu for lu in law_units}

    print(
        f"guidance: {len(guidance)} propositions | law: {len(law_units)} units "
        f"(source={law_source})",
        flush=True,
    )

    # ── embed + retrieve (local, timed) ─────────────────────────────────────────
    t_local = time.time()
    law_index = list(zip(
        [lu.id for lu in law_units],
        _embed([lu.embed_text for lu in law_units], args.embed_base_url, args.embed_model),
        strict=False,
    ))
    g_embs = _embed([gp.proposition_text for gp in guidance], args.embed_base_url, args.embed_model)
    survivors_per_gp: list[list[tuple[str, float]]] = []
    for g_emb in g_embs:
        survivors_per_gp.append(
            find_candidates(g_emb, law_index, top_k=TOP_K, threshold=THRESHOLD, score_gap=SCORE_GAP)
        )
    local_seconds = time.time() - t_local

    # One group-rerank request per guidance proposition that has survivors.
    # Propositions with no survivor above the threshold cost no LLM call.
    rerank_reqs = []
    matched_gis = []
    for gi, survivors in enumerate(survivors_per_gp):
        if not survivors:
            continue
        cands = [(law_by_id[law_id], score) for law_id, score in survivors]
        prompt = build_group_rerank_prompt(guidance[gi], cands)
        rerank_reqs.append(
            Request(
                custom_id=f"g-{gi}",
                params=Params(model=args.model, max_tokens=CLASSIFY_MAX_TOKENS, system=GROUP_RERANK_SYSTEM,
                              messages=[{"role": "user", "content": prompt}]),
            )
        )
        matched_gis.append(gi)
    n_producing = len(matched_gis)
    n_empty = len(guidance) - n_producing
    print(f"retrieved: {n_producing} guidance props with survivors ({n_empty} empty, free) | local embed+retrieve {local_seconds:.0f}s", flush=True)

    if args.dry_run:
        print(f"[dry-run] would submit {len(rerank_reqs)} group-rerank requests; stopping before any API spend.")
        return

    client = anthropic.Anthropic()

    # ── group-rerank batch ───────────────────────────────────────────────────────
    if args.rerank_batch_id:
        b = client.messages.batches.retrieve(args.rerank_batch_id)
        if b.processing_status != "ended":
            raise SystemExit(f"rerank batch {args.rerank_batch_id} not ended (status={b.processing_status})")
        cls_id, cls_msgs, cls_usage, cls_err = _collect_batch_results(client, args.rerank_batch_id, "group-rerank")
        cls_secs = 0.0
    else:
        cls_id, cls_msgs, cls_usage, cls_err, cls_secs = _submit_and_collect(client, rerank_reqs, args.poll_seconds, "group-rerank")
    # Per-GP classification rows plus explicit processing evidence so empty
    # matches[] is never mistaken for "no candidates" / "not checked".
    classified: dict[int, list[dict]] = {}
    processing_by_gi: dict[int, dict] = {}
    for gi in matched_gis:
        survivors = survivors_per_gp[gi]
        survivor_ids = {law_id for law_id, _ in survivors}
        sim_by_id = {law_id: score for law_id, score in survivors}
        msg = cls_msgs.get(f"g-{gi}")
        if msg is None:
            classified[gi] = []
            outcome, reason = classify_processing(
                candidate_count=len(survivors),
                classified_law_ids=set(),
                survivor_law_ids=survivor_ids,
                request_succeeded=False,
                parse_succeeded=False,
            )
            processing_by_gi[gi] = build_match_processing(
                candidate_count=len(survivors), classification=outcome, failure_reason=reason,
            )
            continue
        try:
            verdict = parse_group_rerank_json(_text(msg))
        except Exception:
            classified[gi] = []
            outcome, reason = classify_processing(
                candidate_count=len(survivors),
                classified_law_ids=set(),
                survivor_law_ids=survivor_ids,
                request_succeeded=True,
                parse_succeeded=False,
            )
            processing_by_gi[gi] = build_match_processing(
                candidate_count=len(survivors), classification=outcome, failure_reason=reason,
            )
            continue
        id_by_suffix = {lid.removeprefix("prop:"): lid for lid in sim_by_id}
        rows = []
        classified_ids: set[str] = set()
        for m in verdict["matches"]:
            raw_id = m["law_id"]
            canonical = raw_id if raw_id in sim_by_id else id_by_suffix.get(raw_id.removeprefix("prop:"), raw_id)
            if canonical not in law_by_id:
                continue
            classified_ids.add(canonical)
            rows.append({
                "law_proposition": law_by_id[canonical].payload,
                "similarity_score": round(float(sim_by_id.get(canonical, 0.0)), 4),
                "relationship": m["relationship"],
                "confidence": m["confidence"],
                "explanation": m["explanation"],
                "correctness_score": m["correctness_score"],
            })
        rows.sort(key=lambda r: LABEL_PRIORITY.get(r["relationship"], 99))
        classified[gi] = rows
        outcome, reason = classify_processing(
            candidate_count=len(survivors),
            classified_law_ids=classified_ids,
            survivor_law_ids=survivor_ids,
            request_succeeded=True,
            parse_succeeded=True,
        )
        processing_by_gi[gi] = build_match_processing(
            candidate_count=len(survivors), classification=outcome, failure_reason=reason,
        )

    # Guidance props with no retrieval survivors: complete assessment, zero candidates.
    for gi, survivors in enumerate(survivors_per_gp):
        if gi in processing_by_gi:
            continue
        processing_by_gi[gi] = build_match_processing(
            candidate_count=len(survivors), classification="complete",
        )

    # ── summarise batch (only gps with matches) ─────────────────────────────────
    summ_reqs = [
        Request(
            custom_id=f"s-{gi}",
            params=Params(model=args.model, max_tokens=SUMMARISE_MAX_TOKENS, system=SUMMARISE_SYSTEM,
                          messages=[{"role": "user", "content": build_summarise_prompt(guidance[gi], rows)}]),
        )
        for gi, rows in classified.items() if rows
    ]
    if summ_reqs:
        summ_id, summ_msgs, summ_usage, summ_err, summ_secs = _submit_and_collect(client, summ_reqs, args.poll_seconds, "summarise")
    else:
        summ_id, summ_msgs, summ_usage, summ_err, summ_secs = None, {}, {"input": 0, "output": 0, "cache_read": 0}, 0, 0.0

    # ── assemble results ────────────────────────────────────────────────────────
    records = []
    match_summaries = []
    for gi, gp in enumerate(guidance):
        matches = classified.get(gi, [])
        match_processing = processing_by_gi[gi]
        match_summary = summarise_guidance_proposition_match(
            guidance_proposition_id=gp.id,
            match_processing=match_processing,
            matches=matches,
        )
        records.append({
            "url": gp.source_url,
            "id": gp.id,
            "content_id": gp.content_id,
            "proposition_text": gp.proposition_text,
            "source_paragraphs": gp.source_paragraphs,
            "section_locator": gp.section_locator,
            "law_source": law_source,
            "summary": _text(summ_msgs[f"s-{gi}"]) if f"s-{gi}" in summ_msgs else "",
            "matches": matches,
            # Explicit retrieval/classification evidence — required to distinguish
            # no-candidates / failed / partial / not-checked (see match_summary.py).
            "match_processing": match_processing,
            "match_summary": match_summary,
        })
        match_summaries.append(match_summary)
    (args.out / "results.json").write_text(json.dumps(records, indent=2))
    (args.out / "match_summaries.json").write_text(json.dumps(match_summaries, indent=2))
    _write_csv(records, args.out / "results.csv")

    # ── metrics + model card ────────────────────────────────────────────────────
    cls_cost, summ_cost = _cost(cls_usage, args.model), _cost(summ_usage, args.model)
    total_seconds = local_seconds + cls_secs + summ_secs
    metrics = {
        "model": args.model, "strategy": "group_rerank",
        "top_k": TOP_K, "threshold": THRESHOLD, "score_gap": SCORE_GAP,
        "law_source": law_source,
        "guidance_propositions": len(guidance),
        "law_propositions": len(law_units),  # alias kept for back-compat
        "law_units": len(law_units),
        "guidance_props_with_survivors": n_producing, "guidance_props_empty": n_empty,
        "group_rerank": {"requests": len(rerank_reqs), "errored": cls_err, "batch_id": cls_id, **cls_usage, "cost_usd": round(cls_cost, 4)},
        "summarise": {"requests": len(summ_reqs), "errored": summ_err, "batch_id": summ_id, **summ_usage, "cost_usd": round(summ_cost, 4)},
        "tokens": {"input": cls_usage["input"] + summ_usage["input"], "output": cls_usage["output"] + summ_usage["output"]},
        "cost_usd_total": round(cls_cost + summ_cost, 4),
        "time_seconds": {"local_embed_retrieve": round(local_seconds, 1), "group_rerank_batch": round(cls_secs, 1), "summarise_batch": round(summ_secs, 1), "total": round(total_seconds, 1)},
    }
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    _write_model_card(args.out, metrics, started_at, args.guidance, args.law)

    print(f"\n[done] {len(records)} guidance props | ${metrics['cost_usd_total']} | {total_seconds:.0f}s -> {args.out}", flush=True)
    if cls_err or summ_err:
        print(f"  {cls_err} group-rerank + {summ_err} summarise requests errored", file=sys.stderr)


def _write_model_card(out: Path, m: dict, started_at: str, guidance: Path, law: Path) -> None:
    def mins(s: float) -> str:
        return f"{int(s) // 60}m{int(s) % 60:02d}s"
    t = m["time_seconds"]
    (out / "MODEL.md").write_text(f"""# proposition-matcher run — {out.name}

## Description

Proposition Matcher batch matching run (group-rerank): each Guidance Proposition Extractor guidance proposition is
classified against its surviving Law Proposition Extractor law candidates in a single LLM call, with
a compliance summary per producing proposition. Prompts are shared with the
in-process matcher (`proposition-matcher.matching.prompts`).

## Provenance

- **Guidance (Guidance Proposition Extractor):** `{guidance}`
- **Law (Law Proposition Extractor):** `{law}` (source=`{m['law_source']}`)
- **Model:** Anthropic `{m['model']}` via the Message Batches API (50% cost).
- **Strategy:** group-rerank — local nomic embeddings + cosine retrieval
  (threshold {m['threshold']}, gap {m['score_gap']}, top-{m['top_k']}), then one
  grouped LLM call per guidance proposition.
  Candidates mode embeds `matching_text` and shows `statement_text` to the LLM;
  propositions mode embeds/displays `proposition_text`.

## Started

{started_at}

## Headline

- **Guidance propositions:** {m['guidance_propositions']}
- **Law units:** {m['law_units']} (`{m['law_source']}`)
- **Guidance props with survivors (LLM calls):** {m['guidance_props_with_survivors']}
- **Guidance props empty (no candidate, free):** {m['guidance_props_empty']}

## Cost & runtime

- **Tokens:** {m['tokens']['input']:,} in / {m['tokens']['output']:,} out
- **Cost:** **${m['cost_usd_total']}** total — group-rerank ${m['group_rerank']['cost_usd']}, summarise ${m['summarise']['cost_usd']} (batch-discounted)
- **Time (wall-clock):**
  - local (embed + retrieve): {mins(t['local_embed_retrieve'])}
  - group-rerank batch (submit → ended, incl. queue wait): {mins(t['group_rerank_batch'])}
  - summarise batch (incl. queue wait): {mins(t['summarise_batch'])}
  - **total: {mins(t['total'])}**

Full machine-readable breakdown in `metrics.json`.
""")


if __name__ == "__main__":
    main()
