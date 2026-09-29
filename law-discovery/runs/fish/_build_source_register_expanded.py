#!/usr/bin/env python3
"""Merge fish source register with reviewed related sources."""

from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REGISTER_INPUT = ROOT / "source-register-reviewed.json"
RELATED_INPUT = ROOT / "related-sources-reviewed.json"
OUTPUT_JSON = ROOT / "source-register-expanded-reviewed.json"
OUTPUT_MD = ROOT / "source-register-expanded-summary.md"
FLAT_OUTPUT_JSON = ROOT / "source-register-expanded-flat.json"
FLAT_OUTPUT_MD = ROOT / "source-register-expanded-flat-summary.md"

MERGE_PROMPT_ID = "fish-source-register-merge-related-BR1"
FLATTEN_PROMPT_ID = "fish-source-register-flat-export-BR1"

REGISTER_BUCKETS = (
    "accepted_sources",
    "historical_context",
    "parked_sources",
    "rejected_sources",
    "uncertain_sources",
)

FLATTEN_BUCKETS = (
    "accepted_sources",
    "historical_context",
    "uncertain_sources",
    "included_related_sources",
)

INCLUDED_RELATED_DECISIONS = {"include", "include_needs_legal_review"}

REVIEW_DECISION_RANK = {
    "include": 4,
    "include_needs_legal_review": 3,
    "park_contextual": 2,
    "exclude": 1,
}

SOURCE_ROLE_RANK = {
    "amendment": 100,
    "implementing_measure": 90,
    "related_principal": 80,
    "related_supporting": 70,
    "revocation": 60,
    "commencement": 60,
    "correction": 60,
    "explanatory_note": 50,
    "explanatory_memorandum": 50,
    "impact_assessment": 50,
    "guidance": 50,
    "framework_context": 40,
    "excluded_false_positive": 0,
}

BUCKET_DEFAULTS: dict[str, tuple[str, str]] = {
    "accepted_sources": ("include", "related_principal"),
    "historical_context": ("include", "related_supporting"),
    "uncertain_sources": ("include_needs_legal_review", "related_supporting"),
    "parked_sources": ("park_contextual", "framework_context"),
    "rejected_sources": ("exclude", "excluded_false_positive"),
}

PRESERVED_FIELDS = (
    "source_id",
    "title",
    "citation",
    "source_type",
    "canonical_uri",
    "jurisdiction_extent",
    "temporal_status",
    "relationship_to_category",
    "review_decision",
    "review_status",
    "source_role",
    "matched_terms",
    "ai_triage",
    "notes",
)


def short_title(title: str, max_len: int = 88) -> str:
    title = re.sub(r"\s+", " ", title.strip())
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"


def merge_notes(existing: str | None, incoming: str | None) -> str | None:
    parts: list[str] = []
    for note in (existing, incoming):
        if note and note.strip() and note.strip() not in parts:
            parts.append(note.strip())
    return "\n\n".join(parts) if parts else None


def merge_matched_terms(existing: list[str] | None, incoming: list[str] | None) -> list[str]:
    merged: list[str] = []
    for terms in (existing or [], incoming or []):
        for term in terms:
            if term not in merged:
                merged.append(term)
    return merged


def pick_review_decision(current: str | None, incoming: str | None) -> str | None:
    if not current:
        return incoming
    if not incoming:
        return current
    return (
        current
        if REVIEW_DECISION_RANK.get(current, 0) >= REVIEW_DECISION_RANK.get(incoming, 0)
        else incoming
    )


def pick_source_role(current: str | None, incoming: str | None) -> str | None:
    if not current:
        return incoming
    if not incoming:
        return current
    return (
        current
        if SOURCE_ROLE_RANK.get(current, 0) >= SOURCE_ROLE_RANK.get(incoming, 0)
        else incoming
    )


def derive_register_defaults(source: dict[str, Any], bucket: str) -> tuple[str, str]:
    review_status = source.get("review_status")
    if bucket == "accepted_sources" and review_status == "accepted":
        return ("include", "related_principal")
    if bucket == "historical_context":
        return ("include", "related_supporting")
    if bucket == "uncertain_sources":
        return ("include_needs_legal_review", "related_supporting")
    if bucket == "parked_sources":
        return ("park_contextual", "framework_context")
    if bucket == "rejected_sources":
        return ("exclude", "excluded_false_positive")
    return BUCKET_DEFAULTS.get(bucket, ("include", "related_supporting"))


def normalize_source(
    source: dict[str, Any],
    *,
    bucket: str | None = None,
) -> dict[str, Any]:
    out = deepcopy(source)
    if bucket:
        default_decision, default_role = derive_register_defaults(source, bucket)
        out.setdefault("review_decision", default_decision)
        out.setdefault("source_role", default_role)
    return out


