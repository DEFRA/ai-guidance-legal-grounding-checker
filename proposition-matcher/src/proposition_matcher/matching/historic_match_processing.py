"""Official historic ``match_processing`` reconstruction policy.

Policy version: ``historic_match_processing_backfill_v1``.

Fail-closed: a classification is written only from affirmative evidence.
Empty ``matches[]`` alone is never proof of ``complete`` + zero candidates.
``candidate_count`` means retrieval survivors (same unit as live Matcher runs),
never ``len(matches)`` unless a survivors artefact proves equality.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .match_summary import (
    ClassificationOutcome,
    build_match_processing,
    law_proposition_id,
    summarise_guidance_proposition_match,
)

POLICY_VERSION = "historic_match_processing_backfill_v1"

VALID_CLASSIFICATIONS = frozenset({"complete", "failed", "partial", "not_attempted"})

# Analysis / migration statuses — not part of the runtime classification enum.
AnalysisStatus = Literal[
    "native",
    "reconstructed",
    "ambiguous",
    "invalid_native",
    "missing_result",
]

EvidenceCode = Literal[
    "NATIVE_MATCH_PROCESSING",
    "RESULT_ROW_PRESENT",
    "SURVIVOR_LIST_PRESENT",
    "ZERO_SURVIVORS_RECORDED",
    "ALL_SURVIVORS_CLASSIFIED",
    "SOME_SURVIVORS_CLASSIFIED",
    "NO_SURVIVORS_CLASSIFIED",
    "PROPOSITION_TERMINAL_FAILURE",
    "EXPLICIT_SKIP_RECORDED",
    "METRICS_EMPTY_COUNT_ALIGNED",
    "GROUP_RERANK_ZERO_ERRORS",
    "GROUP_RERANK_ERRORS_UNATTRIBUTED",
    "CANDIDATE_COUNT_FROM_SURVIVOR_LIST",
    "EMPTY_MATCHES_WITHOUT_SUCCESS_EVIDENCE",
    "NON_EMPTY_MATCHES_WITHOUT_SURVIVOR_EVIDENCE",
    "MISSING_RESULT_WITHOUT_SKIP_EVIDENCE",
    "AUTHORITATIVE_CANDIDATE_COUNT_UNAVAILABLE",
]


@dataclass(frozen=True)
class PropositionAnalysis:
    guidance_proposition_id: str
    analysis_status: AnalysisStatus
    evidence_codes: list[str]
    match_processing: dict[str, Any] | None = None
    ambiguity_reasons: list[str] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass
class BackfillReport:
    policy_version: str
    source_run: str
    destination_run: str | None
    source_content_hash: str
    tool_version: str
    total_guidance_propositions: int
    native_count: int
    reconstructed_complete: int
    reconstructed_failed: int
    reconstructed_partial: int
    reconstructed_not_attempted: int
    ambiguous_count: int
    invalid_native_count: int
    missing_result_count: int
    production_backfill_eligible: bool
    candidate_count_evidence_sources: list[str]
    ambiguous_proposition_ids: list[str]
    warnings: list[str]
    propositions: list[dict[str, Any]]
    metrics_summary: dict[str, Any]


def source_content_hash(results_path: Path) -> str:
    digest = hashlib.sha256(results_path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def validate_match_processing(mp: Any) -> list[str]:
    """Return validation errors for a ``match_processing`` object (empty = OK)."""
    errors: list[str] = []
    if not isinstance(mp, dict):
        return ["match_processing must be an object"]
    if "candidate_count" not in mp:
        errors.append("missing candidate_count")
    else:
        raw_count = mp["candidate_count"]
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            errors.append("candidate_count must be an integer")
        elif raw_count < 0:
            errors.append("candidate_count must be >= 0")
    classification = mp.get("classification")
    if classification not in VALID_CLASSIFICATIONS:
        errors.append(
            f"classification must be one of {sorted(VALID_CLASSIFICATIONS)}, "
            f"got {classification!r}"
        )
    if "failure_reason" in mp and mp["failure_reason"] is not None:
        if not isinstance(mp["failure_reason"], str) or not mp["failure_reason"].strip():
            errors.append("failure_reason must be a non-empty string when present")
    provenance = mp.get("provenance")
    if provenance is not None:
        errors.extend(validate_backfill_provenance(provenance))
    return errors


def validate_backfill_provenance(provenance: Any) -> list[str]:
    if not isinstance(provenance, dict):
        return ["provenance must be an object"]
    errors: list[str] = []
    origin = provenance.get("origin")
    if origin not in {"native", "historic_backfill"}:
        errors.append(f"provenance.origin must be 'native' or 'historic_backfill', got {origin!r}")
    if origin == "historic_backfill":
        if provenance.get("policy_version") != POLICY_VERSION:
            errors.append(
                f"provenance.policy_version must be {POLICY_VERSION!r} for historic_backfill, "
                f"got {provenance.get('policy_version')!r}"
            )
        codes = provenance.get("evidence_codes")
        if not isinstance(codes, list) or not codes or not all(isinstance(c, str) for c in codes):
            errors.append("provenance.evidence_codes must be a non-empty list of strings")
    return errors


def load_run_artefacts(run_dir: Path) -> dict[str, Any]:
    """Load historic Matcher run artefacts used by the backfill policy."""
    run_dir = run_dir.resolve()
    results_path = _resolve_results_path(run_dir)
    results = json.loads(results_path.read_text())
    if not isinstance(results, list):
        raise ValueError(f"{results_path} must contain a JSON array of guidance rows")

    metrics_path = run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else None

    errors_path = run_dir / "proposition_errors.json"
    proposition_errors = (
        json.loads(errors_path.read_text()) if errors_path.exists() else None
    )

    skips_path = run_dir / "proposition_skips.json"
    proposition_skips = json.loads(skips_path.read_text()) if skips_path.exists() else None

    survivors_by_id = _load_survivors_by_id(run_dir)
    guidance_ids = _guidance_ids_in_scope(results, run_dir)

    return {
        "run_dir": run_dir,
        "results_path": results_path,
        "results": results,
        "metrics": metrics,
        "proposition_errors": proposition_errors or {},
        "proposition_skips": set(proposition_skips or []),
        "survivors_by_id": survivors_by_id,
        "guidance_ids": guidance_ids,
        "model_md_present": (run_dir / "MODEL.md").exists(),
    }


def analyse_run(
    run_dir: Path,
    *,
    tool_version: str = "0.1.0",
    destination_run: Path | None = None,
) -> tuple[BackfillReport, list[PropositionAnalysis], list[dict[str, Any]]]:
    """Analyse a historic Matcher run under ``historic_match_processing_backfill_v1``.

    Returns ``(report, per_proposition_analysis, results_with_reconstructions)``.
    Reconstructed ``match_processing`` is applied only where justified; ambiguous
    rows keep their original shape (no fabricated processing).
    """
    artefacts = load_run_artefacts(run_dir)
    results: list[dict[str, Any]] = artefacts["results"]
    results_by_id = {_row_id(r, i): r for i, r in enumerate(results)}
    guidance_ids: list[str] = artefacts["guidance_ids"]
    metrics = artefacts["metrics"]
    survivors_by_id: dict[str, list[str] | None] = artefacts["survivors_by_id"]
    proposition_errors: dict[str, Any] = artefacts["proposition_errors"]
    proposition_skips: set[str] = artefacts["proposition_skips"]

    warnings: list[str] = []
    content_hash = source_content_hash(artefacts["results_path"])
    candidate_sources: set[str] = set()

    unattributed_rerank_errors = _unattributed_group_rerank_errors(
        metrics, proposition_errors
    )
    if unattributed_rerank_errors:
        warnings.append(
            "metrics.group_rerank.errored > 0 without per-proposition error attribution; "
            "affected propositions cannot be safely reconstructed from aggregates alone"
        )

    empty_aligned = _metrics_empty_count_aligned(metrics, results)
    if empty_aligned:
        candidate_sources.add("metrics.guidance_props_empty_aligned")

    if any(v is not None for v in survivors_by_id.values()):
        candidate_sources.add("survivors_artefact")

    analyses: list[PropositionAnalysis] = []
    out_results: list[dict[str, Any]] = []

    # Preserve order of original results; append missing guidance ids at end.
    ordered_ids = list(guidance_ids)
    for i, row in enumerate(results):
        rid = _row_id(row, i)
        if rid not in ordered_ids:
            ordered_ids.append(rid)

    emitted_ids: set[str] = set()
    for gp_id in ordered_ids:
        row = results_by_id.get(gp_id)
        analysis = _analyse_proposition(
            gp_id=gp_id,
            row=row,
            survivors=survivors_by_id.get(gp_id),
            has_survivors_artefact=gp_id in survivors_by_id and survivors_by_id[gp_id] is not None,
            proposition_error=proposition_errors.get(gp_id),
            explicitly_skipped=gp_id in proposition_skips,
            empty_aligned=empty_aligned,
            unattributed_rerank_errors=unattributed_rerank_errors,
            metrics=metrics,
            source_run=str(artefacts["run_dir"]),
            source_content_hash=content_hash,
            tool_version=tool_version,
        )
        analyses.append(analysis)
        emitted_ids.add(gp_id)

        if row is None:
            continue
        new_row = dict(row)
        if analysis.analysis_status == "reconstructed" and analysis.match_processing is not None:
            new_row["match_processing"] = analysis.match_processing
            new_row["match_summary"] = summarise_guidance_proposition_match(
                guidance_proposition_id=gp_id,
                match_processing=analysis.match_processing,
                matches=new_row.get("matches"),
            )
        out_results.append(new_row)

    # Keep original row order for rows that existed; do not invent missing rows.
    if len(out_results) != len(results):
        # Rebuild in source order with reconstructions applied by id.
        by_id = {_row_id(r, i): r for i, r in enumerate(out_results)}
        out_results = []
        for i, row in enumerate(results):
            rid = _row_id(row, i)
            out_results.append(by_id.get(rid, dict(row)))

    report = _build_report(
        analyses=analyses,
        artefacts=artefacts,
        content_hash=content_hash,
        tool_version=tool_version,
        destination_run=destination_run,
        candidate_sources=sorted(candidate_sources),
        warnings=warnings,
    )
    return report, analyses, out_results


def write_backfill(
    run_dir: Path,
    dest: Path,
    *,
    overwrite: bool = False,
    tool_version: str = "0.1.0",
) -> BackfillReport:
    """Write a derived run with reconstructed ``match_processing`` (strict mode).

    Fails closed if any proposition is ambiguous or has invalid native processing.
    Never mutates ``run_dir``.
    """
    dest = dest.resolve()
    run_dir = run_dir.resolve()
    if dest == run_dir:
        raise ValueError("destination must differ from source run (refusing in-place mutation)")
    if dest.exists() and not overwrite:
        raise FileExistsError(
            f"destination exists: {dest} (pass overwrite=True / --overwrite to replace)"
        )

    report, analyses, out_results = analyse_run(
        run_dir, tool_version=tool_version, destination_run=dest
    )
    if not report.production_backfill_eligible:
        ambiguous = report.ambiguous_proposition_ids
        invalid = sum(1 for a in analyses if a.analysis_status == "invalid_native")
        raise RuntimeError(
            "run is not production-backfill eligible under "
            f"{POLICY_VERSION}: ambiguous={len(ambiguous)}, invalid_native={invalid}. "
            "Re-run analysis with --check and inspect the report; a Matcher rerun may be required."
        )

    _atomic_write_derived_run(
        source_dir=run_dir,
        dest=dest,
        results=out_results,
        report=report,
    )
    return report


def report_to_dict(report: BackfillReport) -> dict[str, Any]:
    return asdict(report)


def format_analysis_text(report: BackfillReport) -> str:
    lines = [
        f"policy_version: {report.policy_version}",
        f"source_run: {report.source_run}",
        f"source_content_hash: {report.source_content_hash}",
        f"total_guidance_propositions: {report.total_guidance_propositions}",
        f"native_processing_records: {report.native_count}",
        f"reconstructable_complete: {report.reconstructed_complete}",
        f"reconstructable_failed: {report.reconstructed_failed}",
        f"reconstructable_partial: {report.reconstructed_partial}",
        f"reconstructable_not_attempted: {report.reconstructed_not_attempted}",
        f"ambiguous: {report.ambiguous_count}",
        f"invalid_native: {report.invalid_native_count}",
        f"missing_result_identities: {report.missing_result_count}",
        f"candidate_count_evidence_sources: {', '.join(report.candidate_count_evidence_sources) or '(none)'}",
        f"production_backfill_eligible: {report.production_backfill_eligible}",
    ]
    if report.warnings:
        lines.append("warnings:")
        lines.extend(f"  - {w}" for w in report.warnings)
    if report.ambiguous_proposition_ids:
        lines.append("ambiguous_proposition_ids:")
        for gp_id in report.ambiguous_proposition_ids[:50]:
            lines.append(f"  - {gp_id}")
        if len(report.ambiguous_proposition_ids) > 50:
            lines.append(f"  … ({len(report.ambiguous_proposition_ids) - 50} more)")
    return "\n".join(lines) + "\n"


# ── internals ─────────────────────────────────────────────────────────────────


def _resolve_results_path(run_dir: Path) -> Path:
    for name in ("results.json", "output.json"):
        path = run_dir / name
        if path.exists():
            return path
    raise FileNotFoundError(f"no results.json or output.json in {run_dir}")


def _row_id(row: dict[str, Any], index: int) -> str:
    if row.get("id"):
        return str(row["id"])
    # Older Beatrice runs keyed rows by guidance text + url.
    text = str(row.get("guidance_proposition_text") or row.get("proposition_text") or "")
    url = str(row.get("guidance_source_url") or row.get("url") or "")
    if text or url:
        return f"text-url:{hashlib.sha256(f'{url}\n{text}'.encode()).hexdigest()[:16]}"
    return f"row-index:{index}"


def _guidance_ids_in_scope(results: list[dict[str, Any]], run_dir: Path) -> list[str]:
    """Guidance proposition identities in scope for the run.

    Prefer an explicit ``guidance_proposition_ids.json`` when present; otherwise
    every result row is in scope (historic Matcher emits one row per GP).
    """
    ids_path = run_dir / "guidance_proposition_ids.json"
    if ids_path.exists():
        raw = json.loads(ids_path.read_text())
        if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
            raise ValueError("guidance_proposition_ids.json must be a JSON array of strings")
        return list(raw)
    return [_row_id(r, i) for i, r in enumerate(results)]


def _load_survivors_by_id(run_dir: Path) -> dict[str, list[str] | None]:
    """Map guidance id → survivor law ids when a survivors artefact exists.

    Only ``survivors.json`` is authoritative. Older ``intermediates/04-matches.json``
    dumps (e.g. verdict-otter) are broader retrieval lists, not the group-rerank
    survivor set that live Matcher counts as ``candidate_count`` — using them
    would mis-classify completed runs as ``partial``.
    """
    survivors_path = run_dir / "survivors.json"
    if survivors_path.exists():
        return _parse_survivors_json(json.loads(survivors_path.read_text()))
    return {}
def _parse_survivors_json(raw: Any) -> dict[str, list[str] | None]:
    out: dict[str, list[str] | None] = {}
    if isinstance(raw, dict):
        for gp_id, laws in raw.items():
            if laws is None:
                out[str(gp_id)] = None
            elif isinstance(laws, list):
                out[str(gp_id)] = [str(x) for x in laws]
            else:
                raise ValueError(f"survivors.json[{gp_id!r}] must be a list of law ids")
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or "id" not in item:
                raise ValueError("survivors.json list entries need {id, survivor_law_ids}")
            laws = item.get("survivor_law_ids")
            out[str(item["id"])] = None if laws is None else [str(x) for x in laws]
        return out
    raise ValueError("survivors.json must be an object or array")


def _unattributed_group_rerank_errors(
    metrics: dict[str, Any] | None, proposition_errors: dict[str, Any]
) -> bool:
    if not metrics:
        return False
    errored = int((metrics.get("group_rerank") or {}).get("errored") or 0)
    if errored <= 0:
        return False
    # Any structured per-prop error map counts as attribution capacity.
    return not bool(proposition_errors)


def _metrics_empty_count_aligned(
    metrics: dict[str, Any] | None, results: list[dict[str, Any]]
) -> bool:
    """True only when metrics prove empty-match rows are exactly the zero-survivor set."""
    if not metrics:
        return False
    try:
        empty_metric = int(metrics["guidance_props_empty"])
        with_survivors = int(metrics["guidance_props_with_survivors"])
        gp_total = int(metrics["guidance_propositions"])
        errored = int((metrics.get("group_rerank") or {}).get("errored") or 0)
    except (KeyError, TypeError, ValueError):
        return False
    empty_rows = sum(1 for r in results if not (r.get("matches") or []))
    return (
        errored == 0
        and empty_metric + with_survivors == gp_total
        and gp_total == len(results)
        and empty_rows == empty_metric
    )


def _classified_law_ids(matches: list[dict[str, Any]] | None) -> set[str]:
    ids: set[str] = set()
    for m in matches or []:
        lid = law_proposition_id(m) or (m.get("law_id") if isinstance(m, dict) else None)
        if lid:
            ids.add(str(lid))
    return ids


def _analyse_proposition(
    *,
    gp_id: str,
    row: dict[str, Any] | None,
    survivors: list[str] | None,
    has_survivors_artefact: bool,
    proposition_error: Any,
    explicitly_skipped: bool,
    empty_aligned: bool,
    unattributed_rerank_errors: bool,
    metrics: dict[str, Any] | None,
    source_run: str,
    source_content_hash: str,
    tool_version: str,
) -> PropositionAnalysis:
    if row is not None and "match_processing" in row and row["match_processing"] is not None:
        errors = validate_match_processing(row["match_processing"])
        if errors:
            return PropositionAnalysis(
                guidance_proposition_id=gp_id,
                analysis_status="invalid_native",
                evidence_codes=[],
                ambiguity_reasons=errors,
            )
        return PropositionAnalysis(
            guidance_proposition_id=gp_id,
            analysis_status="native",
            evidence_codes=["NATIVE_MATCH_PROCESSING"],
            match_processing=dict(row["match_processing"]),
        )

    if row is None:
        if explicitly_skipped:
            mp = _reconstructed_processing(
                candidate_count=0,
                classification="not_attempted",
                evidence_codes=["EXPLICIT_SKIP_RECORDED"],
                source_run=source_run,
                source_content_hash=source_content_hash,
                tool_version=tool_version,
            )
            return PropositionAnalysis(
                guidance_proposition_id=gp_id,
                analysis_status="reconstructed",
                evidence_codes=["EXPLICIT_SKIP_RECORDED"],
                match_processing=mp,
            )
        return PropositionAnalysis(
            guidance_proposition_id=gp_id,
            analysis_status="ambiguous",
            evidence_codes=["MISSING_RESULT_WITHOUT_SKIP_EVIDENCE"],
            ambiguity_reasons=[
                "guidance proposition missing from results with no explicit skip record"
            ],
        )

    evidence: list[str] = ["RESULT_ROW_PRESENT"]
    matches = row.get("matches") or []

    if explicitly_skipped:
        mp = _reconstructed_processing(
            candidate_count=0,
            classification="not_attempted",
            evidence_codes=evidence + ["EXPLICIT_SKIP_RECORDED"],
            source_run=source_run,
            source_content_hash=source_content_hash,
            tool_version=tool_version,
        )
        return PropositionAnalysis(
            guidance_proposition_id=gp_id,
            analysis_status="reconstructed",
            evidence_codes=mp["provenance"]["evidence_codes"],
            match_processing=mp,
        )

    if proposition_error:
        reason = _stable_failure_reason(proposition_error)
        count = len(survivors) if survivors is not None else 0
        codes = evidence + ["PROPOSITION_TERMINAL_FAILURE"]
        if survivors is not None:
            codes.append("SURVIVOR_LIST_PRESENT")
            codes.append("CANDIDATE_COUNT_FROM_SURVIVOR_LIST")
        mp = _reconstructed_processing(
            candidate_count=count,
            classification="failed",
            failure_reason=reason,
            evidence_codes=codes,
            source_run=source_run,
            source_content_hash=source_content_hash,
            tool_version=tool_version,
        )
        return PropositionAnalysis(
            guidance_proposition_id=gp_id,
            analysis_status="reconstructed",
            evidence_codes=codes,
            match_processing=mp,
            failure_reason=reason,
        )

    if unattributed_rerank_errors:
        return PropositionAnalysis(
            guidance_proposition_id=gp_id,
            analysis_status="ambiguous",
            evidence_codes=evidence + ["GROUP_RERANK_ERRORS_UNATTRIBUTED"],
            ambiguity_reasons=[
                "run-level group_rerank errors exist without per-proposition attribution"
            ],
        )

    # Affirmative survivor-list path (authoritative candidate_count).
    if has_survivors_artefact and survivors is not None:
        return _analyse_with_survivors(
            gp_id=gp_id,
            matches=matches,
            survivors=survivors,
            base_evidence=evidence,
            metrics=metrics,
            source_run=source_run,
            source_content_hash=source_content_hash,
            tool_version=tool_version,
        )

    # Narrow metrics-alignment path for true zero-survivor empties only.
    if empty_aligned and not matches:
        codes = evidence + [
            "METRICS_EMPTY_COUNT_ALIGNED",
            "GROUP_RERANK_ZERO_ERRORS",
            "ZERO_SURVIVORS_RECORDED",
        ]
        mp = _reconstructed_processing(
            candidate_count=0,
            classification="complete",
            evidence_codes=codes,
            source_run=source_run,
            source_content_hash=source_content_hash,
            tool_version=tool_version,
        )
        return PropositionAnalysis(
            guidance_proposition_id=gp_id,
            analysis_status="reconstructed",
            evidence_codes=codes,
            match_processing=mp,
        )

    # No authoritative survivor evidence → cannot invent candidate_count.
    if not matches:
        return PropositionAnalysis(
            guidance_proposition_id=gp_id,
            analysis_status="ambiguous",
            evidence_codes=evidence + ["EMPTY_MATCHES_WITHOUT_SUCCESS_EVIDENCE"],
            ambiguity_reasons=[
                "empty matches[] without survivors artefact or metrics empty-count alignment; "
                "cannot distinguish complete/zero-candidates from failed/partial/not-attempted"
            ],
        )

    return PropositionAnalysis(
        guidance_proposition_id=gp_id,
        analysis_status="ambiguous",
        evidence_codes=evidence
        + [
            "NON_EMPTY_MATCHES_WITHOUT_SURVIVOR_EVIDENCE",
            "AUTHORITATIVE_CANDIDATE_COUNT_UNAVAILABLE",
        ],
        ambiguity_reasons=[
            "non-empty matches[] without survivors artefact; "
            "candidate_count is retrieval survivors and must not be inferred from len(matches)"
        ],
    )


def _analyse_with_survivors(
    *,
    gp_id: str,
    matches: list[dict[str, Any]],
    survivors: list[str],
    base_evidence: list[str],
    metrics: dict[str, Any] | None,
    source_run: str,
    source_content_hash: str,
    tool_version: str,
) -> PropositionAnalysis:
    survivor_set = set(survivors)
    classified = _classified_law_ids(matches) & survivor_set
    codes = base_evidence + [
        "SURVIVOR_LIST_PRESENT",
        "CANDIDATE_COUNT_FROM_SURVIVOR_LIST",
    ]
    if metrics and int((metrics.get("group_rerank") or {}).get("errored") or 0) == 0:
        codes.append("GROUP_RERANK_ZERO_ERRORS")

    if len(survivors) == 0:
        codes.append("ZERO_SURVIVORS_RECORDED")
        classification: ClassificationOutcome = "complete"
        failure_reason = None
    elif len(classified) == len(survivor_set):
        codes.append("ALL_SURVIVORS_CLASSIFIED")
        classification = "complete"
        failure_reason = None
    elif classified:
        codes.append("SOME_SURVIVORS_CLASSIFIED")
        classification = "partial"
        failure_reason = "not_all_candidates_classified"
    else:
        codes.append("NO_SURVIVORS_CLASSIFIED")
        classification = "partial"
        failure_reason = "no_candidates_classified"

    mp = _reconstructed_processing(
        candidate_count=len(survivors),
        classification=classification,
        failure_reason=failure_reason,
        evidence_codes=codes,
        source_run=source_run,
        source_content_hash=source_content_hash,
        tool_version=tool_version,
    )
    return PropositionAnalysis(
        guidance_proposition_id=gp_id,
        analysis_status="reconstructed",
        evidence_codes=codes,
        match_processing=mp,
        failure_reason=failure_reason,
    )


def _stable_failure_reason(error: Any) -> str:
    if isinstance(error, dict):
        reason = error.get("failure_reason") or error.get("reason") or error.get("type")
        if isinstance(reason, str) and reason.strip():
            # Keep short, non-sensitive codes only.
            cleaned = reason.strip().replace(" ", "_").lower()[:120]
            return cleaned
    if isinstance(error, str) and error.strip():
        return error.strip().replace(" ", "_").lower()[:120]
    return "proposition_terminal_failure"


def _reconstructed_processing(
    *,
    candidate_count: int,
    classification: ClassificationOutcome,
    evidence_codes: list[str],
    source_run: str,
    source_content_hash: str,
    tool_version: str,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    row = build_match_processing(
        candidate_count=candidate_count,
        classification=classification,
        failure_reason=failure_reason,
    )
    row["provenance"] = {
        "origin": "historic_backfill",
        "policy_version": POLICY_VERSION,
        "evidence_codes": list(evidence_codes),
        "source_run": source_run,
        "source_content_hash": source_content_hash,
        "tool_version": tool_version,
    }
    return row


def _build_report(
    *,
    analyses: list[PropositionAnalysis],
    artefacts: dict[str, Any],
    content_hash: str,
    tool_version: str,
    destination_run: Path | None,
    candidate_sources: list[str],
    warnings: list[str],
) -> BackfillReport:
    native = sum(1 for a in analyses if a.analysis_status == "native")
    invalid = sum(1 for a in analyses if a.analysis_status == "invalid_native")
    missing = sum(
        1
        for a in analyses
        if a.analysis_status == "ambiguous"
        and "MISSING_RESULT_WITHOUT_SKIP_EVIDENCE" in a.evidence_codes
    )
    ambiguous_ids = [
        a.guidance_proposition_id for a in analyses if a.analysis_status == "ambiguous"
    ]
    recon = [a for a in analyses if a.analysis_status == "reconstructed"]

    def _cls(name: str) -> int:
        return sum(
            1
            for a in recon
            if (a.match_processing or {}).get("classification") == name
        )

    eligible = (
        invalid == 0
        and len(ambiguous_ids) == 0
        and all(a.analysis_status in {"native", "reconstructed"} for a in analyses)
    )

    metrics = artefacts.get("metrics") or {}
    return BackfillReport(
        policy_version=POLICY_VERSION,
        source_run=str(artefacts["run_dir"]),
        destination_run=str(destination_run) if destination_run else None,
        source_content_hash=content_hash,
        tool_version=tool_version,
        total_guidance_propositions=len(analyses),
        native_count=native,
        reconstructed_complete=_cls("complete"),
        reconstructed_failed=_cls("failed"),
        reconstructed_partial=_cls("partial"),
        reconstructed_not_attempted=_cls("not_attempted"),
        ambiguous_count=len(ambiguous_ids),
        invalid_native_count=invalid,
        missing_result_count=missing,
        production_backfill_eligible=eligible,
        candidate_count_evidence_sources=candidate_sources,
        ambiguous_proposition_ids=ambiguous_ids,
        warnings=warnings,
        propositions=[
            {
                "guidance_proposition_id": a.guidance_proposition_id,
                "analysis_status": a.analysis_status,
                "evidence_codes": a.evidence_codes,
                "classification": (a.match_processing or {}).get("classification"),
                "candidate_count": (a.match_processing or {}).get("candidate_count"),
                "ambiguity_reasons": a.ambiguity_reasons,
                "failure_reason": a.failure_reason,
            }
            for a in analyses
        ],
        metrics_summary={
            "guidance_propositions": metrics.get("guidance_propositions"),
            "guidance_props_with_survivors": metrics.get("guidance_props_with_survivors"),
            "guidance_props_empty": metrics.get("guidance_props_empty"),
            "group_rerank_errored": (metrics.get("group_rerank") or {}).get("errored"),
            "model_md_present": artefacts.get("model_md_present"),
            "survivors_artefact_present": bool(artefacts.get("survivors_by_id")),
        },
    )


def _atomic_write_derived_run(
    *,
    source_dir: Path,
    dest: Path,
    results: list[dict[str, Any]],
    report: BackfillReport,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(dest.parent)) as tmp:
        tmp_dir = Path(tmp) / "run"
        shutil.copytree(source_dir, tmp_dir, dirs_exist_ok=True)
        results_name = "results.json" if (source_dir / "results.json").exists() else "output.json"
        (tmp_dir / results_name).write_text(json.dumps(results, indent=2) + "\n")
        (tmp_dir / "match_processing_backfill_report.json").write_text(
            json.dumps(report_to_dict(report), indent=2) + "\n"
        )
        _append_model_md_backfill_note(tmp_dir, report)
        if dest.exists():
            shutil.rmtree(dest)
        tmp_dir.rename(dest)


def _append_model_md_backfill_note(run_dir: Path, report: BackfillReport) -> None:
    note = f"""

## Historic match_processing backfill

- **Policy:** `{report.policy_version}`
- **Source run:** `{report.source_run}`
- **Source content hash:** `{report.source_content_hash}`
- **Tool version:** `{report.tool_version}`
- **Eligible:** `{report.production_backfill_eligible}`
- **Machine report:** `match_processing_backfill_report.json`

Pair relationships and match rows are unchanged. Only approved `match_processing`
provenance was added under the fail-closed historic backfill policy.
"""
    model_path = run_dir / "MODEL.md"
    if model_path.exists():
        model_path.write_text(model_path.read_text() + note)
    else:
        model_path.write_text(
            f"# Derived Matcher run — historic match_processing backfill\n{note}"
        )
