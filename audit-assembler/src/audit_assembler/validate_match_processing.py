"""Validate Matcher ``match_processing`` at the Audit Assembler boundary.

Assembler never invents historic processing state. It consumes valid native or
approved reconstructed ``match_processing`` only. Absent metadata stays legacy
(``NOT_CHECKED``). Purported historic backfills with missing/invalid provenance
are rejected.
"""

from __future__ import annotations

from typing import Any

# Keep in sync with proposition_matcher.matching.historic_match_processing.POLICY_VERSION.
APPROVED_HISTORIC_BACKFILL_POLICY_VERSIONS = frozenset({
    "historic_match_processing_backfill_v1",
})

VALID_CLASSIFICATIONS = frozenset({"complete", "failed", "partial", "not_attempted"})


def validate_matcher_match_processing(matcher_output: list[dict]) -> list[str]:
    """Return errors for invalid ``match_processing`` rows (empty = OK).

    Missing ``match_processing`` is valid legacy input (Assembler → NOT_CHECKED).
    """
    errors: list[str] = []
    for index, row in enumerate(matcher_output):
        gp_id = row.get("id") or f"row[{index}]"
        mp = row.get("match_processing")
        if mp is None:
            continue
        if not isinstance(mp, dict):
            errors.append(f"{gp_id}: match_processing must be an object")
            continue
        if "candidate_count" not in mp:
            errors.append(f"{gp_id}: match_processing missing candidate_count")
        else:
            raw = mp["candidate_count"]
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                errors.append(f"{gp_id}: match_processing.candidate_count must be an int >= 0")
        classification = mp.get("classification")
        if classification not in VALID_CLASSIFICATIONS:
            errors.append(
                f"{gp_id}: match_processing.classification invalid: {classification!r}"
            )
        provenance = mp.get("provenance")
        if provenance is None:
            continue
        if not isinstance(provenance, dict):
            errors.append(f"{gp_id}: match_processing.provenance must be an object")
            continue
        origin = provenance.get("origin")
        if origin == "historic_backfill":
            policy = provenance.get("policy_version")
            if policy not in APPROVED_HISTORIC_BACKFILL_POLICY_VERSIONS:
                errors.append(
                    f"{gp_id}: historic_backfill provenance has unapproved or missing "
                    f"policy_version: {policy!r}"
                )
            codes = provenance.get("evidence_codes")
            if not isinstance(codes, list) or not codes:
                errors.append(
                    f"{gp_id}: historic_backfill provenance requires non-empty evidence_codes"
                )
        elif origin not in {None, "native"}:
            errors.append(f"{gp_id}: match_processing.provenance.origin invalid: {origin!r}")
    return errors


def count_historic_backfill_rows(matcher_output: list[dict]) -> int:
    n = 0
    for row in matcher_output:
        mp = row.get("match_processing")
        if isinstance(mp, dict):
            provenance = mp.get("provenance")
            if isinstance(provenance, dict) and provenance.get("origin") == "historic_backfill":
                n += 1
    return n


def collect_backfill_policy_versions(matcher_output: list[dict]) -> set[str]:
    versions: set[str] = set()
    for row in matcher_output:
        mp = row.get("match_processing")
        if not isinstance(mp, dict):
            continue
        provenance = mp.get("provenance")
        if isinstance(provenance, dict) and provenance.get("origin") == "historic_backfill":
            policy = provenance.get("policy_version")
            if isinstance(policy, str):
                versions.add(policy)
    return versions
