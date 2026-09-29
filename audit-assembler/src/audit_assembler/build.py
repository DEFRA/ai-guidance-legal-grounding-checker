"""Shape upstream pipeline outputs into the content-audit frontend data files.

Pure transform: every function here takes already-loaded JSON and returns plain
data — no file or network IO (the CLI owns that). This keeps the join logic
unit-testable and the data lineage explicit.

Identity model (pipeline-native keys, one file per entity):
  - pages            keyed by ``content_id`` (gov.uk content id)
  - legislation      keyed by ``source_record_id`` (``lex-…``)
  - law propositions keyed by ``id`` (Law Proposition Extractor ``prop:…``)
  - guidance props   keyed by ``id`` (native Guidance Proposition Extractor id from Proposition Matcher's output)
  - matches          keyed by a derived stable ``id`` (``m-…``) for feedback

No silent fallbacks: anything that can't be derived is recorded in ``warnings``
and either left null or dropped with an explicit message.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from .law_candidates import locator_from_law_row
from .legislation_gov_uk_url import legislation_provision_url
from .match_summary import (
    build_guidance_proposition_match_summaries,
    distinct_matches_by_law_id,
    is_reportable_relationship,
    law_proposition_id,
    normalise_relationship,
)
from .validate_match_processing import (
    count_historic_backfill_rows,
    validate_matcher_match_processing,
)

# Proposition Matcher's six-way taxonomy, normalised onto the frontend's status values.
# CONFLICT is the only rename (the prompt sometimes emits the singular).
# These are pair-level outcomes only — proposition-level coverage lives in
# ``guidance-proposition-match-summaries.json`` (see match_summary.py).
# Full reportable pairs (not just top match) live in
# ``guidance-proposition-law-comparisons.json``.
RELATIONSHIP_NORMALISE = {
    "GROUNDED": "GROUNDED",
    "GUIDANCE_INCOMPLETE": "GUIDANCE_INCOMPLETE",
    "GUIDANCE_MISSING": "GUIDANCE_MISSING",
    "GUIDANCE_BROADER": "GUIDANCE_BROADER",
    "UNGROUNDED": "UNGROUNDED",
    "CONFLICT": "CONFLICTS",
    "CONFLICTS": "CONFLICTS",
}

STATUS_ORDER = [
    "UNGROUNDED",
    "GUIDANCE_BROADER",
    "GUIDANCE_INCOMPLETE",
    "NO_MATCH",
    "GROUNDED",
    "CONFLICTS",
    "GUIDANCE_MISSING",
]


def _sha8(*parts: str) -> str:
    return hashlib.sha1("\0".join(parts).encode()).hexdigest()[:8]


def _relevance_score(meta: dict, category: str) -> float | None:
    """Guidance Relevance Filter's per-category relevance score. New runs use ``scores``; older
    runs used ``cosine_score`` — accept either, prefer the new key."""
    for key in ("scores", "cosine_score"):
        block = meta.get(key)
        if isinstance(block, dict) and category in block:
            return block[category]
    return None


def build_pages(
    page_records: list[dict],
    category: str,
    warnings: list[str],
    title_by_url: dict[str, str] | None = None,
) -> list[dict]:
    """Audited pages, sorted by URL. Prefer content_id; keep pages without one.

    Title prefers the upstream metadata, falling back to the authoritative gov.uk
    content-API title (``title_by_url``, from the reading-age fetch) when the corpus
    carried none — without it the frontend has no link text to click.
    """
    title_by_url = title_by_url or {}
    pages = []
    for item in sorted(page_records, key=lambda p: p["url"]):
        content_id = item.get("content_id") or None
        if not content_id:
            warnings.append(f"page has no content_id: {item.get('url')}")
        md = item.get("meta_data", {}) or {}
        title = md.get("title") or title_by_url.get(item["url"]) or ""
        if not title:
            warnings.append(f"page has no title from corpus or content API: {item['url']}")
        pages.append({
            "content_id": content_id,
            "category": category,
            "url": item["url"],
            "title": title,
            "description": md.get("description", ""),
            "document_type": md.get("document_type"),
        })
    return pages


def build_guidance_propositions(
    matcher_output: list[dict],
    url_to_content_id: dict[str, str],
    warnings: list[str],
) -> tuple[list[dict], list[str | None]]:
    """Flatten Proposition Matcher's guidance propositions, keyed by their native id.

    Proposition Matcher's results.json carries the stable Guidance Proposition Extractor id on each entry, so we use
    it directly. Prefer ``content_id`` on the Proposition Matcher entry, falling back to the
    URL→content_id map from audited pages. Returns the rows plus a per-output-row
    id list (aligned to ``matcher_output``) for the matches builder to reuse.
    """
    rows: list[dict] = []
    row_ids: list[str | None] = []
    seen_ids: set[str] = set()
    missing_id = 0
    for entry in matcher_output:
        url = entry["url"]
        text = entry["proposition_text"]
        content_id = entry.get("content_id") or url_to_content_id.get(url)
        if not content_id:
            warnings.append(f"guidance proposition source URL not in audited pages: {url}")
            row_ids.append(None)
            continue
        gp_id = entry.get("id")
        if not gp_id:
            missing_id += 1
            row_ids.append(None)
            continue
        row_ids.append(gp_id)
        if gp_id not in seen_ids:
            seen_ids.add(gp_id)
            rows.append({
                "id": gp_id,
                "content_id": content_id,
                "proposition_text": text,
                "source_paragraphs": entry.get("source_paragraphs") or [],
                "section_locator": entry.get("section_locator") or "",
            })
    if missing_id:
        warnings.append(f"{missing_id} guidance propositions had no id in the Proposition Matcher output")
    return rows, row_ids


def build_legislation(legislation_seed: list[dict], category: str) -> list[dict]:
    """Re-key the legislation seed by source_record_id (drops the integer id)."""
    return [
        {
            "source_record_id": law["source_record_id"],
            "category": category,
            "name": law["name"],
            "url": law.get("url"),
        }
        for law in legislation_seed
        if law.get("source_record_id")
    ]


def build_legislation_propositions(
    law_input: list[dict],
    legacy_law_props: list[dict],
    known_source_record_ids: set[str],
    warnings: list[str],
    *,
    legislation_url_by_srid: dict[str, str | None] | None = None,
) -> list[dict]:
    """Law propositions keyed by Law Proposition Extractor ``prop:`` / ``bcand:`` id.

    ``graph_node`` in the Proposition Matcher law input is a rename of Law Proposition Extractor's
    ``source_record_id``. Locators are taken from law_input (including values joined from
    ``--law-candidates``), then legacy seed by id. ``provision_url`` is a legislation.gov.uk
    deep-link when the instrument URL + locator can be mapped.
    """
    legacy_by_id = {lp["judit_id"]: lp for lp in legacy_law_props if lp.get("judit_id")}
    url_by_srid = legislation_url_by_srid or {}
    rows: list[dict] = []
    missing_legislation: set[str] = set()
    missing_legacy = 0
    missing_locator = 0
    for lp in law_input:
        source_record_id = lp.get("graph_node") or lp.get("source_record_id")
        if source_record_id not in known_source_record_ids:
            missing_legislation.add(str(source_record_id))
            continue
        legacy = legacy_by_id.get(lp["id"])
        if legacy is None:
            missing_legacy += 1
        locator = locator_from_law_row(lp) or (legacy or {}).get("fragment_locator")
        if not locator:
            missing_locator += 1
        instrument_url = url_by_srid.get(str(source_record_id))
        rows.append({
            "id": lp["id"],
            "source_record_id": source_record_id,
            "proposition_text": lp["proposition_text"],
            "short_name": (legacy or {}).get("short_name"),
            "label": (legacy or {}).get("label"),
            "fragment_locator": locator,
            "provision_url": legislation_provision_url(instrument_url, locator),
        })
    if missing_legislation:
        for g in sorted(missing_legislation):
            warnings.append(
                f"law proposition source_record_id {g} has no row in legislation.json "
                "— add it to the seed or drop the proposition"
            )
    if missing_legacy:
        warnings.append(
            f"{missing_legacy} law propositions are new (no legacy law-proposition-extractor id match); "
            "short_name/label may be null — backfill from Law Proposition Extractor."
        )
    if missing_locator:
        warnings.append(
            f"{missing_locator} law proposition(s) have no fragment_locator "
            "(pass --law-candidates or enrich law.json)"
        )
    return rows


def _assembled_pair_row(gp_id: str | None, law_id: str, match: dict) -> dict:
    """Shared assembled shape for top-match and full reportable-comparison rows."""
    relationship = RELATIONSHIP_NORMALISE.get(match.get("relationship"))
    if relationship is None:
        relationship = normalise_relationship(match.get("relationship"))
    return {
        "id": f"m-{_sha8(gp_id or 'MISSING', law_id)}",
        "guidance_proposition_id": gp_id,
        "law_proposition_id": law_id,
        "relationship": relationship,
        "confidence": match.get("confidence"),
        "cosine_score": (
            round(match["similarity_score"], 4) if "similarity_score" in match else None
        ),
        "bert_score_f1": (
            round(match["bert_score_f1"], 4) if "bert_score_f1" in match else None
        ),
        "explanation": match.get("explanation"),
    }


def build_proposition_matches(
    matcher_output: list[dict],
    guidance_row_ids: list[str | None],
    law_prop_ids: set[str],
    warnings: list[str],
) -> list[dict]:
    """Compatibility top-match projection + synthesised gap rows.

    Proposition Matcher sorts ``matches`` best-first, so ``matches[0]`` is the top match.
    Full reportable pairs are emitted separately in
    ``guidance-proposition-law-comparisons.json``.
    Guidance with an empty ``matches`` array gets a ``NO_MATCH`` row
    (``law_proposition_id: null``). Every law proposition with no guidance match
    gets a ``GUIDANCE_MISSING`` row (``guidance_proposition_id: null``).
    """
    matches: list[dict] = []
    matched_law_ids: set[str] = set()
    unknown_law_ids: set[str] = set()
    unmapped: set[str] = set()

    for entry, gp_id in zip(matcher_output, guidance_row_ids, strict=True):
        if gp_id is None:
            continue
        top = next(iter(entry.get("matches", [])), None)
        if top is None:
            matches.append({
                "id": f"m-{_sha8(gp_id, 'NO_MATCH')}",
                "guidance_proposition_id": gp_id,
                "law_proposition_id": None,
                "relationship": "NO_MATCH",
                "confidence": None,
                "cosine_score": None,
                "bert_score_f1": None,
                "explanation": None,
            })
            continue
        law_id = law_proposition_id(top)
        if law_id not in law_prop_ids:
            unknown_law_ids.add(str(law_id))
            continue
        relationship = RELATIONSHIP_NORMALISE.get(top.get("relationship"))
        if relationship is None:
            unmapped.add(str(top.get("relationship")))
            continue
        matched_law_ids.add(law_id)
        matches.append(_assembled_pair_row(gp_id, law_id, top))

    if unknown_law_ids:
        for lid in sorted(unknown_law_ids):
            warnings.append(f"top match references unknown law id (not in law input): {lid}")
    if unmapped:
        for r in sorted(unmapped):
            warnings.append(f"unknown relationship value in Proposition Matcher output: {r!r}")

    for law_id in sorted(law_prop_ids - matched_law_ids):
        matches.append({
            "id": f"m-{_sha8('MISSING', law_id)}",
            "guidance_proposition_id": None,
            "law_proposition_id": law_id,
            "relationship": "GUIDANCE_MISSING",
            "confidence": None,
            "cosine_score": None,
            "bert_score_f1": None,
            "explanation": None,
        })
    return matches


def build_guidance_proposition_law_comparisons(
    matcher_output: list[dict],
    guidance_row_ids: list[str | None],
    law_prop_ids: set[str],
    match_summaries: list[dict],
    warnings: list[str],
) -> list[dict]:
    """All distinct reportable guidance–law pairs for frontend rendering.

    Emits only for propositions with ``COMPLETE`` + ``HAS_REPORTABLE_COMPARISON``.
    ``UNGROUNDED`` pairs are excluded (remain in Matcher ``results.json``).
    Pair identity is ``(guidance_proposition_id, law_proposition_id)``; accidental
    duplicates keep the first Matcher-ranked row and raise a warning.

    Ordering: guidance propositions in matcher/summary order; within each
    proposition, Matcher ``matches[]`` order (LABEL_PRIORITY best-first).

    Match Adjudicator only rewrites ``matches[0]`` in place; non-top pairs are
    emitted with their Matcher relationships (not represented as adjudicated).
    """
    summary_by_id = {s["guidance_proposition_id"]: s for s in match_summaries}
    comparisons: list[dict] = []
    unknown_law_ids: set[str] = set()
    unmapped: set[str] = set()
    total_duplicates = 0
    seen_ids: set[str] = set()

    for entry, gp_id in zip(matcher_output, guidance_row_ids, strict=True):
        if gp_id is None or gp_id in seen_ids:
            continue
        seen_ids.add(gp_id)
        summary = summary_by_id.get(gp_id) or {}
        if (
            summary.get("assessment_status") != "COMPLETE"
            or summary.get("coverage_result") != "HAS_REPORTABLE_COMPARISON"
        ):
            continue

        distinct, duplicates = distinct_matches_by_law_id(entry.get("matches"))
        total_duplicates += duplicates
        for match in distinct:
            if not is_reportable_relationship(match.get("relationship")):
                continue
            law_id = law_proposition_id(match)
            if law_id is None or law_id not in law_prop_ids:
                unknown_law_ids.add(str(law_id))
                continue
            relationship = RELATIONSHIP_NORMALISE.get(match.get("relationship"))
            if relationship is None:
                unmapped.add(str(match.get("relationship")))
                continue
            comparisons.append(_assembled_pair_row(gp_id, law_id, match))

    if total_duplicates:
        warnings.append(
            f"{total_duplicates} duplicate guidance–law match rows dropped "
            "(kept first Matcher-ranked row per (guidance_proposition_id, law_proposition_id))"
        )
    if unknown_law_ids:
        for lid in sorted(unknown_law_ids):
            warnings.append(
                f"reportable comparison references unknown law id (not in law input): {lid}"
            )
    if unmapped:
        for r in sorted(unmapped):
            warnings.append(f"unknown relationship value in Proposition Matcher output: {r!r}")

    return comparisons


def assert_reportable_comparison_count_invariant(
    match_summaries: list[dict],
    comparisons: list[dict],
    warnings: list[str],
) -> None:
    """COMPLETE + HAS_REPORTABLE_COMPARISON counts must match emitted pair rows."""
    counts: dict[str, int] = {}
    for row in comparisons:
        gp_id = row.get("guidance_proposition_id")
        if gp_id:
            counts[gp_id] = counts.get(gp_id, 0) + 1

    for summary in match_summaries:
        if (
            summary.get("assessment_status") != "COMPLETE"
            or summary.get("coverage_result") != "HAS_REPORTABLE_COMPARISON"
        ):
            continue
        gp_id = summary["guidance_proposition_id"]
        expected = summary["reportable_comparison_count"]
        actual = counts.get(gp_id, 0)
        if expected != actual:
            warnings.append(
                f"reportable comparison count mismatch for {gp_id}: "
                f"summary={expected} assembled={actual}"
            )


def build_page_relevance(
    pages: list[dict], relevance_filter_output: list[dict], category: str, warnings: list[str]
) -> list[dict]:
    """Per-page relevance from Guidance Relevance Filter, joined by content_id (falls back to url)."""
    score_by_content_id: dict[str, float | None] = {}
    score_by_url: dict[str, float | None] = {}
    for row in relevance_filter_output:
        score = _relevance_score(row.get("meta_data", {}) or {}, category)
        if row.get("content_id"):
            score_by_content_id[row["content_id"]] = score
        if row.get("url"):
            score_by_url[row["url"]] = score
    out = []
    missing = 0
    for p in pages:
        score = score_by_content_id.get(p["content_id"])
        if score is None:
            score = score_by_url.get(p["url"])
        if score is None:
            missing += 1
        out.append({
            "category": category,
            "content_id": p["content_id"],
            "relevance_score": score,
        })
    if missing:
        warnings.append(f"{missing} audited pages had no Guidance Relevance Filter relevance score (left null)")
    return out


def build_reading_age(pages: list[dict], reading_age_by_url: dict[str, dict]) -> list[dict]:
    out = []
    for p in pages:
        ra = reading_age_by_url.get(p["url"], {})
        out.append({
            "content_id": p["content_id"],
            "url": p["url"],
            "word_count": ra.get("word_count"),
            "reading_age": ra.get("reading_age"),
        })
    return out


def build_page_analytics(pages: list[dict], page_records: list[dict]) -> list[dict]:
    content_by_url = {c["url"]: c for c in page_records}
    out = []
    for p in pages:
        md = (content_by_url.get(p["url"], {}) or {}).get("meta_data", {}) or {}
        updated_at = md.get("updated_at")
        out.append({
            "content_id": p["content_id"],
            "last_updated_date": updated_at[:10] if updated_at else None,
            "view_count_period": md.get("view_count"),
            "period": "last_12_months",
        })
    return out


def build_subject_summary(
    category: str,
    matches: list[dict],
    pages: list[dict],
    legislation: list[dict],
    total_pages_audited: int,
) -> dict:
    counter = Counter(m["relationship"] for m in matches)
    return {
        "category": category,
        "total_pages_audited": total_pages_audited,
        "laws_found": len(legislation),
        "pages_relevant": len(pages),
        "proposition_status_counts": {k: counter.get(k, 0) for k in STATUS_ORDER},
    }


def build(
    *,
    matcher_output: list[dict],
    law_input: list[dict],
    relevance_filter_output: list[dict],
    legislation_seed: list[dict],
    legacy_law_props: list[dict],
    category: dict,
    reading_age_by_url: dict[str, dict],
) -> tuple[dict[str, object], list[str]]:
    """Run the full transform. Returns ``(files, warnings)`` where ``files`` maps
    output filename -> JSON-serialisable data. ``category`` is
    ``{"id": slug, "title": ..., "description": ...}``."""
    warnings: list[str] = []
    slug = category["id"]

    # Assembler never invents match_processing. Reject purported historic backfills
    # with missing/invalid provenance; legacy rows without the field stay NOT_CHECKED.
    processing_errors = validate_matcher_match_processing(matcher_output)
    if processing_errors:
        raise ValueError(
            "invalid Matcher match_processing at Assembler boundary:\n  - "
            + "\n  - ".join(processing_errors)
        )
    backfilled = count_historic_backfill_rows(matcher_output)
    if backfilled:
        warnings.append(
            f"{backfilled} Matcher row(s) carry approved historic_backfill "
            "match_processing provenance (Assembler did not reconstruct processing)"
        )

    # The audited pages are the ones Proposition Matcher produced guidance for; their
    # metadata + analytics come from the Guidance Relevance Filter run (Proposition Matcher no longer emits a
    # content intermediate). Guidance Relevance Filter's full output is the audited-corpus size.
    audited_urls = {entry["url"] for entry in matcher_output if entry.get("url")}
    page_records = [r for r in relevance_filter_output if r.get("url") in audited_urls]

    title_by_url = {u: ra.get("title") for u, ra in reading_age_by_url.items() if ra.get("title")}
    pages = build_pages(page_records, slug, warnings, title_by_url)
    url_to_content_id = {
        p["url"]: p["content_id"] for p in pages if p.get("content_id")
    }

    guidance_props, guidance_row_ids = build_guidance_propositions(
        matcher_output, url_to_content_id, warnings
    )

    legislation = build_legislation(legislation_seed, slug)
    known_srids = {law["source_record_id"] for law in legislation}
    legislation_url_by_srid = {
        str(law["source_record_id"]): law.get("url") for law in legislation
    }
    legislation_props = build_legislation_propositions(
        law_input,
        legacy_law_props,
        known_srids,
        warnings,
        legislation_url_by_srid=legislation_url_by_srid,
    )
    law_prop_ids = {lp["id"] for lp in legislation_props}

    matches = build_proposition_matches(
        matcher_output, guidance_row_ids, law_prop_ids, warnings
    )
    match_summaries = build_guidance_proposition_match_summaries(
        matcher_output, guidance_row_ids
    )
    law_comparisons = build_guidance_proposition_law_comparisons(
        matcher_output, guidance_row_ids, law_prop_ids, match_summaries, warnings
    )
    assert_reportable_comparison_count_invariant(match_summaries, law_comparisons, warnings)

    files: dict[str, object] = {
        "categories.json": [category],
        "legislation.json": legislation,
        "legislation-propositions.json": legislation_props,
        "pages.json": pages,
        "guidance-propositions.json": guidance_props,
        # Compatibility: top match per guidance prop + synthetic gap rows
        # (NO_MATCH for empty Matcher matches; law-side GUIDANCE_MISSING).
        "proposition-matches.json": matches,
        # Proposition-level assessment/coverage (not pair rows).
        "guidance-proposition-match-summaries.json": match_summaries,
        # All distinct reportable guidance–law pairs (UNGROUNDED excluded).
        "guidance-proposition-law-comparisons.json": law_comparisons,
        "page-relevance.json": build_page_relevance(pages, relevance_filter_output, slug, warnings),
        "pages-reading-age.json": build_reading_age(pages, reading_age_by_url),
        "page-analytics.json": build_page_analytics(pages, page_records),
        "subject-summary.json": [
            build_subject_summary(slug, matches, pages, legislation, len(relevance_filter_output))
        ],
    }
    return files, warnings
