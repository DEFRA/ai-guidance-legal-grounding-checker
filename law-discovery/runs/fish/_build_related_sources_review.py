#!/usr/bin/env python3
"""Build reviewed related-sources output from fish related-sources-run-ai-triage.json."""

from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "related-sources-run-ai-triage.json"
OUTPUT_JSON = ROOT / "related-sources-reviewed.json"
OUTPUT_MD = ROOT / "related-sources-review-summary.md"

REVIEW_PROMPT_ID = "fish-related-sources-review-BR1"

REVIEW_STATUS_MAP = {
    "include": "accepted",
    "include_needs_legal_review": "needs_more_research",
    "park_contextual": "parked",
    "exclude": "rejected",
}

SOURCE_REVIEW: dict[str, tuple[str, str, str | None]] = {
    # source_id -> (review_decision, source_role, optional review note)
    # Already triage-accepted
    "lex-6704406fee2f40bd": (
        "include",
        "amendment",
        "EU Exit amendment to Common Fisheries Policy retained law.",
    ),
    "lex-970feca6a6cb49a8": (
        "include",
        "amendment",
        "Follow-up EU Exit amendment to CFP / IUU retained law.",
    ),
    "lex-9cc294c9aca01db8": (
        "include",
        "amendment",
        "Amends IUU catch-certificate implementing rules (1010/2009).",
    ),
    "lex-e765bc0036b75601": (
        "include",
        "amendment",
        "Amends fishery and aquaculture market organisation (1379/2013).",
    ),
    "lex-b5be4907f680752a": (
        "include",
        "amendment",
        "EU Exit amendment to CFP and fisheries control retained law.",
    ),
    "lex-6deac13df85eb723": (
        "include",
        "amendment",
        "Later EU Exit amendment to CFP retained law.",
    ),
    "lex-7d7c8dabf5b23341": (
        "include_needs_legal_review",
        "amendment",
        "Revoked EU Exit food/feed hygiene amendment; confirm current effect on fishery-product hygiene.",
    ),
    "lex-f3dc0b0810b676d5": (
        "include",
        "amendment",
        "EU Exit amendment to specific food hygiene (853/2004 / 2074/2005).",
    ),
    "lex-70eb2c4a481eaedf": (
        "include",
        "amendment",
        "Amends fisheries control regulation (1224/2009) on landing obligation.",
    ),
    "lex-c0936e9ec1554c50": (
        "include",
        "amendment",
        "Dedicated EU Exit amendment to Reg 853/2004 fishery-product hygiene.",
    ),
    # Previously unreviewed (17)
    "lex-4b10f9ce94cc6de3": (
        "include_needs_legal_review",
        "amendment",
        "NI miscellaneous food amendments; fishery-product materiality not confirmed from title alone.",
    ),
    "lex-8d151b0b0bb5ff15": (
        "include_needs_legal_review",
        "amendment",
        "Scotland food hygiene amendment; may touch fishery-product hygiene indirectly.",
    ),
    "lex-913f9e433ac478a5": (
        "park_contextual",
        "framework_context",
        "Windsor Framework retail movement; park until fish/shellfish provisions confirmed.",
    ),
    "lex-a1937e2cabf9d05b": (
        "include",
        "amendment",
        "Sea fisheries EU Exit amendment instrument.",
    ),
    "lex-067d1a8ff1ca8c99": (
        "include",
        "related_supporting",
        "European Maritime and Fisheries Fund grants (Wales).",
    ),
    "lex-2d9bd8f115d0067b": (
        "include",
        "implementing_measure",
        "Scotland order on sea-fishing EU control measures.",
    ),
    "lex-c619d90b6b772116": (
        "include",
        "amendment",
        "IUU fishing vessel provisions for North-East Atlantic.",
    ),
    "lex-151ca7f8501c8266": (
        "include",
        "amendment",
        "ICCAT / Atlantic tuna sea fisheries amendment.",
    ),
    "lex-b6a512185e10664e": (
        "include",
        "amendment",
        "Shark fin removal on fishing vessels (1185/2003).",
    ),
    "lex-caec2afd773e8a91": (
        "include",
        "related_supporting",
        "Emergency measure for scrapping fishing vessels.",
    ),
    "lex-1f8f3283ec08837c": (
        "include_needs_legal_review",
        "amendment",
        "England food/feed hygiene and safety miscellaneous amendments.",
    ),
    "lex-645388a4783af79a": (
        "include_needs_legal_review",
        "amendment",
        "Scotland official feed and food controls miscellaneous amendments.",
    ),
    "lex-40933b6d54a77e62": (
        "include",
        "implementing_measure",
        "Scotland fishery products official controls charges.",
    ),
    "lex-edd3fce31ba4962f": (
        "include_needs_legal_review",
        "amendment",
        "UK food and feed miscellaneous amendments; confirm fishery-product scope.",
    ),
    "lex-6cd739d13947ecca": (
        "include_needs_legal_review",
        "framework_context",
        "General food hygiene framework (852/2004); fishery-product materiality plausible via 853/2004 chain.",
    ),
    "lex-cbea33336a7a255e": (
        "exclude",
        "excluded_false_positive",
        "Bovine products restriction; no fish/shellfish relevance identified.",
    ),
    "lex-0bae7a364b3ed852": (
        "include_needs_legal_review",
        "framework_context",
        "NI food hygiene regulations; general framework with plausible fishery-product application.",
    ),
    # Previously parked
    "lex-87d3d001cfd651ba": (
        "park_contextual",
        "framework_context",
        "Mixed aquatic animal health / seed / plant EU Exit instrument; aquaculture relevance uncertain.",
    ),
    "lex-61a86f9486e7fd6b": (
        "include_needs_legal_review",
        "amendment",
        "Scottish fisheries/aquaculture/marine EU Exit functions; title directly relevant but seed relationship unconfirmed.",
    ),
    "lex-d87bdb1e26a9809c": (
        "exclude",
        "excluded_false_positive",
        "Alternative investment fund managers EU Exit; spurious fisheries query match.",
    ),
    "lex-5d68d58988f41b40": (
        "park_contextual",
        "framework_context",
        "Scotland animal health EU Exit amendment; fish/aquaculture materiality not confirmed.",
    ),
}

