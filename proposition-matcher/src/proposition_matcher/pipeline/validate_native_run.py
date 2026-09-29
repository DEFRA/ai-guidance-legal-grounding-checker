"""Validate a native Proposition Matcher run (post-``run`` gate).

Checks scope completeness, schema-valid ``match_processing``, candidate-count
agreement with recomputed retrieval survivors, pair identity, and relationship
vocabulary. Does not mutate the run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from openai import OpenAI

from proposition_matcher.matching.embeddings import find_candidates
from proposition_matcher.matching.historic_match_processing import validate_match_processing
from proposition_matcher.matching.match_summary import law_proposition_id
from proposition_matcher.matching.models import RELATIONSHIP_TYPES
from proposition_matcher.pipeline.batch_match import SCORE_GAP, THRESHOLD, TOP_K
from proposition_matcher.pipeline.law_loading import load_law_units
from proposition_matcher.pipeline.mapping import guidance_from_guidance_proposition_extractor_output

VALID_CLASSIFICATIONS = frozenset({"complete", "failed", "partial", "not_attempted"})


def _embed(texts: list[str], base_url: str, model: str) -> list[list[float]]:
    client = OpenAI(base_url=base_url, api_key="ollama", max_retries=3, timeout=120)
    out: list[list[float]] = []
    for i in range(0, len(texts), 128):
        resp = client.embeddings.create(model=model, input=texts[i : i + 128])
        out.extend(d.embedding for d in sorted(resp.data, key=lambda x: x.index))
    return out


def load_results(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text())
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("results"), list):
        return raw["results"]
    raise ValueError(f"unrecognised results shape at {path}")


def recompute_survivor_counts(
    *,
    guidance_path: Path,
    law_path: Path,
    law_source: str = "auto",
    embed_base_url: str | None = None,
    embed_model: str | None = None,
) -> dict[str, int]:
    """Re-run local retrieval; return ``{guidance_id: survivor_count}``."""
    base_url = embed_base_url or os.getenv("EMBED_BASE_URL", "http://127.0.0.1:11434/v1")
    model = embed_model or os.getenv("EMBED_MODEL", "nomic-embed-text:v1.5")
    g_raw = json.loads(guidance_path.read_text())
    guidance = guidance_from_guidance_proposition_extractor_output(
        g_raw if isinstance(g_raw, list) else g_raw.get("pages", [])
    )
    law_units, _ = load_law_units(law_path, source=law_source)
    law_index = list(
        zip(
            [lu.id for lu in law_units],
            _embed([lu.embed_text for lu in law_units], base_url, model),
            strict=False,
        )
    )
    g_embs = _embed([gp.proposition_text for gp in guidance], base_url, model)
    out: dict[str, int] = {}
    for gp, g_emb in zip(guidance, g_embs, strict=True):
        survivors = find_candidates(
            g_emb, law_index, top_k=TOP_K, threshold=THRESHOLD, score_gap=SCORE_GAP
        )
        out[gp.id] = len(survivors)
    return out


def validate_native_matcher_run(
    *,
    results: list[dict[str, Any]],
    input_guidance_ids: list[str],
    survivor_counts: dict[str, int] | None = None,
    law_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return a machine-readable validation report (``ok`` true iff all gates pass)."""
    errors: list[str] = []
    warnings: list[str] = []

    result_ids = [str(r.get("id") or "") for r in results]
    input_set = list(dict.fromkeys(input_guidance_ids))
    result_set = set(result_ids)

    if len(result_ids) != len(set(result_ids)):
        dupes = [gid for gid, n in Counter(result_ids).items() if n > 1]
        errors.append(f"duplicate guidance result IDs: {dupes[:20]}")
    if set(input_set) != result_set:
        missing = sorted(set(input_set) - result_set)
        extra = sorted(result_set - set(input_set))
        if missing:
            errors.append(f"missing guidance result IDs ({len(missing)}): {missing[:20]}")
        if extra:
            errors.append(f"extra guidance result IDs ({len(extra)}): {extra[:20]}")
    if len(result_ids) != len(input_set):
        errors.append(
            f"result count {len(result_ids)} != input guidance count {len(input_set)}"
        )

    classification_counts: Counter[str] = Counter()
    candidate_mismatches: list[dict[str, Any]] = []
    duplicate_pairs: list[dict[str, Any]] = []
    unknown_relationships: list[dict[str, Any]] = []
    consistency_errors: list[str] = []
    unresolved_law: list[dict[str, Any]] = []

    for row in results:
        gid = str(row.get("id") or "")
        mp = row.get("match_processing")
        mp_errors = validate_match_processing(mp)
        if mp_errors:
            errors.append(f"{gid}: match_processing invalid: {'; '.join(mp_errors)}")
            continue
        assert isinstance(mp, dict)
        classification = mp["classification"]
        if classification not in VALID_CLASSIFICATIONS:
            errors.append(f"{gid}: unknown classification {classification!r}")
        classification_counts[classification] += 1

        cand = int(mp["candidate_count"])
        if survivor_counts is not None:
            expected = survivor_counts.get(gid)
            if expected is None:
                errors.append(f"{gid}: no recomputed survivor count")
            elif expected != cand:
                candidate_mismatches.append(
                    {
                        "guidance_proposition_id": gid,
                        "match_processing.candidate_count": cand,
                        "recomputed_survivors": expected,
                    }
                )

        matches = row.get("matches") or []
        seen_law: set[str] = set()
        for match in matches:
            rel = str(match.get("relationship") or "")
            if rel not in RELATIONSHIP_TYPES:
                unknown_relationships.append(
                    {"guidance_proposition_id": gid, "relationship": rel}
                )
            lid = law_proposition_id(match)
            if lid is None:
                consistency_errors.append(f"{gid}: match missing law_proposition.id")
                continue
            if lid in seen_law:
                duplicate_pairs.append(
                    {"guidance_proposition_id": gid, "law_proposition_id": lid}
                )
            seen_law.add(lid)
            if law_ids is not None and lid not in law_ids:
                unresolved_law.append(
                    {"guidance_proposition_id": gid, "law_proposition_id": lid}
                )

        if cand == 0 and matches:
            consistency_errors.append(
                f"{gid}: zero survivors but {len(matches)} classified pair rows"
            )

    if candidate_mismatches:
        errors.append(
            f"candidate_count mismatch on {len(candidate_mismatches)} propositions"
        )
    if duplicate_pairs:
        warnings.append(
            f"duplicate (guidance, law) pairs within proposition: {len(duplicate_pairs)}"
        )
    if unknown_relationships:
        errors.append(
            f"unknown relationship labels: {len(unknown_relationships)} "
            f"(e.g. {unknown_relationships[:5]})"
        )
    if unresolved_law:
        errors.append(f"matches reference unknown law IDs: {len(unresolved_law)}")
    errors.extend(consistency_errors)

    incomplete = [
        str(r.get("id"))
        for r in results
        if (r.get("match_processing") or {}).get("classification") != "complete"
    ]
    ready_for_adjudication = (
        not errors
        and len(incomplete) == 0
        and classification_counts.get("complete", 0) == len(input_set)
        and len(input_set) > 0
    )

    return {
        "ok": not errors,
        "ready_for_adjudication": ready_for_adjudication,
        "input_guidance_count": len(input_set),
        "result_guidance_count": len(result_ids),
        "distinct_result_ids": len(result_set),
        "classification_counts": dict(classification_counts),
        "incomplete_guidance_proposition_ids": incomplete,
        "candidate_count_mismatches": candidate_mismatches,
        "duplicate_pairs": duplicate_pairs,
        "unknown_relationships": unknown_relationships,
        "unresolved_law_ids": unresolved_law,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Validate a native Proposition Matcher run (match_processing gate)."
    )
    ap.add_argument("--run", type=Path, required=True, help="Matcher run directory")
    ap.add_argument(
        "--guidance",
        type=Path,
        required=True,
        help="Authoritative Guidance Proposition Extractor output.json",
    )
    ap.add_argument(
        "--law",
        type=Path,
        required=True,
        help="Authoritative Law Proposition Extractor candidates/propositions",
    )
    ap.add_argument(
        "--law-source",
        choices=("auto", "propositions", "candidates"),
        default="auto",
    )
    ap.add_argument("--embed-base-url", default=os.getenv("EMBED_BASE_URL", "http://127.0.0.1:11434/v1"))
    ap.add_argument("--embed-model", default=os.getenv("EMBED_MODEL", "nomic-embed-text:v1.5"))
    ap.add_argument(
        "--skip-survivor-recompute",
        action="store_true",
        help="Skip local embed/retrieve candidate-count check (schema/scope only).",
    )
    ap.add_argument(
        "--write-json",
        type=Path,
        help="Optional path for machine-readable validation report",
    )
    args = ap.parse_args(argv)

    results_path = args.run / "results.json"
    if not results_path.is_file():
        raise SystemExit(f"missing {results_path}")

    g_raw = json.loads(args.guidance.read_text())
    guidance = guidance_from_guidance_proposition_extractor_output(
        g_raw if isinstance(g_raw, list) else g_raw.get("pages", [])
    )
    law_units, _ = load_law_units(args.law, source=args.law_source)
    results = load_results(results_path)

    survivor_counts = None
    if not args.skip_survivor_recompute:
        print("recomputing retrieval survivors for candidate_count check...", flush=True)
        survivor_counts = recompute_survivor_counts(
            guidance_path=args.guidance,
            law_path=args.law,
            law_source=args.law_source,
            embed_base_url=args.embed_base_url,
            embed_model=args.embed_model,
        )

    report = validate_native_matcher_run(
        results=results,
        input_guidance_ids=[gp.id for gp in guidance],
        survivor_counts=survivor_counts,
        law_ids={lu.id for lu in law_units},
    )
    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(json.dumps(report, indent=2))
        print(f"wrote {args.write_json}", flush=True)

    print(
        f"ok={report['ok']} ready_for_adjudication={report['ready_for_adjudication']} "
        f"guidance={report['result_guidance_count']}/{report['input_guidance_count']} "
        f"classifications={report['classification_counts']}",
        flush=True,
    )
    for err in report["errors"]:
        print(f"ERROR: {err}", file=sys.stderr)
    for warn in report["warnings"]:
        print(f"WARN: {warn}", file=sys.stderr)
    raise SystemExit(0 if report["ok"] and report["ready_for_adjudication"] else 1)


if __name__ == "__main__":
    main()
