#!/usr/bin/env python3
"""Build reviewed source register from fish discovery-run-ai-triage-3.json."""

from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "discovery-run-ai-triage-3.json"
OUTPUT_JSON = ROOT / "source-register-reviewed.json"
OUTPUT_MD = ROOT / "source-register-review-summary.md"

FISH_TITLE_RE = re.compile(
    r"|".join(
        [
            r"\bfish\b",
            r"\bfishes\b",
            r"fisheries",
            r"fishery",
            r"sea[\s-]?fish",
            r"seafood",
            r"shellfish",
            r"aquaculture",
            r"bivalve",
            r"mollusc",
            r"molluscan",
            r"crustacean",
            r"herring",
            r"salmon",
            r"\beel\b",
            r"\beels\b",
            r"oyster",
            r"cockle",
            r"\btrout\b",
            r"lobster",
            r"\bcrab\b",
            r"whiting",
            r"haddock",
            r"\bplaice\b",
            r"fish stock",
            r"fishing opportunit",
            r"landing oblig",
            r"catch certificate",
            r"\biuu\b",
            r"illegal.{0,30}unregulated",
            r"fish labell",
            r"fish health",
            r"fish import",
            r"fish export",
            r"live fish",
            r"fishery product",
            r"fishing engine",
            r"\bnetting\b",
            r"fishmeal",
            r"fish meal",
            r"fish paste",
            r"spreadable fish",
            r"white fish",
            r"sea fishing",
            r"inshore fish",
            r"freshwater fish",
            r"disease.{0,12}fish",
            r"fish disease",
            r"fish buyer",
            r"fish seller",
            r"fish auction",
            r"fish market",
            r"fish wharf",
            r"fish farming",
            r"fishing boat",
            r"fishing vessel",
            r"fishing quota",
            r"fisheries quota",
            r"fish quota",
            r"\bquota\b.{0,20}fish",
            r"fish.{0,20}\bquota\b",
            r"\btac\b",
            r"total allowable catch",
            r"fisheries enforcement",
            r"fishing control",
            r"fishing licence",
            r"fishing license",
            r"fish product",
            r"hygiene.{0,30}fish",
            r"fish.{0,30}hygiene",
            r"products of animal origin",
            r"animal by-product",
            r"processed animal protein",
            r"feeding stuff",
            r"fishmeal",
            r"foyle",
            r"carlingford",
            r"tweed",
            r"poole fishery",
            r"poole harbour fishery",
            r"wash fishery",
            r"colne fishery",
            r"waddeton fishery",
            r"towy fishery",
            r"exe fisheries",
            r"kent and bela fisheries",
            r"ipswich fishery",
            r"solent oyster",
            r"tollesbury",
            r"mersea",
            r"shetland.{0,20}fishery",
            r"solway.{0,20}fishery",
            r"river roach oyster",
            r"great yarmouth fish",
            r"metropolitan markets \(fish",
            r"london river-side fish",
            r"importation of fresh herring",
            r"preserving of fish",
            r"reward to exporter of certain fish",
            r"penalty for using roe",
            r"restriction on importation of live fish",
            r"prohibition of keeping or release of live fish",
            r"prohibition of introduction of fish",
            r"import of live fish",
            r"demersal fish",
            r"immature sea[\s-]?fish",
            r"specified sea fish",
            r"fish sellers",
            r"fish buyers",
            r"fish farming",
            r"fish hatchery",
            r"fish reared",
            r"caviar",
            r"isinglass",
            r"discard plan",
            r"discard.{0,20}fish",
            r"third countr.{0,30}fish",
            r"third countr.{0,30}fishery",
            r"marketing standards.{0,30}fish",
            r"common marketing standards",
            r"control system.{0,30}fisher",
            r"recovery plan.{0,30}fish",
            r"multi-annual plan.{0,30}fish",
            r"multiannual plan.{0,30}fish",
            r"common fisheries policy",
            r"sea-fishing industry",
            r"sea fish industry",
            r"fish industry",
            r"fish sales",
            r"fish labelling",
            r"live bivalve",
            r"paralytic shellfish",
            r"amnesic shellfish",
            r"pollution of fish",
            r"karpfen",
            r"\bcarp\b",
            r"muikku",
            r"viisas",
            r"phú quốc",
        ]
    ),
    re.IGNORECASE,
)

