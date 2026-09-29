"""Deterministic human review report for normalised proposition exports (no LLM)."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import is_generic_display_label, is_placeholder_subject
from law_proposition_extractor_domain.enums import LegalEffectType, PropositionTier

from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import (
    default_slurry_export_path,
    load_normalised_slurry_export_propositions,
    load_slurry_export_propositions,
)

REVIEW_MD_FILENAME = "NORMALISED_PROPOSITION_REVIEW.md"
REVIEW_JSON_FILENAME = "normalised_proposition_review.json"

_MIN_ACTOR_ACTION_LEN = 3
_LABEL_TOP_N = 30


@dataclass(frozen=True)
class ReviewRow:
    """One proposition row for markdown/json sections."""

    proposition_id: str
    fields: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"proposition_id": self.proposition_id, **self.fields}


@dataclass(frozen=True)
class SemanticComparisonBucket:
    semantic_comparison_key: str
    size: int
    members: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_comparison_key": self.semantic_comparison_key,
            "size": self.size,
            "members": self.members,
        }


@dataclass(frozen=True)
class NormalisedPropositionReview:
    export_dir: str
    proposition_count: int
    unknown_classifications: list[ReviewRow]
    legacy_category_conflicts: list[ReviewRow]
    application_scope_rows: list[ReviewRow]
    cross_reference_rows: list[ReviewRow]
    semantic_comparison_buckets: list[SemanticComparisonBucket]
    compliance_without_clear_actor: list[ReviewRow]
    longest_labels: list[ReviewRow]
    shortest_generic_labels: list[ReviewRow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_dir": self.export_dir,
            "proposition_count": self.proposition_count,
            "sections": {
                "unknown_classifications": [r.to_dict() for r in self.unknown_classifications],
                "legacy_category_conflicts": [r.to_dict() for r in self.legacy_category_conflicts],
                "application_scope_rows": [r.to_dict() for r in self.application_scope_rows],
                "cross_reference_rows": [r.to_dict() for r in self.cross_reference_rows],
                "semantic_comparison_buckets": [b.to_dict() for b in self.semantic_comparison_buckets],
                "compliance_without_clear_actor": [
                    r.to_dict() for r in self.compliance_without_clear_actor
                ],
                "longest_labels": [r.to_dict() for r in self.longest_labels],
                "shortest_generic_labels": [r.to_dict() for r in self.shortest_generic_labels],
            },
            "counts": {
                "unknown_classifications": len(self.unknown_classifications),
                "legacy_category_conflicts": len(self.legacy_category_conflicts),
                "application_scope_rows": len(self.application_scope_rows),
                "cross_reference_rows": len(self.cross_reference_rows),
                "semantic_comparison_buckets": len(self.semantic_comparison_buckets),
                "compliance_without_clear_actor": len(self.compliance_without_clear_actor),
                "longest_labels": len(self.longest_labels),
                "shortest_generic_labels": len(self.shortest_generic_labels),
            },
        }


def load_export_sources(export_dir: str | Path) -> dict[str, dict[str, Any]]:
    path = Path(export_dir) / "sources.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return {}
    return {str(item.get("id") or ""): item for item in raw if isinstance(item, dict) and item.get("id")}


def _str_field(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _list_field(row: dict[str, Any], key: str) -> list[str]:
    raw = row.get(key)
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _categories(row: dict[str, Any]) -> list[str]:
    raw = row.get("categories")
    if not isinstance(raw, list):
        return []
    return [str(c) for c in raw]


def _bool_field(row: dict[str, Any], key: str) -> bool | None:
    val = row.get(key)
    if val is True or val is False:
        return val
    return None


def _source_title(source_id: str, sources_by_id: dict[str, dict[str, Any]]) -> str:
    src = sources_by_id.get(source_id)
    if not isinstance(src, dict):
        return ""
    return str(src.get("title") or src.get("citation") or "").strip()


def _locator(row: dict[str, Any]) -> str:
    return _str_field(row, "fragment_locator") or _str_field(row, "article_reference")


def _sort_key_row(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _str_field(row, "source_record_id"),
        _locator(row).lower(),
        _str_field(row, "id"),
    )


def _base_fields(row: dict[str, Any], sources_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sid = _str_field(row, "source_record_id")
    return {
        "source_record_id": sid,
        "source_title": _source_title(sid, sources_by_id),
        "locator": _locator(row),
        "label": _str_field(row, "label"),
        "proposition_tier": _str_field(row, "proposition_tier"),
        "legal_effect_type": _str_field(row, "legal_effect_type"),
    }


def _is_blank_or_unknown_classification_value(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized == PropositionTier.UNKNOWN.value


def _is_unknown_classification(row: dict[str, Any]) -> bool:
    tier = _str_field(row, "proposition_tier")
    effect = _str_field(row, "legal_effect_type")
    return _is_blank_or_unknown_classification_value(
        tier
    ) or _is_blank_or_unknown_classification_value(effect)


def _verify_unknown_classifications_complete(
    rows: list[dict[str, Any]],
    unknown: list[ReviewRow],
) -> None:
    """Every row with missing/blank/unknown tier or effect must appear in unknown_classifications."""
    unknown_ids = {r.proposition_id for r in unknown}
    gaps: list[str] = []
    for row in rows:
        pid = _str_field(row, "id")
        tier = _str_field(row, "proposition_tier")
        effect = _str_field(row, "legal_effect_type")
        if not _is_unknown_classification(row):
            continue
        if pid not in unknown_ids:
            gaps.append(f"{pid} (tier={tier!r}, effect={effect!r})")
    if gaps:
        raise ValueError(
            "review internal inconsistency: rows with unknown classification not listed "
            f"in unknown_classifications: {', '.join(gaps[:5])}"
            + (f" (+{len(gaps) - 5} more)" if len(gaps) > 5 else "")
        )


def _is_legacy_category_conflict(row: dict[str, Any]) -> bool:
    return "obligation" in _categories(row) and _bool_field(row, "is_compliance_relevant") is False


def _is_weak_actor_or_action(row: dict[str, Any]) -> bool:
    subject = _str_field(row, "legal_subject")
    action = _str_field(row, "action")
    if not subject or is_placeholder_subject(subject) or len(subject) < _MIN_ACTOR_ACTION_LEN:
        return True
    if not action or len(action) < _MIN_ACTOR_ACTION_LEN:
        return True
    return False


def _explicit_cross_reference_targets(row: dict[str, Any]) -> list[str]:
    explicit = _list_field(row, "explicit_cross_reference_targets")
    if explicit:
        return explicit
    return _list_field(row, "cross_reference_targets")


def _proposition_text_snippet(row: dict[str, Any], *, max_len: int = 200) -> str:
    text = _str_field(row, "proposition_text")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def build_normalised_proposition_review(
    propositions: list[dict[str, Any]],
    *,
    export_dir: str | Path,
    sources_by_id: dict[str, dict[str, Any]] | None = None,
) -> NormalisedPropositionReview:
    """Build all review sections from export proposition dicts (deterministic)."""
    sources = sources_by_id if sources_by_id is not None else {}
    rows = sorted(
        [p for p in propositions if isinstance(p, dict) and _str_field(p, "id")],
        key=_sort_key_row,
    )

    unknown: list[ReviewRow] = []
    legacy_conflicts: list[ReviewRow] = []
    scope_rows: list[ReviewRow] = []
    xref_rows: list[ReviewRow] = []
    compliance_weak: list[ReviewRow] = []

    for row in rows:
        pid = _str_field(row, "id")
        base = _base_fields(row, sources)

        if _is_unknown_classification(row):
            unknown.append(
                ReviewRow(
                    proposition_id=pid,
                    fields={
                        **base,
                        "legal_subject": _str_field(row, "legal_subject"),
                        "action": _str_field(row, "action"),
                        "proposition_text": _proposition_text_snippet(row),
                    },
                )
            )

        if _is_legacy_category_conflict(row):
            legacy_conflicts.append(
                ReviewRow(
                    proposition_id=pid,
                    fields={
                        **base,
                        "categories": _categories(row),
                        "is_compliance_relevant": _bool_field(row, "is_compliance_relevant"),
                    },
                )
            )

        if _str_field(row, "legal_effect_type") == LegalEffectType.APPLICATION_SCOPE.value:
            scope_rows.append(
                ReviewRow(
                    proposition_id=pid,
                    fields={
                        **base,
                        "territorial_application": _list_field(row, "territorial_application"),
                        "affected_subjects": _list_field(row, "affected_subjects"),
                    },
                )
            )

        if _str_field(row, "legal_effect_type") == LegalEffectType.CROSS_REFERENCE.value:
            xref_rows.append(
                ReviewRow(
                    proposition_id=pid,
                    fields={
                        **base,
                        "explicit_targets": _explicit_cross_reference_targets(row),
                        "proposition_text": _proposition_text_snippet(row, max_len=280),
                    },
                )
            )

        if _bool_field(row, "is_compliance_relevant") is True and _is_weak_actor_or_action(row):
            compliance_weak.append(
                ReviewRow(
                    proposition_id=pid,
                    fields={
                        **base,
                        "legal_subject": _str_field(row, "legal_subject"),
                        "action": _str_field(row, "action"),
                        "is_compliance_relevant": True,
                    },
                )
            )

    semantic_buckets = _build_semantic_comparison_buckets(rows, sources)

    label_rows = [
        (
            len(_str_field(row, "label")),
            _str_field(row, "label"),
            row,
        )
        for row in rows
        if _str_field(row, "label")
    ]
    label_rows.sort(key=lambda item: (-item[0], _sort_key_row(item[2])))
    longest = [
        ReviewRow(
            proposition_id=_str_field(row, "id"),
            fields={**_base_fields(row, sources), "label_length": length},
        )
        for length, _label, row in label_rows[:_LABEL_TOP_N]
    ]

    generic_candidates: list[tuple[int, int, tuple[str, str, str], dict[str, Any], str]] = []
    for row in rows:
        label = _str_field(row, "label")
        if not label:
            continue
        generic = is_generic_display_label(label)
        generic_candidates.append(
            (
                0 if generic else 1,
                len(label),
                _sort_key_row(row),
                row,
                label,
            )
        )
    generic_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    shortest_generic = [
        ReviewRow(
            proposition_id=_str_field(row, "id"),
            fields={
                **_base_fields(row, sources),
                "label_length": length,
                "generic_label": is_generic_display_label(label),
            },
        )
        for _prio, length, _sort, row, label in generic_candidates[:_LABEL_TOP_N]
    ]

    _verify_unknown_classifications_complete(rows, unknown)

    return NormalisedPropositionReview(
        export_dir=str(Path(export_dir).resolve()),
        proposition_count=len(rows),
        unknown_classifications=unknown,
        legacy_category_conflicts=legacy_conflicts,
        application_scope_rows=scope_rows,
        cross_reference_rows=xref_rows,
        semantic_comparison_buckets=semantic_buckets,
        compliance_without_clear_actor=compliance_weak,
        longest_labels=longest,
        shortest_generic_labels=shortest_generic,
    )


def _build_semantic_comparison_buckets(
    rows: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
) -> list[SemanticComparisonBucket]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _str_field(row, "semantic_comparison_key")
        if not key:
            continue
        sid = _str_field(row, "source_record_id")
        buckets[key].append(
            {
                "proposition_id": _str_field(row, "id"),
                "source_record_id": sid,
                "source_title": _source_title(sid, sources),
                "label": _str_field(row, "label"),
                "locator": _locator(row),
                "territorial_application": _list_field(row, "territorial_application"),
                "legal_effect_type": _str_field(row, "legal_effect_type"),
            }
        )

    out: list[SemanticComparisonBucket] = []
    for key in sorted(buckets):
        members = buckets[key]
        if len(members) <= 1:
            continue
        members.sort(key=lambda m: (m["source_record_id"], m["locator"], m["proposition_id"]))
        out.append(
            SemanticComparisonBucket(
                semantic_comparison_key=key,
                size=len(members),
                members=members,
            )
        )
    out.sort(key=lambda b: (-b.size, b.semantic_comparison_key))
    return out


def render_normalised_proposition_review_md(review: NormalisedPropositionReview) -> str:
    """Render markdown report (stable section order)."""
    lines: list[str] = [
        "# Normalised proposition review",
        "",
        f"Export: `{review.export_dir}`",
        f"Propositions reviewed: **{review.proposition_count}**",
        "",
        "_Deterministic report for human review. Semantic comparison buckets are hints only — "
        "not automatic legal links._",
        "",
    ]

    lines.extend(
        _section_unknown(review.unknown_classifications),
    )
    lines.extend(
        _section_legacy_conflicts(review.legacy_category_conflicts),
    )
    lines.extend(
        _section_application_scope(review.application_scope_rows),
    )
    lines.extend(
        _section_cross_reference(review.cross_reference_rows),
    )
    lines.extend(
        _section_semantic_buckets(review.semantic_comparison_buckets),
    )
    lines.extend(
        _section_compliance_weak(review.compliance_without_clear_actor),
    )
    lines.extend(
        _section_label_ranking("Longest labels (top 30)", review.longest_labels, include_length=True),
    )
    lines.extend(
        _section_label_ranking(
            "Shortest / generic labels (top 30)",
            review.shortest_generic_labels,
            include_length=True,
        ),
    )
    return "\n".join(lines).rstrip() + "\n"


def _section_unknown(rows: list[ReviewRow]) -> list[str]:
    lines = [
        "## 1. Unknown classifications",
        "",
        f"Count: **{len(rows)}** — `proposition_tier` or `legal_effect_type` is missing, "
        "blank, or `unknown`.",
        "",
    ]
    if not rows:
        lines.append("_None._\n")
        return lines
    lines.extend(_table_header(["ID", "Locator", "Tier", "Effect", "Label", "Snippet"]))
    for row in rows:
        f = row.fields
        lines.append(
            _table_row(
                [
                    row.proposition_id,
                    f.get("locator", ""),
                    f.get("proposition_tier", ""),
                    f.get("legal_effect_type", ""),
                    f.get("label", ""),
                    f.get("proposition_text", ""),
                ]
            )
        )
    lines.append("")
    return lines


def _section_legacy_conflicts(rows: list[ReviewRow]) -> list[str]:
    lines = [
        "## 2. Legacy category conflicts",
        "",
        f"Count: **{len(rows)}** — legacy `categories` contains `obligation` but "
        "`is_compliance_relevant` is `false`.",
        "",
    ]
    if not rows:
        lines.append("_None._\n")
        return lines
    lines.extend(
        _table_header(["ID", "Locator", "Label", "Categories", "Compliance"])
    )
    for row in rows:
        f = row.fields
        cats = f.get("categories") or []
        lines.append(
            _table_row(
                [
                    row.proposition_id,
                    f.get("locator", ""),
                    f.get("label", ""),
                    ", ".join(cats) if isinstance(cats, list) else str(cats),
                    str(f.get("is_compliance_relevant")),
                ]
            )
        )
    lines.append("")
    return lines


def _section_application_scope(rows: list[ReviewRow]) -> list[str]:
    lines = [
        "## 3. Scope / application rows",
        "",
        f"Count: **{len(rows)}** — `legal_effect_type` is `application_scope`.",
        "",
    ]
    if not rows:
        lines.append("_None._\n")
        return lines
    lines.extend(
        _table_header(
            ["ID", "Locator", "Source", "Label", "Territory", "Affected subjects"]
        )
    )
    for row in rows:
        f = row.fields
        terr = f.get("territorial_application") or []
        aff = f.get("affected_subjects") or []
        lines.append(
            _table_row(
                [
                    row.proposition_id,
                    f.get("locator", ""),
                    f.get("source_title", ""),
                    f.get("label", ""),
                    ", ".join(terr) if isinstance(terr, list) else str(terr),
                    ", ".join(aff) if isinstance(aff, list) else str(aff),
                ]
            )
        )
    lines.append("")
    return lines


def _section_cross_reference(rows: list[ReviewRow]) -> list[str]:
    lines = [
        "## 4. Cross-reference rows",
        "",
        f"Count: **{len(rows)}** — `legal_effect_type` is `cross_reference`.",
        "",
    ]
    if not rows:
        lines.append("_None._\n")
        return lines
    lines.extend(
        _table_header(["ID", "Locator", "Label", "Targets", "Text"])
    )
    for row in rows:
        f = row.fields
        targets = f.get("explicit_targets") or []
        lines.append(
            _table_row(
                [
                    row.proposition_id,
                    f.get("locator", ""),
                    f.get("label", ""),
                    ", ".join(targets) if isinstance(targets, list) else str(targets),
                    f.get("proposition_text", ""),
                ]
            )
        )
    lines.append("")
    return lines


def _section_semantic_buckets(buckets: list[SemanticComparisonBucket]) -> list[str]:
    lines = [
        "## 5. Semantic comparison buckets (review hints)",
        "",
        f"Count: **{len(buckets)}** — buckets with more than one proposition sharing a "
        "`semantic_comparison_key`. **Not treated as automatic links.**",
        "",
    ]
    if not buckets:
        lines.append("_None._\n")
        return lines
    for bucket in buckets:
        lines.append(f"### `{bucket.semantic_comparison_key}` ({bucket.size} propositions)")
        lines.append("")
        lines.extend(
            _table_header(["ID", "Source", "Locator", "Label", "Territory", "Effect"])
        )
        for member in bucket.members:
            terr = member.get("territorial_application") or []
            lines.append(
                _table_row(
                    [
                        member.get("proposition_id", ""),
                        member.get("source_title", ""),
                        member.get("locator", ""),
                        member.get("label", ""),
                        ", ".join(terr) if isinstance(terr, list) else str(terr),
                        member.get("legal_effect_type", ""),
                    ]
                )
            )
        lines.append("")
    return lines


def _section_compliance_weak(rows: list[ReviewRow]) -> list[str]:
    lines = [
        "## 6. Compliance-relevant rows without clear actor/action",
        "",
        f"Count: **{len(rows)}** — `is_compliance_relevant` is `true` but `legal_subject` or "
        "`action` is missing, placeholder, or very short.",
        "",
    ]
    if not rows:
        lines.append("_None._\n")
        return lines
    lines.extend(
        _table_header(["ID", "Locator", "Label", "Subject", "Action"])
    )
    for row in rows:
        f = row.fields
        lines.append(
            _table_row(
                [
                    row.proposition_id,
                    f.get("locator", ""),
                    f.get("label", ""),
                    f.get("legal_subject", ""),
                    f.get("action", ""),
                ]
            )
        )
    lines.append("")
    return lines


def _section_label_ranking(
    title: str,
    rows: list[ReviewRow],
    *,
    include_length: bool,
) -> list[str]:
    section_num = "7" if "Longest" in title else "8"
    lines = [
        f"## {section_num}. {title}",
        "",
        f"Count: **{len(rows)}**",
        "",
    ]
    if not rows:
        lines.append("_None._\n")
        return lines
    headers = ["ID", "Locator", "Label"]
    if include_length:
        headers.insert(2, "Len")
    lines.extend(_table_header(headers))
    for row in rows:
        f = row.fields
        cells = [
            row.proposition_id,
            f.get("locator", ""),
        ]
        if include_length:
            cells.append(str(f.get("label_length", "")))
        cells.append(f.get("label", ""))
        lines.append(_table_row(cells))
    lines.append("")
    return lines


def _escape_cell(value: Any) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    return text


def _table_header(columns: list[str]) -> list[str]:
    return [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]


def _table_row(cells: list[Any]) -> str:
    return "| " + " | ".join(_escape_cell(c) for c in cells) + " |"


def write_normalised_proposition_review(
    export_dir: str | Path,
    review: NormalisedPropositionReview,
    *,
    write_json: bool = True,
) -> tuple[Path, Path | None]:
    root = Path(export_dir)
    md_path = root / REVIEW_MD_FILENAME
    md_path.write_text(render_normalised_proposition_review_md(review), encoding="utf-8")
    json_path: Path | None = None
    if write_json:
        json_path = root / REVIEW_JSON_FILENAME
        json_path.write_text(
            json.dumps(review.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return md_path, json_path


def build_review_from_export_dir(
    export_dir: str | Path,
    *,
    propositions: list[dict[str, Any]] | None = None,
    sources_by_id: dict[str, dict[str, Any]] | None = None,
    normalise: bool = True,
) -> NormalisedPropositionReview:
    root = Path(export_dir)
    if propositions is not None:
        props = propositions
    elif normalise:
        props = load_normalised_slurry_export_propositions(root)
    else:
        props = load_slurry_export_propositions(root)
    sources = sources_by_id if sources_by_id is not None else load_export_sources(root)
    return build_normalised_proposition_review(props, export_dir=root, sources_by_id=sources)


def default_review_export_path(repo_root: Path | None = None) -> Path:
    return default_slurry_export_path(repo_root)
