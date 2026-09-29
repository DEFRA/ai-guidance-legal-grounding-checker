"""Three-way reconciliation for a production Matcher rerun.

Compares a new native Matcher run against:
  A. historic Beatrice (raw Matcher)
  B. Anna adjudicated output (comparison baseline only)
  C. acceptance-only derived copy

Does not apply adjudications or mutate any run.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from proposition_matcher.matching.match_summary import (
    REPORTABLE_RELATIONSHIPS,
    is_reportable_relationship,
    law_proposition_id,
)
from proposition_matcher.matching.models import RELATIONSHIP_TYPES
from proposition_matcher.pipeline.validate_native_run import load_results

AdjudicationPortability = Literal[
    "UNCHANGED_PAIR_PRESENT",
    "PAIR_PRESENT_RELATIONSHIP_DIFFERS",
    "OLD_PAIR_NOT_PRESENT",
    "NEW_TOP_PAIR_DIFFERS",
    "GUIDANCE_PROPOSITION_MISSING",
]

AdjudicationStrategy = Literal[
    "FULL_ADJUDICATOR_RERUN_REQUIRED",
    "PAIRWISE_ADJUDICATION_RECONCILIATION_POSSIBLE",
    "NO_ADJUDICATION_REQUIRED",
]


def _by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["id"]): r for r in rows if r.get("id")}


def _pair_map(row: dict[str, Any]) -> dict[str, str]:
    """law_id -> relationship for matches in a guidance row."""
    out: dict[str, str] = {}
    for m in row.get("matches") or []:
        lid = law_proposition_id(m)
        if lid:
            out[lid] = str(m.get("relationship") or "")
    return out


def _top_pair(row: dict[str, Any]) -> tuple[str | None, str | None]:
    matches = row.get("matches") or []
    if not matches:
        return None, None
    lid = law_proposition_id(matches[0])
    return lid, str(matches[0].get("relationship") or "") if lid else (None, None)


def _processing_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    c: Counter[str] = Counter()
    native = 0
    for r in rows:
        mp = r.get("match_processing")
        if isinstance(mp, dict) and "classification" in mp:
            native += 1
            c[str(mp["classification"])] += 1
    return {
        "native_processing_records": native,
        "complete": c.get("complete", 0),
        "failed": c.get("failed", 0),
        "partial": c.get("partial", 0),
        "not_attempted": c.get("not_attempted", 0),
    }


def _run_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    proc = _processing_counts(rows)
    rel: Counter[str] = Counter()
    pair_rows = 0
    distinct_pairs: set[tuple[str, str]] = set()
    zero_survivors = 0
    multi_hit = 0
    only_ungrounded = 0
    reportable_pairs = 0
    empty_matches = 0

    for r in rows:
        gid = str(r.get("id") or "")
        matches = r.get("matches") or []
        mp = r.get("match_processing") if isinstance(r.get("match_processing"), dict) else {}
        cand = mp.get("candidate_count")
        if cand == 0:
            zero_survivors += 1
        elif cand is None and not matches:
            # historic: empty matches is not authoritative zero-survivors
            pass
        if not matches:
            empty_matches += 1
        reportable_in_row = 0
        ungrounded_in_row = 0
        for m in matches:
            pair_rows += 1
            lid = law_proposition_id(m)
            rel_name = str(m.get("relationship") or "")
            rel[rel_name] += 1
            if lid:
                distinct_pairs.add((gid, lid))
            if is_reportable_relationship(rel_name):
                reportable_pairs += 1
                reportable_in_row += 1
            elif rel_name == "UNGROUNDED":
                ungrounded_in_row += 1
        if reportable_in_row >= 2:
            multi_hit += 1
        if matches and reportable_in_row == 0 and ungrounded_in_row == len(matches):
            only_ungrounded += 1

    return {
        "guidance_propositions": len(rows),
        **proc,
        "zero_survivors": zero_survivors,
        "empty_matches_rows": empty_matches,
        "pair_rows": pair_rows,
        "distinct_pairs": len(distinct_pairs),
        "multi_hit_guidance_propositions": multi_hit,
        "only_ungrounded_guidance_propositions": only_ungrounded,
        "reportable_pair_rows": reportable_pairs,
        "relationship_distribution": {k: rel[k] for k in RELATIONSHIP_TYPES},
        "unknown_relationships": {
            k: v for k, v in rel.items() if k not in RELATIONSHIP_TYPES
        },
    }


def compare_pair_churn(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
) -> dict[str, Any]:
    base = _by_id(baseline)
    cand = _by_id(candidate)
    base_pairs: set[tuple[str, str]] = set()
    cand_pairs: set[tuple[str, str]] = set()
    base_rel: dict[tuple[str, str], str] = {}
    cand_rel: dict[tuple[str, str], str] = {}
    changed_top: list[dict[str, Any]] = []
    same_pair_rel_changed: list[dict[str, Any]] = []

    for gid, row in base.items():
        for lid, rel in _pair_map(row).items():
            base_pairs.add((gid, lid))
            base_rel[(gid, lid)] = rel
    for gid, row in cand.items():
        for lid, rel in _pair_map(row).items():
            cand_pairs.add((gid, lid))
            cand_rel[(gid, lid)] = rel

    unchanged = base_pairs & cand_pairs
    new_pairs = cand_pairs - base_pairs
    removed_pairs = base_pairs - cand_pairs

    for gid in sorted(set(base) & set(cand)):
        b_top, b_rel = _top_pair(base[gid])
        c_top, c_rel = _top_pair(cand[gid])
        if b_top != c_top:
            changed_top.append(
                {
                    "guidance_proposition_id": gid,
                    "historic_top_law_id": b_top,
                    "historic_top_relationship": b_rel,
                    "new_top_law_id": c_top,
                    "new_top_relationship": c_rel,
                }
            )
        for lid in set(_pair_map(base[gid])) & set(_pair_map(cand[gid])):
            if base_rel[(gid, lid)] != cand_rel[(gid, lid)]:
                same_pair_rel_changed.append(
                    {
                        "guidance_proposition_id": gid,
                        "law_proposition_id": lid,
                        "historic_relationship": base_rel[(gid, lid)],
                        "new_relationship": cand_rel[(gid, lid)],
                    }
                )

    return {
        "unchanged_distinct_pairs": len(unchanged),
        "new_pairs": len(new_pairs),
        "removed_pairs": len(removed_pairs),
        "same_pair_relationship_changed": len(same_pair_rel_changed),
        "changed_top_pairs": len(changed_top),
        "new_pair_samples": [
            {"guidance_proposition_id": g, "law_proposition_id": l}
            for g, l in sorted(new_pairs)[:50]
        ],
        "removed_pair_samples": [
            {"guidance_proposition_id": g, "law_proposition_id": l}
            for g, l in sorted(removed_pairs)[:50]
        ],
        "same_pair_relationship_changed_samples": same_pair_rel_changed[:50],
        "changed_top_pair_samples": changed_top[:50],
    }


def classify_anna_portability(
    anna_rows: list[dict[str, Any]],
    beatrice_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify each historically adjudicated top-pair change vs new Matcher output.

    Anna is treated as adjudicated baseline; new run is raw Matcher output.
    """
    anna = _by_id(anna_rows)
    beatrice = _by_id(beatrice_rows)
    new = _by_id(new_rows)

    # Historic adjudications = rows where Anna top relationship differs from Beatrice.
    adjudicated: list[dict[str, Any]] = []
    for gid, a_row in anna.items():
        b_row = beatrice.get(gid)
        if b_row is None:
            continue
        a_top, a_rel = _top_pair(a_row)
        b_top, b_rel = _top_pair(b_row)
        if a_top is None:
            continue
        if a_top != b_top or a_rel != b_rel:
            adjudicated.append(
                {
                    "guidance_proposition_id": gid,
                    "law_proposition_id": a_top,
                    "beatrice_relationship": b_rel if a_top == b_top else None,
                    "anna_relationship": a_rel,
                    "historic_rank": 0,
                }
            )

    classes: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    safe_to_review: list[dict[str, Any]] = []
    pair_disappeared: list[dict[str, Any]] = []
    different_rank: list[dict[str, Any]] = []
    already_agrees: list[dict[str, Any]] = []
    would_change_different_pair: list[dict[str, Any]] = []
    fresh_needed: list[str] = []

    for adj in adjudicated:
        gid = adj["guidance_proposition_id"]
        old_law = adj["law_proposition_id"]
        anna_rel = adj["anna_relationship"]
        n_row = new.get(gid)
        if n_row is None:
            label: AdjudicationPortability = "GUIDANCE_PROPOSITION_MISSING"
            classes[label] += 1
            details.append({**adj, "portability": label})
            fresh_needed.append(gid)
            continue

        n_pairs = _pair_map(n_row)
        n_top, n_rel = _top_pair(n_row)
        n_matches = n_row.get("matches") or []
        rank = next(
            (
                i
                for i, m in enumerate(n_matches)
                if law_proposition_id(m) == old_law
            ),
            None,
        )

        if old_law not in n_pairs:
            label = "OLD_PAIR_NOT_PRESENT"
            classes[label] += 1
            pair_disappeared.append(adj)
            fresh_needed.append(gid)
        elif n_pairs[old_law] != anna_rel:
            label = "PAIR_PRESENT_RELATIONSHIP_DIFFERS"
            classes[label] += 1
            if rank == 0:
                safe_to_review.append({**adj, "new_relationship": n_pairs[old_law], "new_rank": 0})
            else:
                different_rank.append({**adj, "new_relationship": n_pairs[old_law], "new_rank": rank})
                would_change_different_pair.append(
                    {
                        **adj,
                        "new_top_law_id": n_top,
                        "new_top_relationship": n_rel,
                        "adjudicated_pair_new_rank": rank,
                    }
                )
            fresh_needed.append(gid)
        else:
            # Exact pair present with Anna's relationship already.
            if n_top != old_law:
                label = "NEW_TOP_PAIR_DIFFERS"
                classes[label] += 1
                different_rank.append({**adj, "new_relationship": n_pairs[old_law], "new_rank": rank})
                would_change_different_pair.append(
                    {
                        **adj,
                        "new_top_law_id": n_top,
                        "new_top_relationship": n_rel,
                        "adjudicated_pair_new_rank": rank,
                        "note": "Anna relationship already present on non-top pair",
                    }
                )
            else:
                label = "UNCHANGED_PAIR_PRESENT"
                classes[label] += 1
                already_agrees.append(adj)
                safe_to_review.append({**adj, "new_relationship": n_pairs[old_law], "new_rank": 0})
            # still may need review of other churn; not auto-apply
        details.append({**adj, "portability": label, "new_top_law_id": n_top, "new_rank": rank})

    # Propositions whose new top has no historic Anna adjudication on that pair
    new_tops_without_adj: list[dict[str, Any]] = []
    adj_pair_keys = {(a["guidance_proposition_id"], a["law_proposition_id"]) for a in adjudicated}
    for gid, n_row in new.items():
        n_top, n_rel = _top_pair(n_row)
        if n_top is None:
            continue
        if (gid, n_top) not in adj_pair_keys:
            # only flag when historic Anna had a different adjudication on this GP
            if any(a["guidance_proposition_id"] == gid for a in adjudicated):
                new_tops_without_adj.append(
                    {
                        "guidance_proposition_id": gid,
                        "new_top_law_id": n_top,
                        "new_top_relationship": n_rel,
                    }
                )

    return {
        "historic_adjudications_count": len(adjudicated),
        "portability_counts": dict(classes),
        "safe_to_review_same_pair": safe_to_review,
        "pair_disappeared": pair_disappeared,
        "adjudication_now_non_top": different_rank,
        "raw_matcher_already_agrees_with_anna": already_agrees,
        "blind_copy_would_change_different_pair": would_change_different_pair,
        "new_top_pairs_without_historic_adjudication": new_tops_without_adj[:50],
        "propositions_needing_fresh_adjudication": sorted(set(fresh_needed)),
        "details": details,
    }