NEEDS_REVIEW_EXCLUDE_RE = re.compile(
    r"|".join(
        [
            r"\bbeer\b",
            r"\bbread\b",
            r"\bspirits\b",
            r"\bthames conservancy\b",
            r"\bharbour act\b",
            r"\bharbours act\b",
            r"\bpier and harbour\b",
            r"city of london \(various powers\)",
            r"great eastern railway",
            r"local government supplemental",
            r"food industry development scheme",
            r"river tummel catchment",
            r"marine licensing \(exempted activities\)",
            r"import duties \(drawback\)",
            r"import duties \(exemptions\)",
            r"import duties \(general\)",
            r"ship.?s report, importation and exportation by sea",
            r"retained eu law \(revocation and reform\) act 2023 \(consequential",
            r"medicines \(medicated animal feeding stuffs\)",
            r"miscellaneous food additives",
            r"food \(licensing of wholesalers\)",
            r"canning of food and feeding stuffs",
            r"fertilisers and feeding stuffs",
            r"weymouth and melcombe regis markets and pier",
            r"sutton harbour act",
            r"hayle harbour act",
            r"lynmouth harbour act",
            r"peterhead harbours act",
            r"agriculture \(miscellaneous provisions\)",
            r"agriculture and fisheries \(financial assistance\)",
            r"organic production and labelling",
            r"placing on the market of a fish \(sardinops",
            r"non-minor amendments to the specification",
            r"temporary increase of official controls",
            r"undesirable substances in animal feed",
            r"transmissible spongiform encephalopathy",
            r"veterinary medicinal products",
        ]
    ),
    re.IGNORECASE,
)

LIKELY_ACCEPT_EXCLUDE_RE = re.compile(
    r"|".join(
        [
            r"food protection \(emergency prohibitions\) \(dounreay nuclear",
            r"white fish subsidy",
            r"white fish and herring subsidies",
            r"white fish \(inshore vessels\) and herring subsidies",
            r"export of goods \(fish\) licence",
            r"fish \(maximum prices\) order",
            r"fish sales \(charges\) order",
            r"fish \(returnable containers\) order",
            r"imported canned fish \(maximum prices\)",
            r"price marking \(fish\) order",
            r"food standards \(fish paste\) order",
            r"fish and fish products \(control of packing\)",
            r"white fish authority \(general levy\)",
            r"fishing boats designation",
            r"fishing boats \(federal republic of germany\) designation",
            r"fishing boats \(france\) designation",
            r"fishing boats \(poland\) designation",
            r"sea-fishing industry \(nets on british and foreign fishing boats\) order 1965",
            r"sea-fishing industry \(immature sea-fish\) amendment order 1954",
            r"feeding stuffs \(manufacture\) order",
            r"imported food \(northern ireland\) regulations 1968",
            r"imported food \(scotland\) regulations",
            r"imported food regulations 1968",
            r"imported food regulations 1984",
            r"official feed and food controls \(wales\) regulations",
            r"official controls \(exemptions from controls at border control posts\)",
            r"contaminants in food \(wales\) regulations",
        ]
    ),
    re.IGNORECASE,
)

ESSENTIAL_PREDECESSOR_RE = re.compile(
    r"|".join(
        [
            r"853/2004",
            r"854/2004",
            r"1380/2013",
            r"1379/2013",
            r"1224/2009",
            r"1005/2008",
            r"2406/96",
            r"2006/88",
            r"Fisheries Act 2020",
            r"Sea Fish \(Conservation\) Act 1967",
            r"Fisheries Act 1981",
            r"1774/2002",
            r"183/2005",
            r"1026/2012",
            r"640/2010",
            r"1236/2010",
            r"2016/429",
            r"2017/625",
            r"2019/6\b",
            r"1069/2009",
            r"178/2002",
            r"Food Safety \(Fishery Products\)",
            r"Food Safety \(Live Bivalve",
            r"Fish Labelling",
            r"Aquatic Animal Health",
            r"Import of Live Fish",
            r"Sea Fishing \(Illegal, Unreported",
            r"Common Fisheries Policy \(Amendment",
            r"Common Fisheries Policy and",
            r"Fisheries Act \(Northern Ireland\) 1966",
            r"Fish Industry Act \(Northern Ireland\) 1972",
            r"Aquaculture and Fisheries \(Scotland\) Act",
        ]
    ),
    re.IGNORECASE,
)