RELATIONSHIP_REVIEW: dict[str, tuple[str, str | None, str | None]] = {
    # relationship_id -> (relationship_review, normalized relationship_type or None, optional note append)
}


def short_title(title: str, max_len: int = 72) -> str:
    title = re.sub(r"\s+", " ", title.strip())
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"


def build_source_notes(source: dict, review_note: str | None) -> str:
    parts: list[str] = []
    if review_note:
        parts.append(f"Review decision: {review_note}")
    if source.get("notes"):
        parts.append(source["notes"])
    return "\n\n".join(parts) if parts else ""


def review_relationship(rel: dict) -> dict:
    out = deepcopy(rel)
    rel_id = rel["relationship_id"]
    rel_type = rel["relationship_type"]
    triage_status = rel.get("review_status", "unreviewed")

    if triage_status == "accepted":
        out["relationship_review"] = "accepted"
        out["relationship_type"] = rel_type
    elif triage_status == "needs_more_research":
        out["relationship_review"] = "needs_legal_review"
        if rel_type == "unknown":
            out["relationship_type"] = "unknown_needs_review"
        else:
            out["relationship_type"] = rel_type
        note = (
            "Human review: relationship retained from AI triage needs_more_research; "
            "confirm materiality before treating as settled."
        )
        out["notes"] = f"{rel.get('notes', '')}\n\n{note}".strip() if rel.get("notes") else note
    else:
        out["relationship_review"] = triage_status
        out["relationship_type"] = rel_type

    if rel_id in RELATIONSHIP_REVIEW:
        review, norm_type, note = RELATIONSHIP_REVIEW[rel_id]
        out["relationship_review"] = review
        if norm_type:
            out["relationship_type"] = norm_type
        if note:
            out["notes"] = f"{out.get('notes', '')}\n\n{note}".strip()

    return out


def review_source(source: dict) -> dict:
    out = deepcopy(source)
    source_id = source["source_id"]
    if source_id not in SOURCE_REVIEW:
        raise KeyError(f"Missing review mapping for related source {source_id}")

    review_decision, source_role, review_note = SOURCE_REVIEW[source_id]
    out["review_decision"] = review_decision
    out["source_role"] = source_role
    out["review_status"] = REVIEW_STATUS_MAP[review_decision]
    out["notes"] = build_source_notes(source, review_note) or None
    return out