def normalize_related_source(source: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(source)


def merge_source_fields(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    merged = deepcopy(existing)
    merged_decision = pick_review_decision(
        existing.get("review_decision"),
        incoming.get("review_decision"),
    )
    merged["review_decision"] = merged_decision
    merged["source_role"] = pick_source_role(
        existing.get("source_role"),
        incoming.get("source_role"),
    )
    if merged_decision == "include_needs_legal_review":
        merged["review_status"] = "needs_more_research"
    elif existing.get("review_status") not in {"historical_context", "parked", "rejected"}:
        merged["review_status"] = existing.get("review_status") or incoming.get("review_status")
    if incoming.get("relationship_to_category") not in (None, "unknown"):
        merged["relationship_to_category"] = incoming["relationship_to_category"]
    merged["matched_terms"] = merge_matched_terms(
        existing.get("matched_terms"),
        incoming.get("matched_terms"),
    )
    merged["notes"] = merge_notes(existing.get("notes"), incoming.get("notes"))
    if incoming.get("ai_triage") and not existing.get("ai_triage"):
        merged["ai_triage"] = incoming["ai_triage"]
    return merged


def find_source_location(
    register: dict[str, Any],
    *,
    source_id: str | None = None,
    canonical_uri: str | None = None,
) -> tuple[str, int] | None:
    if source_id:
        for bucket in REGISTER_BUCKETS:
            for idx, source in enumerate(register[bucket]):
                if source["source_id"] == source_id:
                    return bucket, idx
    if canonical_uri:
        for bucket in REGISTER_BUCKETS:
            for idx, source in enumerate(register[bucket]):
                if source.get("canonical_uri") == canonical_uri:
                    return bucket, idx
    return None


def all_register_sources(register: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for bucket in REGISTER_BUCKETS:
        items.extend(register[bucket])
    return items


def count_by(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(item.get(field, "unknown") for item in items).items()))


def extract_flat_source(source: dict[str, Any], bucket: str) -> dict[str, Any]:
    out = {field: deepcopy(source.get(field)) for field in PRESERVED_FIELDS}
    out["source_bucket"] = bucket
    return out


def dedupe_flat_sources(
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    seen_ids: set[str] = set()
    seen_uris: set[str] = set()
    kept: list[dict[str, Any]] = []
    omitted = 0
    for source in sources:
        source_id = source["source_id"]
        canonical_uri = source.get("canonical_uri")
        if source_id in seen_ids:
            omitted += 1
            continue
        if canonical_uri and canonical_uri in seen_uris:
            omitted += 1
            continue
        seen_ids.add(source_id)
        if canonical_uri:
            seen_uris.add(canonical_uri)
        kept.append(source)
    return kept, omitted


def build_flat_export(expanded: dict[str, Any]) -> dict[str, Any]:
    bucket_counts = {bucket: len(expanded[bucket]) for bucket in FLATTEN_BUCKETS}
    candidates: list[dict[str, Any]] = []
    for bucket in FLATTEN_BUCKETS:
        for source in expanded[bucket]:
            candidates.append(extract_flat_source(source, bucket))

    sources, _ = dedupe_flat_sources(candidates)
    sources.sort(key=lambda s: s["source_id"])
    relationships = deepcopy(expanded["relationships"])

    return {
        "category_id": expanded["category_id"],
        "created_at": expanded["created_at"],
        "metadata": {
            **expanded.get("metadata", {}),
            "flatten_prompt_id": FLATTEN_PROMPT_ID,
            "flatten_source_file": "source-register-expanded-reviewed.json",
            "flattened_source_count": len(sources),
            "accepted_count": bucket_counts["accepted_sources"],
            "historical_context_count": bucket_counts["historical_context"],
            "uncertain_count": bucket_counts["uncertain_sources"],
            "included_related_count": bucket_counts["included_related_sources"],
            "relationship_count": len(relationships),
            "omitted_rejected_count": len(expanded["rejected_sources"]),
            "omitted_parked_count": len(expanded["parked_sources"]),
        },
        "sources": sources,
        "relationships": relationships,
    }


def write_flat_summary(flat: dict[str, Any]) -> str:
    meta = flat["metadata"]
    sources = flat["sources"]
    relationships = flat["relationships"]
    pre_dedupe_total = sum(
        meta[b]
        for b in (
            "accepted_count",
            "historical_context_count",
            "uncertain_count",
            "included_related_count",
        )
    )
    dedupe_omitted = pre_dedupe_total - meta["flattened_source_count"]

    lines = [
        "# Fish flattened source register summary",
        "",
        "Flattened `source-register-expanded-reviewed.json` into a single `sources` array.",
        f"Output: `source-register-expanded-flat.json`",
        f"Prompt: `{FLATTEN_PROMPT_ID}`",
        "",
        "## Flatten counts",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Pre-dedupe bucket total | {pre_dedupe_total} |",
        f"| Deduplicated omitted | {dedupe_omitted} |",
        f"| Flattened source count | {meta['flattened_source_count']} |",
        f"| Accepted sources | {meta['accepted_count']} |",
        f"| Historical context | {meta['historical_context_count']} |",
        f"| Uncertain sources | {meta['uncertain_count']} |",
        f"| Included related sources | {meta['included_related_count']} |",
        f"| Relationships preserved | {meta['relationship_count']} |",
        f"| Omitted rejected sources | {meta['omitted_rejected_count']} |",
        f"| Omitted parked sources | {meta['omitted_parked_count']} |",
        "",
        "## Counts by source_bucket",
        "",
        "| source_bucket | Count |",
        "| --- | ---: |",
    ]
    for key, count in count_by(sources, "source_bucket").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## Counts by review_decision", "", "| review_decision | Count |", "| --- | ---: |"])
    for key, count in count_by(sources, "review_decision").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## Counts by source_role", "", "| source_role | Count |", "| --- | ---: |"])
    for key, count in count_by(sources, "source_role").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(
        ["", "## Counts by temporal_status", "", "| temporal_status | Count |", "| --- | ---: |"]
    )
    for key, count in count_by(sources, "temporal_status").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## Counts by source_type", "", "| source_type | Count |", "| --- | ---: |"])
    for key, count in count_by(sources, "source_type").items():
        lines.append(f"| {key} | {count} |")

    legal_review_queue = [
        s
        for s in sources
        if s.get("review_decision") == "include_needs_legal_review"
        or s.get("review_status") == "uncertain"
        or s.get("review_status") == "needs_more_research"
    ]
    legal_review_queue.sort(key=lambda s: s["title"].lower())

    lines.extend(["", "## Needs legal review queue", ""])
    for source in legal_review_queue:
        lines.append(
            f"- **{short_title(source['title'])}** (`{source['source_id']}`) — "
            f"{source.get('review_decision', 'n/a')} / {source.get('source_role', 'n/a')} "
            f"[{source.get('source_bucket')}]"
        )

    lines.extend(["", "## Relationships", ""])
    for rel in relationships:
        rel_type = rel.get("relationship_type", "unknown")
        from_id = rel.get("from_source_id", "?")
        to_id = rel.get("to_source_id", "?")
        lines.append(f"- `{from_id}` → `{to_id}` ({rel_type})")

    return "\n".join(lines) + "\n"


def main() -> None:
    register = json.loads(REGISTER_INPUT.read_text())
    related_run = json.loads(RELATED_INPUT.read_text())

    expanded: dict[str, Any] = {
        "register_id": "ada-register-fish-expanded",
        "category_id": register["category_id"],
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    for bucket in REGISTER_BUCKETS:
        expanded[bucket] = [
            normalize_source(source, bucket=bucket)
            for source in register[bucket]
        ]

    related_sources = related_run["related_sources"]
    relationships = deepcopy(related_run["relationships"])
    included_related = [
        s for s in related_sources if s.get("review_decision") in INCLUDED_RELATED_DECISIONS
    ]
    excluded_related = [
        s
        for s in related_sources
        if s.get("review_decision") not in INCLUDED_RELATED_DECISIONS
    ]

    duplicate_count = 0
    included_related_sources: list[dict[str, Any]] = []

    for related in included_related:
        normalized = normalize_related_source(related)
        location = find_source_location(
            expanded,
            source_id=related["source_id"],
            canonical_uri=related.get("canonical_uri"),
        )
        if location:
            bucket, idx = location
            expanded[bucket][idx] = merge_source_fields(expanded[bucket][idx], normalized)
            duplicate_count += 1
        else:
            included_related_sources.append(normalized)

    included_related_sources.sort(key=lambda s: (s.get("review_decision", ""), s["title"].lower()))
    expanded["included_related_sources"] = included_related_sources
    expanded["relationships"] = relationships

    original_source_count = sum(len(register[b]) for b in REGISTER_BUCKETS)
    related_source_count = len(related_sources)
    included_related_count = len(included_related)
    excluded_or_parked_related_count = len(excluded_related)
    merged_source_count = original_source_count + len(included_related_sources)

    expanded["metadata"] = {
        **register.get("metadata", {}),
        "merge_prompt_id": MERGE_PROMPT_ID,
        "source_register_file": "source-register-reviewed.json",
        "related_sources_file": "related-sources-reviewed.json",
        "related_expansion_run_id": related_run.get("run_id"),
        "merged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "original_source_count": original_source_count,
        "related_source_count": related_source_count,
        "merged_source_count": merged_source_count,
        "duplicate_count": duplicate_count,
        "relationship_count": len(relationships),
        "included_related_count": included_related_count,
        "excluded_or_parked_related_count": excluded_or_parked_related_count,
        "included_related_only_count": len(included_related_sources),
    }

    OUTPUT_JSON.write_text(json.dumps(expanded, indent=2, ensure_ascii=False) + "\n")

    merged_sources = all_register_sources(expanded) + included_related_sources
    principal_current = [
        s
        for s in expanded["accepted_sources"]
        if s.get("temporal_status") in {"current", "unknown", None}
    ]
    legal_review_queue = [
        s
        for s in merged_sources
        if s.get("review_decision") == "include_needs_legal_review"
        or s.get("review_status") == "uncertain"
        or s.get("review_status") == "needs_more_research"
    ]
    legal_review_queue.sort(key=lambda s: s["title"].lower())

    lines = [
        "# Fish expanded source register summary",
        "",
        f"Merged `source-register-reviewed.json` with `related-sources-reviewed.json`.",
        f"Output: `source-register-expanded-reviewed.json`",
        f"Prompt: `{MERGE_PROMPT_ID}`",
        "",
        "## Merge counts",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Original source register entries | {original_source_count} |",
        f"| Related sources reviewed | {related_source_count} |",
        f"| Included related sources (eligible) | {included_related_count} |",
        f"| Duplicates merged into register | {duplicate_count} |",
        f"| New related-only sources added | {len(included_related_sources)} |",
        f"| Merged source total | {merged_source_count} |",
        f"| Relationships preserved | {len(relationships)} |",
        f"| Excluded/parked related (not merged) | {excluded_or_parked_related_count} |",
        "",
        "## Counts by review_decision",
        "",
        "| review_decision | Count |",
        "| --- | ---: |",
    ]
    for key, count in count_by(merged_sources, "review_decision").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## Counts by source_role", "", "| source_role | Count |", "| --- | ---: |"])
    for key, count in count_by(merged_sources, "source_role").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(
        ["", "## Counts by temporal_status", "", "| temporal_status | Count |", "| --- | ---: |"]
    )
    for key, count in count_by(merged_sources, "temporal_status").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## Counts by source_type", "", "| source_type | Count |", "| --- | ---: |"])
    for key, count in count_by(merged_sources, "source_type").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## Principal / current sources", ""])
    for source in principal_current[:30]:
        lines.append(
            f"- **{short_title(source['title'])}** (`{source['source_id']}`) — "
            f"{source.get('review_decision', 'n/a')} / {source.get('source_role', 'n/a')}"
        )
    if len(principal_current) > 30:
        lines.append(f"- …and {len(principal_current) - 30} more in `accepted_sources`")

    lines.extend(["", "## Included related sources", ""])
    for source in included_related_sources:
        lines.append(
            f"- **{short_title(source['title'])}** (`{source['source_id']}`) — "
            f"{source.get('review_decision')} / {source.get('source_role')}"
        )
    if duplicate_count:
        lines.append(
            f"\n_{duplicate_count} included related source(s) were already present in the "
            "source register and were merged in place._"
        )

    lines.extend(["", "## Needs legal review queue", ""])
    for source in legal_review_queue:
        lines.append(
            f"- **{short_title(source['title'])}** (`{source['source_id']}`) — "
            f"{source.get('review_decision', 'n/a')} / {source.get('source_role', 'n/a')}"
        )

    lines.extend(["", "## Excluded / parked related sources (not merged)", ""])
    for source in sorted(excluded_related, key=lambda s: s["title"].lower()):
        lines.append(
            f"- **{short_title(source['title'])}** (`{source['source_id']}`) — "
            f"{source.get('review_decision')} / {source.get('source_role')}"
        )

    OUTPUT_MD.write_text("\n".join(lines) + "\n")

    flat = build_flat_export(expanded)
    FLAT_OUTPUT_JSON.write_text(json.dumps(flat, indent=2, ensure_ascii=False) + "\n")
    FLAT_OUTPUT_MD.write_text(write_flat_summary(flat))

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")
    print(f"Wrote {FLAT_OUTPUT_JSON}")
    print(f"Wrote {FLAT_OUTPUT_MD}")
    print(
        "merged:",
        merged_source_count,
        "duplicates:",
        duplicate_count,
        "new related:",
        len(included_related_sources),
        "flat:",
        flat["metadata"]["flattened_source_count"],
    )


def flatten_main() -> None:
    expanded = json.loads(OUTPUT_JSON.read_text())
    flat = build_flat_export(expanded)
    FLAT_OUTPUT_JSON.write_text(json.dumps(flat, indent=2, ensure_ascii=False) + "\n")
    FLAT_OUTPUT_MD.write_text(write_flat_summary(flat))
    print(f"Wrote {FLAT_OUTPUT_JSON}")
    print(f"Wrote {FLAT_OUTPUT_MD}")
    print("flat:", flat["metadata"]["flattened_source_count"])


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "flatten":
        flatten_main()
    else:
        main()