FRAMEWORK_PARK_IDS = {
    "lex-e3ab476f94866ade",  # Reg 1069/2009 ABP - fish by-products framework
}

ANNUAL_FISHING_RE = re.compile(
    r"fixing (for|the fishing opportunities)|"
    r"fishing opportunities (for|and associated)|"
    r"establishing a prohibition of fishing|"
    r"establishing a discard plan|"
    r"prohibition of fishing for .+ in .+ waters",
    re.IGNORECASE,
)

HISTORICAL_MARKER_RE = re.compile(
    r"\(repealed\)|\(revoked\)|\(repeal\)|repealing regulation|revoking regulation",
    re.IGNORECASE,
)


def is_historical(title: str, temporal_status: str | None) -> bool:
    title_lower = title.lower()
    if temporal_status == "historical":
        return True
    if HISTORICAL_MARKER_RE.search(title):
        return True
    if ANNUAL_FISHING_RE.search(title):
        return True
    if re.search(r"regulation as to importation of fresh", title_lower):
        return True
    if re.search(r"subsidy|subsidies", title_lower):
        return True
    if re.search(r"order,? \d{4}$|act,? \d{4}$|act \d{4}\b", title_lower):
        years = [int(y) for y in re.findall(r"\b(1[0-9]{3}|20[0-1][0-9])\b", title)]
        if years and max(years) < 1980 and "fisheries act" not in title_lower:
            return True
    return False


def is_essential_predecessor(title: str) -> bool:
    return bool(ESSENTIAL_PREDECESSOR_RE.search(title))


def title_concerns_fish(title: str) -> bool:
    if NEEDS_REVIEW_EXCLUDE_RE.search(title):
        return False
    return bool(FISH_TITLE_RE.search(title))


def build_notes(candidate: dict, review_note: str | None = None) -> str:
    triage = candidate.get("ai_triage") or {}
    parts = []
    if review_note:
        parts.append(f"Review decision: {review_note}")
    if triage.get("rationale"):
        parts.append(f"AI triage rationale: {triage['rationale']}")
    for key, label in [
        ("relevance", "AI triage relevance"),
        ("review_priority", "AI triage review_priority"),
        ("recommended_action", "AI triage recommended_action"),
    ]:
        if triage.get(key):
            parts.append(f"{label}: {triage[key]}")
    if triage.get("supporting_signals"):
        parts.append(
            "Supporting signals:\n- " + "\n- ".join(triage["supporting_signals"])
        )
    if triage.get("false_positive_risks"):
        parts.append(
            "False positive risks:\n- " + "\n- ".join(triage["false_positive_risks"])
        )
    if triage.get("evidence_limitations"):
        parts.append(
            "Evidence limitations:\n- " + "\n- ".join(triage["evidence_limitations"])
        )
    return "\n\n".join(parts)


def prepare_entry(
    candidate: dict,
    review_status: str,
    review_note: str | None = None,
    temporal_override: str | None = None,
) -> dict:
    entry = deepcopy(candidate)
    entry["review_status"] = review_status
    entry["notes"] = build_notes(candidate, review_note)
    if temporal_override:
        entry["temporal_status"] = temporal_override
    elif review_status == "historical_context":
        entry["temporal_status"] = "historical"
    return entry


