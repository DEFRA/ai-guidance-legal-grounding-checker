"""Denormalized CSV export of reportable guidance↔law pairs.

Reads Audit Assembler presentation data (envelope ``output.json`` or a flat
presentation directory) and emits one row per reportable pair, plus one stub
row per guidance proposition with zero reportable pairs.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

CSV_HEADERS = [
    "category",
    "page_url",
    "page_title",
    "content_id",
    "guidance_proposition_id",
    "guidance_proposition_text",
    "section_locator",
    "source_paragraphs",
    "comparison_id",
    "relationship",
    "confidence",
    "cosine_score",
    "bert_score_f1",
    "explanation",
    "assessment_status",
    "coverage_result",
    "candidate_count",
    "reportable_comparison_count",
    "ungrounded_candidate_count",
    "law_proposition_id",
    "law_proposition_text",
    "law_source_record_id",
    "law_name",
    "law_url",
    "law_provision_url",
    "law_short_name",
    "law_label",
    "law_fragment_locator",
]

FLAT_FILES = {
    "categories": "categories.json",
    "legislation": "legislation.json",
    "legislation_propositions": "legislation-propositions.json",
    "pages": "pages.json",
    "guidance_propositions": "guidance-propositions.json",
    "proposition_matches": "proposition-matches.json",
    "page_analytics": "page-analytics.json",
    "subject_summary": "subject-summary.json",
    "page_relevance": "page-relevance.json",
    "pages_reading_age": "pages-reading-age.json",
    "guidance_proposition_match_summaries": "guidance-proposition-match-summaries.json",
    "guidance_proposition_law_comparisons": "guidance-proposition-law-comparisons.json",
}

REQUIRED_FLAT_KEYS = (
    "guidance_propositions",
    "legislation_propositions",
    "pages",
    "legislation",
    "guidance_proposition_match_summaries",
    "guidance_proposition_law_comparisons",
)

PAIRS_CSV_FILENAME = "pairs.csv"


class MissingSummariesError(ValueError):
    """Presentation lacks guidance_proposition_match_summaries."""


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _join_paragraphs(paragraphs: Any) -> str:
    if not paragraphs:
        return ""
    if isinstance(paragraphs, str):
        return paragraphs
    return " | ".join(str(p) for p in paragraphs)


def _empty_row() -> dict[str, str]:
    return {key: "" for key in CSV_HEADERS}


def load_presentation(path: Path) -> tuple[dict[str, list], str | None]:
    """Load presentation arrays from an envelope or flat directory.

    Returns ``(presentation, category)`` where ``category`` is the envelope
    category slug when present, else ``None``.
    """
    path = Path(path)
    if path.is_file():
        envelope = _load_json(path)
        if not isinstance(envelope, dict) or "presentation" not in envelope:
            raise ValueError(
                f"{path} is not an Audit Assembler envelope (missing presentation)"
            )
        presentation = dict(envelope["presentation"])
        category = envelope.get("category")
        if isinstance(category, str):
            return presentation, category
        return presentation, None

    if not path.is_dir():
        raise ValueError(f"input not found: {path}")

    presentation: dict[str, list] = {}
    for key, filename in FLAT_FILES.items():
        file_path = path / filename
        if not file_path.exists():
            if key in (
                "guidance_proposition_match_summaries",
                "guidance_proposition_law_comparisons",
            ):
                presentation[key] = []
                continue
            if key in REQUIRED_FLAT_KEYS:
                raise ValueError(f"missing presentation file: {file_path}")
            continue
        presentation[key] = _load_json(file_path)

    category: str | None = None
    categories = presentation.get("categories") or []
    if len(categories) == 1 and isinstance(categories[0], dict):
        cat_id = categories[0].get("id")
        if isinstance(cat_id, str):
            category = cat_id
    return presentation, category


def _require_summaries(presentation: dict[str, list]) -> list[dict]:
    summaries = presentation.get("guidance_proposition_match_summaries")
    if not summaries:
        raise MissingSummariesError(
            "guidance_proposition_match_summaries is missing or empty; "
            "rebuild with Audit Assembler before exporting CSV"
        )
    return summaries


def iter_pair_rows(
    presentation: dict[str, list],
    category: str | None = None,
    *,
    warnings: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build denormalized CSV rows from presentation arrays."""
    warn = warnings if warnings is not None else []
    summaries = _require_summaries(presentation)

    guidance_props = presentation.get("guidance_propositions") or []
    law_props = presentation.get("legislation_propositions") or []
    pages = presentation.get("pages") or []
    legislation = presentation.get("legislation") or []
    comparisons = presentation.get("guidance_proposition_law_comparisons") or []

    gp_by_id = {gp["id"]: gp for gp in guidance_props if gp.get("id")}
    lp_by_id = {lp["id"]: lp for lp in law_props if lp.get("id")}
    page_by_cid = {
        page["content_id"]: page for page in pages if page.get("content_id") is not None
    }
    law_by_srid = {
        law["source_record_id"]: law
        for law in legislation
        if law.get("source_record_id") is not None
    }
    summary_by_gp = {
        row["guidance_proposition_id"]: row
        for row in summaries
        if row.get("guidance_proposition_id")
    }

    comps_by_gp: dict[str, list[dict]] = defaultdict(list)
    for comp in comparisons:
        gp_id = comp.get("guidance_proposition_id")
        if not gp_id:
            warn.append(f"comparison {comp.get('id')!r} missing guidance_proposition_id; skipped")
            continue
        if gp_id not in gp_by_id:
            warn.append(
                f"comparison {comp.get('id')!r} references unknown guidance "
                f"proposition {gp_id!r}; skipped"
            )
            continue
        comps_by_gp[gp_id].append(comp)

    def gp_sort_key(gp: dict) -> tuple[str, str]:
        page = page_by_cid.get(gp.get("content_id")) or {}
        return (page.get("url") or "", gp.get("id") or "")

    rows: list[dict[str, str]] = []
    for gp in sorted(guidance_props, key=gp_sort_key):
        gp_id = gp.get("id")
        if not gp_id:
            continue
        summary = summary_by_gp.get(gp_id)
        if summary is None:
            warn.append(f"guidance proposition {gp_id!r} has no match summary")
        page = page_by_cid.get(gp.get("content_id")) or {}
        row_category = category
        if row_category is None:
            row_category = page.get("category") or gp.get("category") or ""

        base = _empty_row()
        base.update(
            {
                "category": _cell(row_category),
                "page_url": _cell(page.get("url")),
                "page_title": _cell(page.get("title")),
                "content_id": _cell(gp.get("content_id")),
                "guidance_proposition_id": _cell(gp_id),
                "guidance_proposition_text": _cell(gp.get("proposition_text")),
                "section_locator": _cell(gp.get("section_locator")),
                "source_paragraphs": _join_paragraphs(gp.get("source_paragraphs")),
                "assessment_status": _cell(summary.get("assessment_status") if summary else None),
                "coverage_result": _cell(summary.get("coverage_result") if summary else None),
                "candidate_count": _cell(summary.get("candidate_count") if summary else None),
                "reportable_comparison_count": _cell(
                    summary.get("reportable_comparison_count") if summary else None
                ),
                "ungrounded_candidate_count": _cell(
                    summary.get("ungrounded_candidate_count") if summary else None
                ),
            }
        )

        gp_comps = comps_by_gp.get(gp_id) or []
        if not gp_comps:
            rows.append(base)
            continue

        for comp in gp_comps:
            row = dict(base)
            law_id = comp.get("law_proposition_id")
            lp = lp_by_id.get(law_id) if law_id else None
            if law_id and lp is None:
                warn.append(
                    f"comparison {comp.get('id')!r} references unknown law "
                    f"proposition {law_id!r}"
                )
            law = law_by_srid.get((lp or {}).get("source_record_id")) if lp else None
            row.update(
                {
                    "comparison_id": _cell(comp.get("id")),
                    "relationship": _cell(comp.get("relationship")),
                    "confidence": _cell(comp.get("confidence")),
                    "cosine_score": _cell(comp.get("cosine_score")),
                    "bert_score_f1": _cell(comp.get("bert_score_f1")),
                    "explanation": _cell(comp.get("explanation")),
                    "law_proposition_id": _cell(law_id),
                    "law_proposition_text": _cell((lp or {}).get("proposition_text")),
                    "law_source_record_id": _cell((lp or {}).get("source_record_id")),
                    "law_name": _cell((law or {}).get("name")),
                    "law_url": _cell((law or {}).get("url")),
                    "law_provision_url": _cell((lp or {}).get("provision_url")),
                    "law_short_name": _cell((lp or {}).get("short_name")),
                    "law_label": _cell((lp or {}).get("label")),
                    "law_fragment_locator": _cell((lp or {}).get("fragment_locator")),
                }
            )
            rows.append(row)

    return rows


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_csv(
    input_path: Path,
    out_path: Path,
    *,
    warnings: list[str] | None = None,
) -> list[dict[str, str]]:
    """Load presentation from ``input_path`` and write CSV to ``out_path``."""
    presentation, category = load_presentation(input_path)
    rows = iter_pair_rows(presentation, category, warnings=warnings)
    write_csv(rows, out_path)
    return rows


def default_pairs_csv_path(input_path: Path) -> Path:
    """``pairs.csv`` next to an envelope file, or inside a flat dest directory."""
    path = Path(input_path)
    if path.is_file():
        return path.parent / PAIRS_CSV_FILENAME
    return path / PAIRS_CSV_FILENAME


def try_write_pairs_csv(
    dest: Path,
    *,
    warnings: list[str] | None = None,
) -> list[dict[str, str]] | None:
    """Write ``dest/pairs.csv`` from a flat assembled directory.

    Returns rows when written. Returns ``None`` (and appends a warning) when
    match summaries are missing — callers should not fail the surrounding build.
    """
    dest = Path(dest)
    try:
        return export_csv(dest, dest / PAIRS_CSV_FILENAME, warnings=warnings)
    except MissingSummariesError:
        if warnings is not None:
            warnings.append(
                "skipped pairs.csv: guidance_proposition_match_summaries is "
                "missing or empty"
            )
        return None