def recommend_strategy(
    *,
    churn: dict[str, Any],
    portability: dict[str, Any],
    validation_ready: bool,
) -> tuple[AdjudicationStrategy, list[str]]:
    reasons: list[str] = []
    if not validation_ready:
        reasons.append("native run is not ready for adjudication (incomplete processing)")
        return "FULL_ADJUDICATOR_RERUN_REQUIRED", reasons

    removed = churn["removed_pairs"]
    new = churn["new_pairs"]
    top_changed = churn["changed_top_pairs"]
    rel_changed = churn["same_pair_relationship_changed"]
    disappeared = len(portability["pair_disappeared"])
    adj_n = portability["historic_adjudications_count"]

    # Material churn thresholds — evidence-based, not cosmetic similarity.
    material = (
        top_changed >= max(10, adj_n)  # top-pair churn at/above adjudication volume
        or removed >= 100
        or new >= 100
        or disappeared >= max(5, adj_n // 2)
    )
    if material:
        reasons.append(
            f"material pair/top churn: new={new}, removed={removed}, "
            f"changed_top={top_changed}, anna_pairs_disappeared={disappeared}"
        )
        return "FULL_ADJUDICATOR_RERUN_REQUIRED", reasons

    joinable = (
        adj_n > 0
        and disappeared < adj_n
        and (portability["portability_counts"].get("UNCHANGED_PAIR_PRESENT", 0)
             + portability["portability_counts"].get("PAIR_PRESENT_RELATIONSHIP_DIFFERS", 0)
             + portability["portability_counts"].get("NEW_TOP_PAIR_DIFFERS", 0))
        >= 1
    )
    if joinable and (new > 0 or removed > 0 or top_changed > 0 or rel_changed > 0):
        reasons.append(
            "historic Anna adjudications can be joined by exact (guidance, law) pair; "
            f"isolate fresh work for new/removed/changed-top "
            f"(new={new}, removed={removed}, changed_top={top_changed}, "
            f"same_pair_rel_changed={rel_changed})"
        )
        return "PAIRWISE_ADJUDICATION_RECONCILIATION_POSSIBLE", reasons

    if new == 0 and removed == 0 and top_changed == 0 and rel_changed == 0 and adj_n == 0:
        reasons.append("byte-identical pair set with no historic adjudications — unlikely")
        return "NO_ADJUDICATION_REQUIRED", reasons

    # Default: pairwise when join keys exist; otherwise full rerun.
    if adj_n and disappeared == 0:
        reasons.append(
            "all historic adjudicated pairs still present; reconcile pairwise and "
            "fresh-adjudicate residual churn"
        )
        return "PAIRWISE_ADJUDICATION_RECONCILIATION_POSSIBLE", reasons

    reasons.append("insufficient join confidence for pairwise reconciliation")
    return "FULL_ADJUDICATOR_RERUN_REQUIRED", reasons


def build_reconciliation(
    *,
    new_rows: list[dict[str, Any]],
    beatrice_rows: list[dict[str, Any]],
    anna_rows: list[dict[str, Any]],
    acceptance_rows: list[dict[str, Any]],
    validation: dict[str, Any] | None = None,
    paths: dict[str, str] | None = None,
    run_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    new_m = _run_metrics(new_rows)
    hist_m = _run_metrics(beatrice_rows)
    anna_m = _run_metrics(anna_rows)
    acc_m = _run_metrics(acceptance_rows)
    churn = compare_pair_churn(beatrice_rows, new_rows)
    portability = classify_anna_portability(anna_rows, beatrice_rows, new_rows)
    ready = bool(validation and validation.get("ready_for_adjudication"))
    strategy, reasons = recommend_strategy(
        churn=churn, portability=portability, validation_ready=ready
    )

    # Acceptance vs native processing deltas
    acc_by = _by_id(acceptance_rows)
    new_by = _by_id(new_rows)
    cand_diff = 0
    cand_diff_samples: list[dict[str, Any]] = []
    for gid, n_row in new_by.items():
        a_row = acc_by.get(gid)
        if not a_row:
            continue
        n_mp = n_row.get("match_processing") or {}
        a_mp = a_row.get("match_processing") or {}
        if n_mp.get("candidate_count") != a_mp.get("candidate_count"):
            cand_diff += 1
            if len(cand_diff_samples) < 30:
                cand_diff_samples.append(
                    {
                        "guidance_proposition_id": gid,
                        "acceptance_candidate_count": a_mp.get("candidate_count"),
                        "native_candidate_count": n_mp.get("candidate_count"),
                    }
                )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "paths": paths or {},
        "run_meta": run_meta or {},
        "validation": validation,
        "run_summary": {
            "historic_beatrice": hist_m,
            "anna_adjudicated": anna_m,
            "acceptance_derived": acc_m,
            "new_matcher": new_m,
        },
        "pair_churn_historic_vs_new": churn,
        "adjudication_portability_anna_vs_new": portability,
        "acceptance_vs_native_processing": {
            "note": (
                "Acceptance copy reconstructed candidate_count from distinct law IDs "
                "in matches[] and forced classification=complete. It is not "
                "authoritative production Matcher evidence."
            ),
            "guidance_propositions_acceptance": acc_m["guidance_propositions"],
            "guidance_propositions_new": new_m["guidance_propositions"],
            "native_processing_records_new": new_m["native_processing_records"],
            "reconstructed_processing_records_acceptance": acc_m["native_processing_records"],
            "candidate_count_differences": cand_diff,
            "candidate_count_difference_samples": cand_diff_samples,
            "only_ungrounded_acceptance": acc_m["only_ungrounded_guidance_propositions"],
            "only_ungrounded_new": new_m["only_ungrounded_guidance_propositions"],
            "zero_survivors_acceptance": acc_m["zero_survivors"],
            "zero_survivors_new": new_m["zero_survivors"],
            "reportable_pairs_acceptance": acc_m["reportable_pair_rows"],
            "reportable_pairs_new": new_m["reportable_pair_rows"],
            "multi_hit_acceptance": acc_m["multi_hit_guidance_propositions"],
            "multi_hit_new": new_m["multi_hit_guidance_propositions"],
            "relationship_distribution_acceptance": acc_m["relationship_distribution"],
            "relationship_distribution_new": new_m["relationship_distribution"],
        },
        "recommendation": {
            "strategy": strategy,
            "reasons": reasons,
            "reportable_relationships": sorted(REPORTABLE_RELATIONSHIPS),
        },
    }


def render_markdown_report(data: dict[str, Any]) -> str:
    rs = data["run_summary"]
    labels = (
        ("historic_beatrice", "Historic Beatrice"),
        ("anna_adjudicated", "Anna adjudicated"),
        ("acceptance_derived", "Acceptance-derived"),
        ("new_matcher", "New Matcher"),
    )

    def cell(metric: str) -> str:
        return " | ".join(str(rs[key].get(metric, "")) for key, _ in labels)

    churn = data["pair_churn_historic_vs_new"]
    port = data["adjudication_portability_anna_vs_new"]
    acc = data["acceptance_vs_native_processing"]
    rec = data["recommendation"]
    val = data.get("validation") or {}

    rel_rows = []
    for rel in RELATIONSHIP_TYPES:
        vals = " | ".join(str(rs[k]["relationship_distribution"].get(rel, 0)) for k, _ in labels)
        rel_rows.append(f"| {rel} | {vals} |")

    lines = [
        "# Matcher rerun reconciliation — ssafo-nitrates",
        "",
        f"Generated: `{data.get('generated_at')}`",
        "",
        "## Paths",
        "",
    ]
    for k, v in (data.get("paths") or {}).items():
        lines.append(f"- **{k}:** `{v}`")
    lines += [
        "",
        "## Validation gate",
        "",
        f"- ok: `{val.get('ok')}`",
        f"- ready_for_adjudication: `{val.get('ready_for_adjudication')}`",
        f"- classifications: `{val.get('classification_counts')}`",
        f"- candidate_count mismatches: `{len(val.get('candidate_count_mismatches') or [])}`",
        "",
        "## Run summary",
        "",
        "| Metric | Historic Beatrice | Anna adjudicated | Acceptance-derived | New Matcher |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| Guidance propositions | {cell('guidance_propositions')} |",
        f"| Native processing records | {cell('native_processing_records')} |",
        f"| Complete | {cell('complete')} |",
        f"| Failed | {cell('failed')} |",
        f"| Partial | {cell('partial')} |",
        f"| Not attempted | {cell('not_attempted')} |",
        f"| Zero survivors | {cell('zero_survivors')} |",
        f"| Empty matches[] rows | {cell('empty_matches_rows')} |",
        f"| Pair rows | {cell('pair_rows')} |",
        f"| Distinct pairs | {cell('distinct_pairs')} |",
        f"| Multi-hit guidance propositions | {cell('multi_hit_guidance_propositions')} |",
        f"| Only-ungrounded guidance propositions | {cell('only_ungrounded_guidance_propositions')} |",
        f"| Reportable pair rows | {cell('reportable_pair_rows')} |",
        "",
        "## Relationship distribution",
        "",
        "| Relationship | Historic Beatrice | Anna adjudicated | Acceptance-derived | New Matcher |",
        "| --- | ---: | ---: | ---: | ---: |",
        *rel_rows,
        "",
        "## A. Historic Beatrice vs new Matcher — pair churn",
        "",
        f"- Unchanged distinct pairs: **{churn['unchanged_distinct_pairs']}**",
        f"- New pairs: **{churn['new_pairs']}**",
        f"- Removed pairs: **{churn['removed_pairs']}**",
        f"- Same pair, changed raw relationship: **{churn['same_pair_relationship_changed']}**",
        f"- Changed top pairs: **{churn['changed_top_pairs']}**",
        "",
        "## B. Anna adjudicated vs new Matcher — portability",
        "",
        "Anna is adjudicated; the new run is raw Matcher output. "
        "**Do not treat portability as auto-apply permission.**",
        "",
        f"- Historic adjudications (Anna≠Beatrice top): **{port['historic_adjudications_count']}**",
        f"- Portability counts: `{port['portability_counts']}`",
        f"- Safe to review on same pair: **{len(port['safe_to_review_same_pair'])}**",
        f"- Historic adjudicated pair disappeared: **{len(port['pair_disappeared'])}**",
        f"- Adjudication now non-top / would hit different rank: "
        f"**{len(port['adjudication_now_non_top'])}**",
        f"- Raw Matcher already agrees with Anna on adjudicated pair: "
        f"**{len(port['raw_matcher_already_agrees_with_anna'])}**",
        f"- Blind copy would change a different pair: "
        f"**{len(port['blind_copy_would_change_different_pair'])}**",
        f"- Propositions needing fresh adjudication: "
        f"**{len(port['propositions_needing_fresh_adjudication'])}**",
        "",
        "## C. Acceptance-only derived vs new Matcher",
        "",
        acc["note"],
        "",
        f"- Candidate-count differences: **{acc['candidate_count_differences']}**",
        f"- Only-ungrounded: acceptance={acc['only_ungrounded_acceptance']}, "
        f"new={acc['only_ungrounded_new']}",
        f"- Zero survivors: acceptance={acc['zero_survivors_acceptance']}, "
        f"new={acc['zero_survivors_new']}",
        f"- Reportable pairs: acceptance={acc['reportable_pairs_acceptance']}, "
        f"new={acc['reportable_pairs_new']}",
        f"- Multi-hit guidance: acceptance={acc['multi_hit_acceptance']}, "
        f"new={acc['multi_hit_new']}",
        "",
        "## Adjudication recommendation",
        "",
        f"**{rec['strategy']}**",
        "",
        "Reasons:",
    ]
    for reason in rec["reasons"]:
        lines.append(f"- {reason}")
    lines += [
        "",
        "This increment does not implement the recommendation.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Reconcile a Matcher rerun against baselines.")
    ap.add_argument("--new-run", type=Path, required=True)
    ap.add_argument("--beatrice", type=Path, required=True, help="Historic Beatrice results.json or run dir")
    ap.add_argument("--anna", type=Path, required=True, help="Anna results.json or run dir")
    ap.add_argument("--acceptance", type=Path, required=True, help="Acceptance results.json or run dir")
    ap.add_argument("--validation-json", type=Path, help="Optional validate-native-run JSON")
    args = ap.parse_args(argv)

    def resolve(p: Path) -> Path:
        return p / "results.json" if p.is_dir() else p

    new_rows = load_results(resolve(args.new_run))
    beatrice_rows = load_results(resolve(args.beatrice))
    anna_rows = load_results(resolve(args.anna))
    acceptance_rows = load_results(resolve(args.acceptance))
    validation = json.loads(args.validation_json.read_text()) if args.validation_json else None

    out_dir = args.new_run if args.new_run.is_dir() else args.new_run.parent
    data = build_reconciliation(
        new_rows=new_rows,
        beatrice_rows=beatrice_rows,
        anna_rows=anna_rows,
        acceptance_rows=acceptance_rows,
        validation=validation,
        paths={
            "new_run": str(args.new_run),
            "beatrice": str(resolve(args.beatrice)),
            "anna": str(resolve(args.anna)),
            "acceptance": str(resolve(args.acceptance)),
        },
    )
    json_path = out_dir / "matcher-rerun-reconciliation.json"
    md_path = out_dir / "MATCHER-RERUN-REPORT.md"
    json_path.write_text(json.dumps(data, indent=2))
    md_path.write_text(render_markdown_report(data))
    print(f"wrote {json_path}", flush=True)
    print(f"wrote {md_path}", flush=True)
    print(f"recommendation: {data['recommendation']['strategy']}", flush=True)


if __name__ == "__main__":
    main()