def classify_candidate(candidate: dict) -> tuple[str, str | None]:
    triage = candidate.get("ai_triage") or {}
    priority = triage.get("review_priority", "")
    title = candidate.get("title", "")
    source_id = candidate.get("source_id", "")
    temporal = candidate.get("temporal_status")

    if priority == "likely_reject":
        return "rejected", "Excluded per AI triage likely_reject."

    if priority == "park_contextual":
        if source_id in FRAMEWORK_PARK_IDS:
            return "parked", "Parked as important framework context (animal by-products)."
        return "parked", "Parked per AI triage park_contextual; not principal fish source."

    if priority == "likely_accept":
        if LIKELY_ACCEPT_EXCLUDE_RE.search(title):
            if re.search(
                r"importation of fresh herring|price marking \(fish\)|export of goods \(fish\)",
                title,
                re.I,
            ):
                return (
                    "historical",
                    "Historical fish trade control; retained in historical context only.",
                )
            if is_historical(title, temporal) and not is_essential_predecessor(title):
                return (
                    "historical",
                    "Historical administrative or price-control instrument; retained for context only.",
                )
            return (
                "parked",
                "Excluded from principal register: general official-control or incidental administrative instrument.",
            )

        historical = is_historical(title, temporal)
        if historical and not is_essential_predecessor(title):
            return "historical", "Historical or superseded instrument; retained for context only."

        return "accepted", "Accepted per AI triage likely_accept."

    if priority == "needs_human_review":
        if not title_concerns_fish(title):
            return "rejected", "Excluded: needs_human_review but title does not clearly concern fish/fisheries scope."

        historical = is_historical(title, temporal)
        uncertain_markers = [
            "animal by-product",
            "processed animal protein",
            "feeding stuff",
            "products of animal origin",
            "organic production",
            "collection, management and use of data",
            "framework for the collection",
            "fisheries control programme",
            "revoked",
            "repealed",
            "provisional order",
            "private act",
            "harbour",
            "pier",
            "markets and pier",
        ]
        title_lower = title.lower()
        is_uncertain = any(m in title_lower for m in uncertain_markers)

        if historical and not is_essential_predecessor(title):
            if is_uncertain:
                return "uncertain_historical", "Historical instrument included tentatively; needs legal review for current applicability."
            return "historical", "Historical instrument with clear fish/fisheries subject matter."

        if is_uncertain:
            return "uncertain", "Accepted tentatively from needs_human_review; legal review recommended."

        return "accepted", "Accepted from needs_human_review where title clearly concerns fish/fisheries."

    return "rejected", f"Unhandled triage priority: {priority}"


def principal_score(entry: dict) -> tuple[int, str]:
    title = entry.get("title", "").lower()
    score = 0
    if entry.get("review_status") != "accepted":
        return (0, entry.get("title", ""))
    if re.search(r"fisheries act 2020|common fisheries policy|1379/2013|1380/2013|1224/2009|1005/2008|853/2004|854/2004", title):
        score += 100
    if re.search(r"aquaculture|fish labelling|fishery products|live bivalve|iuu|illegal, unreported", title):
        score += 80
    if re.search(r"sea fish \(conservation\)|fisheries act 1981|fish health|aquatic animal health", title):
        score += 70
    if "assimilated" in (entry.get("source_type") or ""):
        score += 10
    if entry.get("ai_triage", {}).get("relevance") == "high":
        score += 20
    return (-score, entry.get("title", ""))


