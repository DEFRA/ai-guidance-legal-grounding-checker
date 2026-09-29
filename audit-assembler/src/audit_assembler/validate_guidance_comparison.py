"""Validate assembled guidance–law comparison contract invariants.

Fails with actionable messages naming the guidance proposition id, broken
invariant, and expected vs actual values.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .match_summary import REPORTABLE_RELATIONSHIPS, is_reportable_relationship, normalise_relationship

NO_PAIR_FALLBACK_STATES = frozenset({
    ("COMPLETE", "ONLY_UNGROUNDED_CANDIDATES"),
    ("COMPLETE", "NO_CANDIDATES_FOUND"),
    ("NOT_CHECKED", None),
    ("PARTIAL", None),
    ("FAILED", None),
})


class ContractViolation(Exception):
    """One or more guidance-comparison invariants failed."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} guidance-comparison contract violation(s)")


def _load(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def validate_assembled_dir(dest: Path) -> list[str]:
    """Return a list of invariant violations (empty means OK)."""
    required = [
        "guidance-propositions.json",
        "legislation-propositions.json",
        "guidance-proposition-match-summaries.json",
        "guidance-proposition-law-comparisons.json",
        "proposition-matches.json",
    ]
    missing = [name for name in required if not (dest / name).exists()]
    if missing:
        return [f"missing assembled file(s): {', '.join(missing)}"]

    guidance = _load(dest / "guidance-propositions.json")
    law_props = _load(dest / "legislation-propositions.json")
    summaries = _load(dest / "guidance-proposition-match-summaries.json")
    comparisons = _load(dest / "guidance-proposition-law-comparisons.json")
    top_matches = _load(dest / "proposition-matches.json")

    return validate_assembled_payload(
        guidance_propositions=guidance,
        legislation_propositions=law_props,
        match_summaries=summaries,
        law_comparisons=comparisons,
        proposition_matches=top_matches,
    )


def validate_assembled_payload(
    *,
    guidance_propositions: list[dict],
    legislation_propositions: list[dict],
    match_summaries: list[dict],
    law_comparisons: list[dict],
    proposition_matches: list[dict],
) -> list[str]:
    errors: list[str] = []

    guidance_ids = [g["id"] for g in guidance_propositions if g.get("id")]
    guidance_id_set = set(guidance_ids)
    law_id_set = {lp["id"] for lp in legislation_propositions if lp.get("id")}

    # 1. Summary completeness — exactly one summary per guidance proposition.
    summary_ids = [s.get("guidance_proposition_id") for s in match_summaries]
    if len(match_summaries) != len(guidance_id_set):
        errors.append(
            "summary completeness: number of summaries "
            f"({len(match_summaries)}) !== number of guidance propositions in scope "
            f"({len(guidance_id_set)})"
        )
    summary_counts = Counter(summary_ids)
    for gp_id, n in summary_counts.items():
        if gp_id is None:
            errors.append("summary completeness: summary missing guidance_proposition_id")
            continue
        if n != 1:
            errors.append(
                f"summary completeness: guidance proposition {gp_id}: "
                f"expected exactly 1 summary, actual {n}"
            )
    for gp_id in guidance_id_set:
        if summary_counts.get(gp_id, 0) == 0:
            errors.append(
                f"summary completeness: guidance proposition {gp_id}: "
                "expected 1 summary, actual 0"
            )

    comparisons_by_gp: dict[str, list[dict]] = defaultdict(list)
    pair_keys: list[tuple[str, str]] = []
    for row in law_comparisons:
        gp_id = row.get("guidance_proposition_id")
        law_id = row.get("law_proposition_id")
        if gp_id:
            comparisons_by_gp[gp_id].append(row)
        if gp_id and law_id:
            pair_keys.append((gp_id, law_id))

        relationship = normalise_relationship(row.get("relationship"))
        if relationship == "UNGROUNDED":
            errors.append(
                f"relationship filtering: guidance proposition {gp_id}: "
                "UNGROUNDED pair must not appear in guidance-proposition-law-comparisons.json"
            )
        elif relationship not in REPORTABLE_RELATIONSHIPS:
            errors.append(
                f"relationship filtering: guidance proposition {gp_id}: "
                f"non-reportable relationship {row.get('relationship')!r} in assembled comparisons"
            )

        if gp_id not in guidance_id_set:
            errors.append(
                f"entity join: guidance proposition {gp_id}: "
                "assembled comparison references unknown guidance proposition"
            )
        if law_id not in law_id_set:
            errors.append(
                f"entity join: guidance proposition {gp_id}: "
                f"assembled comparison references unknown law proposition {law_id}"
            )

    # 2. Pair uniqueness
    pair_counts = Counter(pair_keys)
    for (gp_id, law_id), n in pair_counts.items():
        if n > 1:
            errors.append(
                f"pair uniqueness: guidance proposition {gp_id}: "
                f"duplicate (guidance_proposition_id, law_proposition_id)=({gp_id}, {law_id}); "
                f"expected 1, actual {n}"
            )

    summary_by_id = {s["guidance_proposition_id"]: s for s in match_summaries if s.get("guidance_proposition_id")}

    for gp_id, summary in summary_by_id.items():
        status = summary.get("assessment_status")
        coverage = summary.get("coverage_result")
        expected = summary.get("reportable_comparison_count")
        actual = len(comparisons_by_gp.get(gp_id, []))

        # 3. Reportable-pair invariant
        if status == "COMPLETE" and coverage == "HAS_REPORTABLE_COMPARISON":
            if expected != actual:
                errors.append(
                    f"reportable-pair invariant: guidance proposition {gp_id}: "
                    f"reportable_comparison_count expected {expected}, "
                    f"assembled distinct pairs actual {actual}"
                )

        # 4. No-pair fallback invariant
        if (status, coverage) in NO_PAIR_FALLBACK_STATES or (
            status in {"NOT_CHECKED", "PARTIAL", "FAILED"} and coverage is None
        ):
            if actual != 0:
                errors.append(
                    f"no-pair fallback invariant: guidance proposition {gp_id}: "
                    f"assessment_status={status} coverage_result={coverage}: "
                    f"expected 0 assembled comparison rows, actual {actual}"
                )

    # 5. Legacy separation — synthetic law-side GUIDANCE_MISSING stays on legacy path
    for row in proposition_matches:
        if (
            row.get("relationship") == "GUIDANCE_MISSING"
            and row.get("guidance_proposition_id") is None
        ):
            # Must not also appear as a guidance-side comparison/fallback.
            law_id = row.get("law_proposition_id")
            for cmp_row in law_comparisons:
                if (
                    cmp_row.get("law_proposition_id") == law_id
                    and cmp_row.get("guidance_proposition_id") is None
                ):
                    errors.append(
                        f"legacy separation: synthetic law-side GUIDANCE_MISSING for "
                        f"law proposition {law_id} must not appear in "
                        "guidance-proposition-law-comparisons.json"
                    )

    guidance_side_missing = [
        s
        for s in match_summaries
        if s.get("coverage_result") == "GUIDANCE_MISSING"
        or s.get("assessment_status") == "GUIDANCE_MISSING"
    ]
    if guidance_side_missing:
        for s in guidance_side_missing:
            errors.append(
                f"legacy separation: guidance proposition {s.get('guidance_proposition_id')}: "
                "GUIDANCE_MISSING must not be represented as a guidance-side summary fallback"
            )

    return errors


def assert_valid_assembled_dir(dest: Path) -> None:
    errors = validate_assembled_dir(dest)
    if errors:
        raise ContractViolation(errors)