def main() -> None:
    data = json.loads(INPUT.read_text())

    titles = {s["source_id"]: s["title"] for s in data["seed_sources"]}
    related_reviewed = [review_source(s) for s in data["related_sources"]]
    related_reviewed.sort(key=lambda s: (s["review_decision"], s["title"].lower()))

    relationships_reviewed = [review_relationship(r) for r in data["relationships"]]
    relationships_reviewed.sort(
        key=lambda r: (
            r["relationship_review"],
            r["relationship_type"],
            titles.get(r["from_source_id"], r["from_source_id"]).lower(),
        )
    )

    titles.update({s["source_id"]: s["title"] for s in related_reviewed})

    source_decision_counts = Counter(s["review_decision"] for s in related_reviewed)
    source_role_counts = Counter(s["source_role"] for s in related_reviewed)
    rel_type_counts = Counter(r["relationship_type"] for r in relationships_reviewed)
    rel_review_counts = Counter(r["relationship_review"] for r in relationships_reviewed)

    reviewed = {
        "run_id": data["run_id"],
        "created_at": data["created_at"],
        "category_id": data["category_id"],
        "seed_sources": data["seed_sources"],
        "related_sources": related_reviewed,
        "relationships": relationships_reviewed,
        "warnings": data.get("warnings", []),
        "metadata": {
            **data.get("metadata", {}),
            "review_prompt_id": REVIEW_PROMPT_ID,
            "input_file": "related-sources-run-ai-triage.json",
            "reviewed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "related_source_count": len(related_reviewed),
            "relationship_count": len(relationships_reviewed),
            "related_source_review_counts": dict(
                sorted(Counter(s["review_status"] for s in related_reviewed).items())
            ),
            "relationship_review_counts": dict(sorted(rel_review_counts.items())),
            "source_review_decision_counts": dict(sorted(source_decision_counts.items())),
            "source_role_counts": dict(sorted(source_role_counts.items())),
            "relationship_type_counts": dict(sorted(rel_type_counts.items())),
        },
    }

    OUTPUT_JSON.write_text(json.dumps(reviewed, indent=2, ensure_ascii=False) + "\n")

    lines = [
        "# Fish related sources review summary",
        "",
        f"Reviewed **{len(related_reviewed)}** related sources and **{len(relationships_reviewed)}** "
        f"relationships from `related-sources-run-ai-triage.json`.",
        f"Output: `related-sources-reviewed.json`",
        f"Prompt: `{REVIEW_PROMPT_ID}`",
        "",
        "## Counts by source review_decision",
        "",
        "| review_decision | Count |",
        "| --- | ---: |",
    ]
    for key in [
        "include",
        "include_needs_legal_review",
        "park_contextual",
        "exclude",
    ]:
        lines.append(f"| {key} | {source_decision_counts.get(key, 0)} |")

    lines.extend(["", "## Counts by source_role", "", "| source_role | Count |", "| --- | ---: |"])
    for key, count in sorted(source_role_counts.items()):
        lines.append(f"| {key} | {count} |")

    lines.extend(
        ["", "## Counts by relationship_type", "", "| relationship_type | Count |", "| --- | ---: |"]
    )
    for key, count in sorted(rel_type_counts.items()):
        lines.append(f"| {key} | {count} |")

    lines.extend(
        [
            "",
            "## Counts by relationship_review",
            "",
            "| relationship_review | Count |",
            "| --- | ---: |",
        ]
    )
    for key in ["accepted", "needs_legal_review", "park_contextual", "rejected"]:
        lines.append(f"| {key} | {rel_review_counts.get(key, 0)} |")

    lines.extend(
        [
            "",
            "## Relationships (joined titles)",
            "",
            "| relationship_review | relationship_type | from | to | confidence |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for rel in relationships_reviewed:
        from_title = short_title(titles[rel["from_source_id"]])
        to_title = short_title(titles[rel["to_source_id"]])
        lines.append(
            f"| {rel['relationship_review']} | {rel['relationship_type']} | "
            f"{from_title} | {to_title} | {rel.get('confidence', 'unknown')} |"
        )

    lines.extend(["", "## Unknown / needs legal review relationships", ""])
    flagged_rels = [
        r
        for r in relationships_reviewed
        if r["relationship_review"] == "needs_legal_review"
        or r["relationship_type"] == "unknown_needs_review"
    ]
    if flagged_rels:
        for rel in flagged_rels:
            lines.append(
                f"- **{rel['relationship_type']}** "
                f"(`{rel['relationship_id']}`): "
                f"{short_title(titles[rel['from_source_id']], 60)} → "
                f"{short_title(titles[rel['to_source_id']], 60)}"
            )
            if rel.get("notes"):
                first_line = rel["notes"].split("\n")[0][:140]
                lines.append(f"  - {first_line}")
    else:
        lines.append("- None")

    lines.extend(["", "## Excluded false positives", ""])
    excluded = [s for s in related_reviewed if s["review_decision"] == "exclude"]
    for source in excluded:
        lines.append(f"- {source['title']} (`{source['source_id']}`)")

    lines.extend(["", "## Framework-context sources", ""])
    framework = [
        s
        for s in related_reviewed
        if s["source_role"] == "framework_context" or s["review_decision"] == "park_contextual"
    ]
    for source in framework:
        lines.append(
            f"- **{source['title']}** (`{source['source_id']}`) — "
            f"{source['review_decision']} / {source['source_role']}"
        )

    lines.extend(["", "## Newly reviewed sources (formerly unreviewed)", ""])
    newly = [
        s
        for s in related_reviewed
        if s["source_id"]
        in {
            "lex-4b10f9ce94cc6de3",
            "lex-8d151b0b0bb5ff15",
            "lex-913f9e433ac478a5",
            "lex-a1937e2cabf9d05b",
            "lex-067d1a8ff1ca8c99",
            "lex-2d9bd8f115d0067b",
            "lex-c619d90b6b772116",
            "lex-151ca7f8501c8266",
            "lex-b6a512185e10664e",
            "lex-caec2afd773e8a91",
            "lex-1f8f3283ec08837c",
            "lex-645388a4783af79a",
            "lex-40933b6d54a77e62",
            "lex-edd3fce31ba4962f",
            "lex-6cd739d13947ecca",
            "lex-cbea33336a7a255e",
            "lex-0bae7a364b3ed852",
        }
    ]
    for source in newly:
        lines.append(
            f"- **{source['title']}** (`{source['source_id']}`) — "
            f"{source['review_decision']} / {source['source_role']}"
        )

    OUTPUT_MD.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")
    print("source_review_decision:", dict(source_decision_counts))
    print("relationship_review:", dict(rel_review_counts))


if __name__ == "__main__":
    main()