def main() -> None:
    with INPUT.open() as f:
        data = json.load(f)

    candidates = data["candidate_sources"]
    accepted: list[dict] = []
    historical: list[dict] = []
    parked: list[dict] = []
    rejected: list[dict] = []
    uncertain: list[dict] = []
    decision_counts: Counter[str] = Counter()

    for candidate in candidates:
        bucket, note = classify_candidate(candidate)
        decision_counts[bucket] += 1

        if bucket == "accepted":
            accepted.append(prepare_entry(candidate, "accepted", note))
        elif bucket == "historical":
            historical.append(prepare_entry(candidate, "historical_context", note))
        elif bucket == "parked":
            parked.append(prepare_entry(candidate, "parked", note))
        elif bucket == "rejected":
            rejected.append(prepare_entry(candidate, "rejected", note))
        elif bucket == "uncertain":
            uncertain.append(prepare_entry(candidate, "uncertain", note))
            accepted.append(prepare_entry(candidate, "accepted", note + " [flagged uncertain]"))
        elif bucket == "uncertain_historical":
            uncertain.append(prepare_entry(candidate, "uncertain", note))
            historical.append(prepare_entry(candidate, "historical_context", note + " [flagged uncertain]"))

    accepted.sort(key=principal_score)
    historical.sort(key=lambda e: e.get("title", ""))
    parked.sort(key=lambda e: e.get("title", ""))
    rejected.sort(key=lambda e: e.get("title", ""))
    uncertain.sort(key=lambda e: e.get("title", ""))

    register = {
        "register_id": "ada-register-fish",
        "category_id": "fish",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "accepted_sources": accepted,
        "historical_context": historical,
        "parked_sources": parked,
        "rejected_sources": rejected,
        "uncertain_sources": uncertain,
        "metadata": {
            "discovery_run_id": data.get("run_id"),
            "source_discovery_file": "discovery-run-ai-triage-3.json",
            "review_prompt_id": "fish-source-register-review-BR1",
            "candidate_count": len(candidates),
            "accepted_count": len(accepted),
            "historical_context_count": len(historical),
            "parked_count": len(parked),
            "rejected_count": len(rejected),
            "uncertain_count": len(uncertain),
            "review_decision_counts": dict(decision_counts),
        },
    }

    OUTPUT_JSON.write_text(json.dumps(register, indent=2, ensure_ascii=False) + "\n")

    principal = accepted[:25]
    lines = [
        "# Fish source register review summary",
        "",
        f"Reviewed **{len(candidates)}** discovery candidates from `discovery-run-ai-triage-3.json`.",
        f"Output: `source-register-reviewed.json`",
        "",
        "## Counts by review decision",
        "",
        "| Decision | Count |",
        "| --- | ---: |",
        f"| Accepted (principal) | {len(accepted)} |",
        f"| Historical context | {len(historical)} |",
        f"| Parked (framework/context) | {len(parked)} |",
        f"| Rejected (false positives) | {len(rejected)} |",
        f"| Uncertain (needs legal review) | {len(uncertain)} |",
        "",
        "### AI triage input breakdown",
        "",
        "| AI review_priority | Count in discovery |",
        "| --- | ---: |",
    ]
    triage_input = Counter(
        c.get("ai_triage", {}).get("review_priority", "missing") for c in candidates
    )
    for key in ["likely_accept", "needs_human_review", "park_contextual", "likely_reject"]:
        lines.append(f"| {key} | {triage_input[key]} |")

    lines.extend(["", "## Principal candidate sources", ""])
    for entry in principal:
        triage = entry.get("ai_triage", {})
        lines.append(
            f"- **{entry['title']}** (`{entry['source_id']}`) — "
            f"{triage.get('relationship_to_category', 'n/a')}, "
            f"AI relevance: {triage.get('relevance', 'n/a')}"
        )

    lines.extend(["", "## Parked framework/context sources", ""])
    for entry in parked:
        lines.append(f"- {entry['title']} (`{entry['source_id']}`)")

    lines.extend(["", "## Excluded false positives", ""])
    for entry in rejected[:30]:
        triage = entry.get("ai_triage", {})
        lines.append(
            f"- {entry['title']} (`{entry['source_id']}`) — "
            f"{triage.get('rationale', '')[:120]}..."
        )
    if len(rejected) > 30:
        lines.append(f"- …and {len(rejected) - 30} more in `rejected_sources`")

    lines.extend(["", "## Uncertain items needing legal review", ""])
    for entry in uncertain:
        triage = entry.get("ai_triage", {})
        lines.append(
            f"- **{entry['title']}** (`{entry['source_id']}`) — "
            f"{entry.get('notes', '').split(chr(10))[0]}"
        )

    OUTPUT_MD.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")
    print("Decision counts:", dict(decision_counts))


if __name__ == "__main__":
    main()
