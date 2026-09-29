#!/usr/bin/env python3
"""Build a small principal-source pilot register from the flattened fish register."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
ADA_ROOT = ROOT.parent.parent
FLAT_INPUT = ROOT / "source-register-expanded-flat.json"
OUTPUT_JSON = ROOT / "source-register-pilot-principal.json"
OUTPUT_MD = ROOT / "source-register-pilot-principal-summary.md"
REGISTER_ID = "ada-register-fish-pilot-principal"
PILOT_PROMPT_ID = "fish-pilot-priority-order-BR1"

REGISTER_BUCKETS = (
    "accepted_sources",
    "historical_context",
    "parked_sources",
    "rejected_sources",
    "uncertain_sources",
)

FLAT_ONLY_FIELDS = frozenset({"review_decision", "source_role", "source_bucket"})

# Flat export buckets mapped onto reviewed SourceRegister buckets.
FLAT_BUCKET_TO_REGISTER: dict[str, str] = {
    "accepted_sources": "accepted_sources",
    "included_related_sources": "accepted_sources",
    "historical_context": "historical_context",
    "uncertain_sources": "uncertain_sources",
    "parked_sources": "parked_sources",
    "rejected_sources": "rejected_sources",
}

# Ordered principal targets: (selection_key, title_matcher, selection_rationale).
# Order is intentional — Law Proposition Extractor --max-sources N with priority_policy raw takes the first N
# principal_sources from the bundle, so current core fisheries instruments come first.
PRINCIPAL_TARGETS: list[tuple[str, Callable[[str], bool], str]] = [
    (
        "fisheries_act_2020",
        lambda t: t == "Fisheries Act 2020",
        "Core UK fisheries framework Act; primary post-Brexit domestic fisheries legislation.",
    ),
    (
        "eu_1380_2013",
        lambda t: "1380/2013" in t
        and "Common Fisheries Policy" in t
        and not t.lower().startswith("regulation (eu) 2015"),
        "Assimilated EU Common Fisheries Policy principal regulation.",
    ),
    (
        "eu_1224_2009",
        lambda t: t.startswith("Council Regulation (EC) No 1224/2009"),
        "EU fisheries control and enforcement system — catch certificates, inspections, VMS.",
    ),
    (
        "eu_1005_2008",
        lambda t: t.startswith("Council Regulation (EC) No 1005/2008"),
        "IUU fishing and catch-certification regime for fishery products trade.",
    ),
    (
        "eu_1379_2013",
        lambda t: "1379/2013" in t
        and "common organisation" in t.lower()
        and not t.lower().startswith("regulation (eu) 2020"),
        "Assimilated EU common organisation of markets in fishery and aquaculture products.",
    ),
    (
        "fish_labelling_2013",
        lambda t: t == "The Fish Labelling Regulations 2013",
        "Key retained fish marketing/labelling instrument (England-wide SI).",
    ),
    (
        "eu_853_2004",
        lambda t: t.startswith("Regulation (EC) No 853/2004")
        and "explanatory" not in t.lower(),
        "Specific hygiene rules for food of animal origin — core seafood processing hygiene.",
    ),
    (
        "marine_and_coastal_access_act_2009",
        lambda t: t == "Marine and Coastal Access Act 2009",
        "Marine planning, licensing and inshore fisheries management framework.",
    ),
    (
        "aquatic_animal_health_2006_88",
        lambda t: t.startswith(
            "Council Directive 2006/88/EC of 24 October 2006 on animal health requirements"
        ),
        "Principal EU aquaculture and aquatic animal health instrument.",
    ),
    (
        "fisheries_act_1981",
        lambda t: t == "Fisheries Act 1981",
        "Long-standing UK fisheries principal Act covering licensing, enforcement and sea fish industry powers.",
    ),
    (
        "sea_fish_industry_act_1959",
        lambda t: t == "Sea Fish Industry Act 1959",
        "Foundational Sea Fish Industry Authority / levy framework explicitly named in pilot scope.",
    ),
    (
        "sea_fish_industry_act_1973",
        lambda t: t == "Sea Fish Industry Act 1973",
        "Principal Sea Fish Industry Act amendment era instrument; supports industry governance lineage.",
    ),
    (
        "sea_fisheries_shellfish_act_1967",
        lambda t: t == "Sea Fisheries (Shellfish) Act 1967",
        "Shellfish fisheries licensing and bed regulation — direct shellfish scope.",
    ),
]

# Amendment instruments paired to principals for relationship testing (deterministic order).
AMENDMENT_SOURCE_IDS: list[tuple[str, str]] = [
    (
        "lex-c0936e9ec1554c50",
        "UK EU Exit amendment directly transposing Reg 853/2004 seafood hygiene — tests hygiene amendment chain.",
    ),
    (
        "lex-70eb2c4a481eaedf",
        "EU 2015/812 landing-obligation amendment to Reg 1224/2009 — tests EU-to-EU amendment relationship.",
    ),
]

# Important off-pilot amendments referenced by preserved relationships (stub endpoints only).
RELATIONSHIP_STUB_AMENDMENT_IDS = (
    "lex-6704406fee2f40bd",  # CFP (Amendment etc.) (EU Exit) Regulations 2019
    "lex-b5be4907f680752a",  # CFP and Animals (Amendment etc.) (EU Exit) Regulations 2019
)

EXTRACTION_RISKS: dict[str, str] = {
    "fisheries_act_2020": "Large framework Act; extraction may surface cross-cutting marine/conservation provisions beyond trade.",
    "fisheries_act_1981": "Long-lived Act with extensive amendments; temporal_status unknown in register.",
    "sea_fish_industry_act_1959": "Marked historical in register; may yield superseded industry-governance provisions.",
    "sea_fish_industry_act_1973": "Marked historical; overlapping Sea Fish Industry Authority powers with 1959 Act.",
    "sea_fisheries_shellfish_act_1967": "Marked historical; devolved shellfish licensing may need jurisdiction disambiguation.",
    "marine_and_coastal_access_act_2009": "Broad marine statute — fisheries provisions mixed with access/conservation.",
    "eu_1380_2013": "Assimilated EU law; post-Brexit domestic modifications may not be reflected in Lex metadata.",
    "eu_1379_2013": "Market organisation rules overlap with general food marketing — watch for non-fishery COM articles.",
    "eu_1224_2009": "Control-system regulation is lengthy; implementing/delegated acts mostly excluded from pilot.",
    "eu_1005_2008": "IUU/catch-certificate rules cross-cut trade and enforcement; third-country lists excluded.",
    "eu_853_2004": "General animal-origin hygiene — fish-specific annexes need careful scoping.",
    "fish_labelling_2013": "England instrument; devolved labelling SIs excluded — jurisdiction fragmentation risk.",
    "aquatic_animal_health_2006_88": "Aquaculture health scope may pull disease-control provisions beyond food trade.",
    "lex-c0936e9ec1554c50": "Amendment-only SI — extraction depends on reading amendments against Reg 853/2004 base text.",
    "lex-70eb2c4a481eaedf": "Amends multiple CFP regulations; fish-specific landing-obligation articles need targeting.",
}


def short_title(title: str, max_len: int = 88) -> str:
    title = re.sub(r"\s+", " ", title.strip())
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"


def count_by(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(item.get(field, "unknown") for item in items).items()))


def pick_principal_source(
    sources: list[dict[str, Any]],
    matcher: Callable[[str], bool],
) -> dict[str, Any] | None:
    hits = [s for s in sources if matcher(s["title"])]
    if not hits:
        return None
    return sorted(
        hits,
        key=lambda s: (
            s.get("review_decision") not in {"include", "include_needs_legal_review"},
            s.get("source_role") != "related_principal",
            s.get("temporal_status") == "historical",
            s["title"].lower(),
        ),
    )[0]


def build_selection(
    flat: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    sources_by_id = {s["source_id"]: s for s in flat["sources"]}
    ordered: list[dict[str, Any]] = []
    selection_keys: dict[str, str] = {}
    rationales: dict[str, str] = {}

    for key, matcher, rationale in PRINCIPAL_TARGETS:
        source = pick_principal_source(flat["sources"], matcher)
        if source is None:
            raise ValueError(f"No source matched pilot target: {key}")
        ordered.append(deepcopy(source))
        selection_keys[source["source_id"]] = key
        rationales[source["source_id"]] = rationale

    for source_id, rationale in AMENDMENT_SOURCE_IDS:
        source = sources_by_id.get(source_id)
        if source is None:
            raise ValueError(f"Amendment source not found in flat register: {source_id}")
        if source.get("review_decision") not in {"include", "include_needs_legal_review"}:
            raise ValueError(f"Amendment source excluded by review decision: {source_id}")
        ordered.append(deepcopy(source))
        selection_keys[source_id] = source_id
        rationales[source_id] = rationale

    return ordered, selection_keys, rationales


def register_bucket_for_flat_source(source: dict[str, Any]) -> str:
    flat_bucket = source.get("source_bucket", "accepted_sources")
    return FLAT_BUCKET_TO_REGISTER.get(flat_bucket, "accepted_sources")


def to_candidate_source(source: dict[str, Any], *, register_bucket: str) -> dict[str, Any]:
    """Normalise a flat export row into a reviewed SourceRegister CandidateSource."""
    entry = {key: value for key, value in deepcopy(source).items() if key not in FLAT_ONLY_FIELDS}

    if not entry.get("source_system") and entry.get("canonical_uri"):
        entry["source_system"] = "lex"

    if register_bucket == "historical_context":
        entry["review_status"] = "historical_context"
        entry["temporal_status"] = "historical"
    elif register_bucket == "uncertain_sources":
        entry["review_status"] = "needs_more_research"
    elif register_bucket == "parked_sources":
        entry["review_status"] = "parked"
    elif register_bucket == "rejected_sources":
        entry["review_status"] = "rejected"

    return entry


def bucket_selected_sources(
    flat_sources: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in REGISTER_BUCKETS}

    for source in flat_sources:
        register_bucket = register_bucket_for_flat_source(source)
        buckets[register_bucket].append(
            to_candidate_source(source, register_bucket=register_bucket)
        )

    # Preserve pilot priority order in accepted_sources (used for principal_sources bundle order).
    buckets["historical_context"].sort(key=lambda item: item.get("title", ""))
    buckets["parked_sources"].sort(key=lambda item: item.get("title", ""))
    buckets["rejected_sources"].sort(key=lambda item: item.get("title", ""))
    buckets["uncertain_sources"].sort(key=lambda item: item.get("title", ""))
    return buckets


def filter_relationships(
    relationships: list[dict[str, Any]],
    selected_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full: list[dict[str, Any]] = []
    stubs: list[dict[str, Any]] = []
    for rel in relationships:
        from_id = rel["from_source_id"]
        to_id = rel["to_source_id"]
        from_in = from_id in selected_ids
        to_in = to_id in selected_ids
        if from_in and to_in:
            full.append(deepcopy(rel))
        elif from_in ^ to_in:
            other_id = to_id if from_in else from_id
            if other_id in RELATIONSHIP_STUB_AMENDMENT_IDS:
                stub = deepcopy(rel)
                stub["relationship_stub"] = True
                stub["stub_reason"] = (
                    "Pilot retains principal endpoint only; amendment instrument omitted "
                    "from pilot but preserved for downstream relationship awareness."
                )
                stubs.append(stub)
    full.sort(key=lambda r: r.get("relationship_id", ""))
    stubs.sort(key=lambda r: r.get("relationship_id", ""))
    return full, stubs


def build_source_register(
    flat: dict[str, Any],
    flat_sources: list[dict[str, Any]],
    selection_keys: dict[str, str],
    relationships: list[dict[str, Any]],
    stubs: list[dict[str, Any]],
) -> dict[str, Any]:
    buckets = bucket_selected_sources(flat_sources)
    bucket_counts = {name: len(buckets[name]) for name in REGISTER_BUCKETS}

    return {
        "register_id": REGISTER_ID,
        "category_id": flat["category_id"],
        "created_at": flat["created_at"],
        "accepted_sources": buckets["accepted_sources"],
        "historical_context": buckets["historical_context"],
        "parked_sources": buckets["parked_sources"],
        "rejected_sources": buckets["rejected_sources"],
        "uncertain_sources": buckets["uncertain_sources"],
        "metadata": {
            "pilot_prompt_id": PILOT_PROMPT_ID,
            "pilot_source_file": "source-register-expanded-flat.json",
            "schema_reference": "source-register-reviewed.json",
            "input_flat_source_count": flat["metadata"].get(
                "flattened_source_count", len(flat["sources"])
            ),
            "pilot_source_count": len(flat_sources),
            "accepted_count": bucket_counts["accepted_sources"],
            "historical_context_count": bucket_counts["historical_context"],
            "parked_count": bucket_counts["parked_sources"],
            "rejected_count": bucket_counts["rejected_sources"],
            "uncertain_count": bucket_counts["uncertain_sources"],
            "relationship_count": len(relationships),
            "relationship_stub_count": len(stubs),
            "selection_keys": {sid: selection_keys[sid] for sid in sorted(selection_keys)},
            "pilot_source_metadata": {
                source["source_id"]: {
                    "selection_key": selection_keys[source["source_id"]],
                    "source_role": source.get("source_role"),
                    "flat_source_bucket": source.get("source_bucket"),
                    "register_bucket": register_bucket_for_flat_source(source),
                }
                for source in flat_sources
            },
            "relationships": relationships,
            "relationship_stubs": stubs,
        },
    }


def write_summary(
    register: dict[str, Any],
    flat_sources: list[dict[str, Any]],
    selection_keys: dict[str, str],
    rationales: dict[str, str],
) -> str:
    relationships = register["metadata"].get("relationships", [])
    stubs = register["metadata"].get("relationship_stubs", [])
    meta = register["metadata"]

    lines = [
        "# Fish pilot principal source register summary",
        "",
        "Pilot subset of `source-register-expanded-flat.json` for Law Proposition Extractor/Proposition Matcher extraction.",
        "Output: `source-register-pilot-principal.json`",
        f"Prompt: `{PILOT_PROMPT_ID}`",
        f"Register id: `{register['register_id']}`",
        "",
        "## Selection counts",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Selected sources | {meta['pilot_source_count']} |",
        f"| Accepted sources | {meta['accepted_count']} |",
        f"| Historical context | {meta['historical_context_count']} |",
        f"| Uncertain sources | {meta['uncertain_count']} |",
        f"| Parked sources | {meta['parked_count']} |",
        f"| Rejected sources | {meta['rejected_count']} |",
        f"| Full relationships (both endpoints in pilot) | {meta['relationship_count']} |",
        f"| Relationship stubs (principal ↔ off-pilot amendment) | {meta['relationship_stub_count']} |",
        f"| Flat register sources (input) | {meta['input_flat_source_count']} |",
        "",
        "## Counts by source_role",
        "",
        "| source_role | Count |",
        "| --- | ---: |",
    ]
    for key, count in count_by(flat_sources, "source_role").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(
        ["", "## Counts by temporal_status", "", "| temporal_status | Count |", "| --- | ---: |"]
    )
    for key, count in count_by(flat_sources, "temporal_status").items():
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## Selected source titles", ""])
    for source in flat_sources:
        lines.append(f"- {source['title']} (`{source['source_id']}`)")

    lines.extend(["", "## Why each source was selected", ""])
    for source in flat_sources:
        sid = source["source_id"]
        key = selection_keys.get(sid, sid)
        lines.append(f"### {short_title(source['title'], 72)}")
        lines.append("")
        lines.append(f"- **source_id:** `{sid}`")
        lines.append(f"- **selection_key:** `{key}`")
        lines.append(f"- **source_role:** {source.get('source_role', 'unknown')}")
        lines.append(f"- **register_bucket:** {register_bucket_for_flat_source(source)}")
        lines.append(f"- **temporal_status:** {source.get('temporal_status', 'unknown')}")
        lines.append(f"- **Rationale:** {rationales[sid]}")
        risk = EXTRACTION_RISKS.get(key) or EXTRACTION_RISKS.get(sid)
        if risk:
            lines.append(f"- **Extraction risk:** {risk}")
        lines.append("")

    lines.extend(["## Relationships (both endpoints in pilot)", ""])
    if relationships:
        for rel in relationships:
            lines.append(
                f"- `{rel['from_source_id']}` → `{rel['to_source_id']}` "
                f"({rel.get('relationship_type', 'unknown')})"
            )
    else:
        lines.append("- _None_")

    lines.extend(["", "## Relationship stubs (off-pilot amendment endpoint)", ""])
    if stubs:
        for rel in stubs:
            lines.append(
                f"- `{rel['from_source_id']}` → `{rel['to_source_id']}` "
                f"({rel.get('relationship_type', 'unknown')}) — stub"
            )
    else:
        lines.append("- _None_")

    return "\n".join(lines) + "\n"


def validate_source_register(path: Path, *, bundle_output: Path) -> None:
    from law_discovery.models import load_source_register

    register = load_source_register(path)
    if register.register_id != REGISTER_ID:
        raise ValueError(f"Unexpected register_id: {register.register_id!r}")

    result = subprocess.run(
        [
            "uv",
            "run",
            "law-discovery",
            "make-source-bundle",
            str(path),
            "--output",
            str(bundle_output),
        ],
        cwd=ADA_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "make-source-bundle failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )

    print(result.stdout.strip())


def main() -> None:
    flat = json.loads(FLAT_INPUT.read_text())
    flat_sources, selection_keys, rationales = build_selection(flat)
    selected_ids = {s["source_id"] for s in flat_sources}
    relationships, stubs = filter_relationships(flat["relationships"], selected_ids)

    register = build_source_register(
        flat,
        flat_sources,
        selection_keys,
        relationships,
        stubs,
    )

    OUTPUT_JSON.write_text(json.dumps(register, indent=2, ensure_ascii=False) + "\n")
    OUTPUT_MD.write_text(write_summary(register, flat_sources, selection_keys, rationales))

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")
    print(
        "pilot sources:",
        len(flat_sources),
        "accepted:",
        len(register["accepted_sources"]),
        "historical:",
        len(register["historical_context"]),
        "relationships:",
        len(relationships),
        "stubs:",
        len(stubs),
    )

    with tempfile.NamedTemporaryFile(
        suffix=".bundle.json",
        prefix="source-register-pilot-principal-",
        dir=ROOT,
        delete=True,
    ) as bundle_file:
        validate_source_register(OUTPUT_JSON, bundle_output=Path(bundle_file.name))
    print("Validated SourceRegister via make-source-bundle")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)
