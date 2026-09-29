"""Deterministic duplicate and quality review for proposition exports (no LLM)."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import is_generic_display_label, is_placeholder_subject
from law_proposition_extractor_domain.enums import LegalEffectType, PropositionTier

from law_proposition_extractor_pipeline.normalised_proposition_review import (
    SemanticComparisonBucket,
    _build_semantic_comparison_buckets,
    load_export_sources,
)
from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import load_slurry_export_propositions

REVIEW_MD_FILENAME = "SUSPICIOUS_PROPOSITION_REVIEW.md"
REVIEW_JSON_FILENAME = "suspicious_proposition_review.json"

SIMILARITY_THRESHOLD = 0.88
_LABEL_LONG_CHARS = 120
_LOCATOR_HIGH_COUNT_DEFAULT = 12
_LOCATOR_HIGH_COUNT_SCHEDULE = 25

DuplicateClassification = Literal[
    "true_duplicate",
    "legitimate_repeated_legal_pattern",
    "same_rule_split_into_conditions",
    "table_row",
    "semantic_comparison_candidate",
    "key_too_coarse",
    "duplicate_proposition_id",
    "info",
]

Severity = Literal["info", "warning", "error"]
RecommendedAction = Literal[
    "accept",
    "classifier_fix",
    "evidence_matcher_fix",
    "duplicate_key_fix",
    "prompt-lab_fixture_needed",
    "targeted_re-extract_needed",
    "human_legal_review",
]

_MODAL_RE = re.compile(
    r"\b(must not|shall not|may not|must|shall|may)\b",
    re.IGNORECASE,
)
_NUMERIC_TOKEN_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:kg|g|mg|l|litres?|m3|cubic metres?|hectares?|ha|%|tonnes?)\b",
    re.IGNORECASE,
)

_WEAK_SUBJECT_PHRASES = frozenset(
    {
        "it",
        "this regulation",
        "these regulations",
        "these rules",
        "the rule",
        "the rules",
        "the regulations",
        "this instrument",
        "the provision",
        "the act",
    }
)
_WEAK_ACTION_PHRASES = frozenset(
    {
        "apply",
        "relate to",
        "provide for",
        "be",
        "concern",
        "deal with",
        "cover",
        "include",
    }
)

_SCHEDULE_LOCATOR_RE = re.compile(r"schedule", re.IGNORECASE)
_TABLE_LOCATOR_RE = re.compile(r"table|row|column", re.IGNORECASE)
_REG1_BOILERPLATE_RE = re.compile(r"^regulation\s+1(\(|$)", re.IGNORECASE)


def _str_field(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _list_field(row: dict[str, Any], key: str) -> list[str]:
    raw = row.get(key)
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _locator(row: dict[str, Any]) -> str:
    return _str_field(row, "fragment_locator") or _str_field(row, "article_reference")


def _source_title(source_id: str, sources_by_id: dict[str, dict[str, Any]]) -> str:
    src = sources_by_id.get(source_id)
    if not isinstance(src, dict):
        return ""
    return str(src.get("title") or src.get("citation") or "").strip()


def _extraction_meta(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("extraction_debug_meta")
    return meta if isinstance(meta, dict) else {}


def _evidence_quote(row: dict[str, Any]) -> str:
    return str(_extraction_meta(row).get("evidence_quote") or "").strip()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", _normalize_text(text)) if len(t) > 1}


def _text_similarity(a: str, b: str) -> float:
    na, nb = _normalize_text(a), _normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = _token_set(na), _token_set(nb)
    if ta and tb:
        jaccard = len(ta & tb) / len(ta | tb)
    else:
        jaccard = 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    return max(jaccard, seq)


def _is_table_like(row: dict[str, Any]) -> bool:
    loc = _locator(row)
    if _TABLE_LOCATOR_RE.search(loc):
        return True
    text = _str_field(row, "proposition_text")
    if _NUMERIC_TOKEN_RE.search(text) and (
        "produce" in text.lower()
        or "litres" in text.lower()
        or "grams" in text.lower()
        or "kg" in text.lower()
    ):
        return True
    return bool(_SCHEDULE_LOCATOR_RE.search(loc) and _NUMERIC_TOKEN_RE.search(text))


def _sort_key_row(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _str_field(row, "source_record_id"),
        _locator(row).lower(),
        _str_field(row, "id"),
    )


@dataclass(frozen=True)
class SuspiciousFinding:
    severity: Severity
    reason: str
    source_title: str
    source_id: str
    locator: str
    proposition_id: str
    legal_effect_type: str
    proposition_tier: str
    label: str
    proposition_text: str
    evidence_quote: str
    recommended_action: RecommendedAction
    duplicate_classification: DuplicateClassification | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "severity": self.severity,
            "reason": self.reason,
            "source_title": self.source_title,
            "source_id": self.source_id,
            "locator": self.locator,
            "proposition_id": self.proposition_id,
            "legal_effect_type": self.legal_effect_type,
            "proposition_tier": self.proposition_tier,
            "label": self.label,
            "proposition_text": self.proposition_text,
            "evidence_quote": self.evidence_quote,
            "recommended_action": self.recommended_action,
        }
        if self.duplicate_classification is not None:
            out["duplicate_classification"] = self.duplicate_classification
        if self.extra:
            out["extra"] = self.extra
        return out


def _row_context(
    row: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    sid = _str_field(row, "source_record_id")
    return {
        "source_id": sid,
        "source_title": _source_title(sid, sources_by_id),
        "locator": _locator(row),
        "proposition_id": _str_field(row, "id"),
        "legal_effect_type": _str_field(row, "legal_effect_type"),
        "proposition_tier": _str_field(row, "proposition_tier"),
        "label": _str_field(row, "label"),
        "proposition_text": _str_field(row, "proposition_text"),
        "evidence_quote": _evidence_quote(row),
    }


def _finding_from_row(
    row: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
    *,
    severity: Severity,
    reason: str,
    recommended_action: RecommendedAction,
    duplicate_classification: DuplicateClassification | None = None,
    extra: dict[str, Any] | None = None,
) -> SuspiciousFinding:
    ctx = _row_context(row, sources_by_id)
    return SuspiciousFinding(
        severity=severity,
        reason=reason,
        recommended_action=recommended_action,
        duplicate_classification=duplicate_classification,
        extra=extra or {},
        **ctx,
    )


def _infer_territory_from_source(
    source_id: str,
    sources_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    src = sources_by_id.get(source_id)
    if not isinstance(src, dict):
        return []
    title = str(src.get("title") or "").lower()
    territories: list[str] = []
    if "england" in title and "wales" not in title:
        territories.append("England")
    if "wales" in title:
        territories.append("Wales")
    if "scotland" in title:
        territories.append("Scotland")
    if not territories and str(src.get("jurisdiction") or "").upper() == "UK":
        if "nitrate pollution prevention" in title:
            territories.append("England")
    return territories


def _classify_source_scoped_key_group(
    members: list[dict[str, Any]],
) -> DuplicateClassification:
    sources = {m.get("source_id") or m.get("source_record_id") for m in members}
    locators = {m["locator"] for m in members}
    effects = {m["legal_effect_type"] for m in members}
    if len(sources) > 1:
        return "legitimate_repeated_legal_pattern"
    if len(locators) > 1:
        return "key_too_coarse"
    if len(effects) > 1:
        return "same_rule_split_into_conditions"
    if all(_is_table_like(m) for m in members):
        return "table_row"
    texts = [_normalize_text(m["proposition_text"]) for m in members]
    if len(set(texts)) == 1:
        return "true_duplicate"
    return "semantic_comparison_candidate"


def _validation_warning_type(error: str) -> str:
    low = error.lower()
    if "not traceable" in low or "evidence" in low:
        return "evidence_traceability"
    if "repair" in low or "repaired" in low:
        return "json_repair"
    if "table" in low or "numeric" in low or "salvage" in low:
        return "table_numeric_salvage"
    if "parse" in low:
        return "parse_repair"
    return "other_validation"


def _is_strict_weak_compliance(row: dict[str, Any]) -> bool:
    if row.get("is_compliance_relevant") is not True:
        return False
    subject = _str_field(row, "legal_subject").lower()
    action = _str_field(row, "action").lower()
    if subject in _WEAK_SUBJECT_PHRASES or is_placeholder_subject(subject):
        return True
    if action in _WEAK_ACTION_PHRASES or len(action) < 3:
        return True
    text = _str_field(row, "proposition_text")
    if _MODAL_RE.search(text) and (subject in _WEAK_SUBJECT_PHRASES or len(action) < 8):
        return True
    return False


def _is_over_compressed(row: dict[str, Any]) -> bool:
    text = _str_field(row, "proposition_text")
    conditions = _list_field(row, "conditions")
    modals = len(_MODAL_RE.findall(text))
    semicolons = text.count(";")
    if modals >= 2 and (semicolons >= 2 or len(conditions) >= 3):
        return True
    if len(conditions) >= 4:
        return True
    if len(text) > 420 and modals >= 2 and semicolons >= 1:
        return True
    return False


def _label_misaligned(row: dict[str, Any]) -> bool:
    effect = _str_field(row, "legal_effect_type")
    label = _str_field(row, "label").lower()
    if not label:
        return True
    if effect == LegalEffectType.DEFINITION.value and any(
        w in label for w in ("obligation", "prohibition", "must ", "shall ")
    ):
        return True
    if effect == LegalEffectType.OBLIGATION.value and label.startswith("definition"):
        return True
    return False


def _load_extraction_failures(export_dir: Path) -> list[dict[str, Any]]:
    path = export_dir / "proposition_extraction_failures.json"
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


def _load_completeness_by_prop(export_dir: Path) -> dict[str, dict[str, Any]]:
    path = export_dir / "proposition_completeness_assessments.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("proposition_id") or item.get("id") or "").strip()
        if pid:
            out[pid] = item
    return out


def _compare_exports(
    current_dir: Path,
    baseline_dir: Path | None,
    *,
    current_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if baseline_dir is None or not (baseline_dir / "propositions.json").is_file():
        return {"baseline_available": False}
    baseline_rows = load_slurry_export_propositions(baseline_dir)
    cur_ids = {_str_field(r, "id") for r in current_rows}
    base_ids = {_str_field(r, "id") for r in baseline_rows}
    cur_frags = {_str_field(r, "source_fragment_id") for r in current_rows}
    base_frags = {_str_field(r, "source_fragment_id") for r in baseline_rows}

    def dup_id_count(rows: list[dict[str, Any]]) -> int:
        c = Counter(_str_field(r, "id") for r in rows)
        return sum(1 for n in c.values() if n > 1)

    def exact_text_groups(rows: list[dict[str, Any]]) -> int:
        g: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            key = _normalize_text(_str_field(r, "proposition_text"))
            if key:
                g[key].append(_str_field(r, "id"))
        return sum(1 for ids in g.values() if len(ids) > 1)

    def val_warn_count(rows: list[dict[str, Any]]) -> int:
        return sum(1 for r in rows if _extraction_meta(r).get("validation_errors"))

    npp_reg2_cur = sum(
        1 for r in current_rows if _str_field(r, "source_fragment_id") == "frag-lex-120b4f9c395b3f94-002"
    )
    npp_reg2_base = sum(
        1 for r in baseline_rows if _str_field(r, "source_fragment_id") == "frag-lex-120b4f9c395b3f94-002"
    )
    wales_sch2_cur = sum(
        1
        for r in current_rows
        if _str_field(r, "source_fragment_id") == "frag-lex-805b03f284dcf364-080"
    )
    wales_sch2_base = sum(
        1
        for r in baseline_rows
        if _str_field(r, "source_fragment_id") == "frag-lex-805b03f284dcf364-080"
    )

    improved: list[str] = []
    worsened: list[str] = []
    if len(current_rows) > len(baseline_rows):
        improved.append(f"proposition_count +{len(current_rows) - len(baseline_rows)}")
    elif len(current_rows) < len(baseline_rows):
        worsened.append(f"proposition_count {len(current_rows) - len(baseline_rows)}")

    if dup_id_count(current_rows) < dup_id_count(baseline_rows):
        improved.append("duplicate_proposition_id_count reduced")
    elif dup_id_count(current_rows) > dup_id_count(baseline_rows):
        worsened.append("duplicate_proposition_id_count increased")

    if val_warn_count(current_rows) > val_warn_count(baseline_rows):
        worsened.append(
            f"validation_warning_propositions +{val_warn_count(current_rows) - val_warn_count(baseline_rows)}"
        )
    elif val_warn_count(current_rows) < val_warn_count(baseline_rows):
        improved.append("validation_warning_propositions reduced")

    if npp_reg2_base and not npp_reg2_cur:
        worsened.append("NPP regulation:2 definitions lost (parse failure on fresh extract)")
    if not npp_reg2_base and npp_reg2_cur:
        improved.append("NPP regulation:2 definitions present")

    overall = "mixed"
    if worsened and not improved:
        overall = "worsened"
    elif improved and not worsened:
        overall = "improved"
    elif not worsened and not improved:
        overall = "unchanged"

    return {
        "baseline_available": True,
        "baseline_export_dir": str(baseline_dir.resolve()),
        "current_proposition_count": len(current_rows),
        "baseline_proposition_count": len(baseline_rows),
        "duplicate_id_count_current": dup_id_count(current_rows),
        "duplicate_id_count_baseline": dup_id_count(baseline_rows),
        "exact_text_duplicate_groups_current": exact_text_groups(current_rows),
        "exact_text_duplicate_groups_baseline": exact_text_groups(baseline_rows),
        "validation_warning_propositions_current": val_warn_count(current_rows),
        "validation_warning_propositions_baseline": val_warn_count(baseline_rows),
        "npp_reg2_fragment_propositions_current": npp_reg2_cur,
        "npp_reg2_fragment_propositions_baseline": npp_reg2_base,
        "wales_schedule2_fragment_propositions_current": wales_sch2_cur,
        "wales_schedule2_fragment_propositions_baseline": wales_sch2_base,
        "proposition_ids_only_in_current": sorted(cur_ids - base_ids)[:50],
        "proposition_ids_only_in_baseline": sorted(base_ids - cur_ids)[:50],
        "improved": improved,
        "worsened": worsened,
        "overall_vs_baseline": overall,
    }


@dataclass(frozen=True)
class SuspiciousPropositionReview:
    export_dir: str
    proposition_count: int
    generated_from: str
    summary: dict[str, Any]
    duplicate_analysis: dict[str, Any]
    quality_sections: dict[str, Any]
    known_issues: dict[str, Any]
    findings: list[SuspiciousFinding]
    comparison_with_baseline: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_dir": self.export_dir,
            "proposition_count": self.proposition_count,
            "generated_from": self.generated_from,
            "summary": self.summary,
            "duplicate_analysis": self.duplicate_analysis,
            "quality_sections": self.quality_sections,
            "known_issues": self.known_issues,
            "comparison_with_baseline": self.comparison_with_baseline,
            "findings": [f.to_dict() for f in self.findings],
            "finding_counts_by_severity": dict(
                Counter(f.severity for f in self.findings)
            ),
        }


def build_suspicious_proposition_review(
    propositions: list[dict[str, Any]],
    *,
    export_dir: str | Path,
    sources_by_id: dict[str, dict[str, Any]] | None = None,
    baseline_export_dir: str | Path | None = None,
) -> SuspiciousPropositionReview:
    """Build duplicate and quality review (deterministic)."""
    root = Path(export_dir).resolve()
    sources = sources_by_id if sources_by_id is not None else load_export_sources(root)
    rows = sorted(
        [p for p in propositions if isinstance(p, dict) and _str_field(p, "id")],
        key=_sort_key_row,
    )
    findings: list[SuspiciousFinding] = []

    # --- A1 exact duplicate text ---
    by_text: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _normalize_text(_str_field(row, "proposition_text"))
        if key:
            by_text[key].append(row)

    exact_dup_groups: list[dict[str, Any]] = []
    for text_key, group in sorted(by_text.items(), key=lambda kv: -len(kv[1])):
        if len(group) <= 1:
            continue
        members = [_row_context(row, sources) for row in group]
        same_source = len({m["source_id"] for m in members}) == 1
        for row in group:
            findings.append(
                _finding_from_row(
                    row,
                    sources,
                    severity="warning" if same_source else "info",
                    reason="Exact duplicate normalised proposition_text within export",
                    recommended_action="duplicate_key_fix" if same_source else "accept",
                    duplicate_classification=(
                        "true_duplicate" if same_source else "legitimate_repeated_legal_pattern"
                    ),
                    extra={
                        "group_size": len(group),
                        "peer_ids": [m["proposition_id"] for m in members],
                    },
                )
            )
        exact_dup_groups.append(
            {
                "normalized_text_preview": text_key[:160],
                "size": len(group),
                "members": members,
            }
        )

    # --- A2 same source + locator + similar text ---
    by_src_loc: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sid = _str_field(row, "source_record_id")
        loc = _locator(row).lower()
        if sid and loc:
            by_src_loc[(sid, loc)].append(row)

    near_dup_pairs: list[dict[str, Any]] = []
    for (sid, loc), group in sorted(by_src_loc.items(), key=lambda kv: -len(kv[1])):
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                sim = _text_similarity(
                    _str_field(a, "proposition_text"),
                    _str_field(b, "proposition_text"),
                )
                if sim < SIMILARITY_THRESHOLD:
                    continue
                same_effect = _str_field(a, "legal_effect_type") == _str_field(
                    b, "legal_effect_type"
                )
                classification: DuplicateClassification = (
                    "true_duplicate" if sim >= 0.98 and same_effect else "semantic_comparison_candidate"
                )
                severity: Severity = "error" if sim >= 0.98 and same_effect else "warning"
                near_dup_pairs.append(
                    {
                        "source_id": sid,
                        "locator": loc,
                        "similarity": round(sim, 4),
                        "proposition_ids": [_str_field(a, "id"), _str_field(b, "id")],
                        "classification": classification,
                    }
                )
                for row in (a, b):
                    findings.append(
                        _finding_from_row(
                            row,
                            sources,
                            severity=severity,
                            reason=(
                                f"Same source+locator high text similarity ({sim:.2f}); "
                                f"same legal_effect={same_effect}"
                            ),
                            recommended_action="duplicate_key_fix"
                            if classification == "true_duplicate"
                            else "human_legal_review",
                            duplicate_classification=classification,
                            extra={"similarity": round(sim, 4), "peer_id": _str_field(b, "id")},
                        )
                    )

    # --- A3 duplicate proposition id ---
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_id[_str_field(row, "id")].append(row)

    duplicate_id_groups: list[dict[str, Any]] = []
    for pid, group in sorted(by_id.items()):
        if len(group) <= 1:
            continue
        duplicate_id_groups.append(
            {
                "proposition_id": pid,
                "count": len(group),
                "locators": [_locator(r) for r in group],
                "source_fragment_ids": [_str_field(r, "source_fragment_id") for r in group],
            }
        )
        for row in group:
            findings.append(
                _finding_from_row(
                    row,
                    sources,
                    severity="error",
                    reason="Duplicate proposition id appears more than once in export array",
                    recommended_action="duplicate_key_fix",
                    duplicate_classification="duplicate_proposition_id",
                    extra={"occurrence_count": len(group)},
                )
            )

    # --- A3b source_scoped_key ---
    by_ssk: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _str_field(row, "source_scoped_key")
        if key:
            by_ssk[key].append(row)

    source_scoped_key_groups: list[dict[str, Any]] = []
    for key, group in sorted(by_ssk.items(), key=lambda kv: -len(kv[1])):
        if len(group) <= 1:
            continue
        member_dicts = [_row_context(r, sources) for r in group]
        classification = _classify_source_scoped_key_group(member_dicts)
        source_scoped_key_groups.append(
            {
                "source_scoped_key": key,
                "size": len(group),
                "classification": classification,
                "members": member_dicts,
            }
        )
        if classification in {"true_duplicate", "key_too_coarse", "duplicate_proposition_id"}:
            sev: Severity = "error" if classification == "true_duplicate" else "warning"
            for row in group:
                findings.append(
                    _finding_from_row(
                        row,
                        sources,
                        severity=sev,
                        reason=f"Shared source_scoped_key ({len(group)} rows): {classification}",
                        recommended_action="duplicate_key_fix",
                        duplicate_classification=classification,
                        extra={"source_scoped_key": key, "group_size": len(group)},
                    )
                )

    # --- A4 semantic comparison buckets ---
    semantic_buckets = _build_semantic_comparison_buckets(rows, sources)
    top_buckets = semantic_buckets[:30]
    flagged_semantic: list[dict[str, Any]] = []
    for bucket in semantic_buckets:
        member_rows = [r for r in rows if _str_field(r, "semantic_comparison_key") == bucket.semantic_comparison_key]
        if len(member_rows) < 2:
            continue
        texts = [_str_field(r, "proposition_text") for r in member_rows]
        max_sim = 0.0
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                max_sim = max(max_sim, _text_similarity(texts[i], texts[j]))
        sources_in = {m["source_record_id"] for m in bucket.members}
        if len(sources_in) == 1:
            continue
        if max_sim >= SIMILARITY_THRESHOLD:
            flagged_semantic.append(
                {
                    "semantic_comparison_key": bucket.semantic_comparison_key,
                    "size": bucket.size,
                    "max_pairwise_similarity": round(max_sim, 4),
                    "members": bucket.members,
                }
            )
            for row in member_rows:
                findings.append(
                    _finding_from_row(
                        row,
                        sources,
                        severity="info",
                        reason=(
                            "Semantic comparison bucket: cross-source near-duplicate text "
                            f"(max sim {max_sim:.2f})"
                        ),
                        recommended_action="accept",
                        duplicate_classification="semantic_comparison_candidate",
                        extra={"bucket_size": bucket.size},
                    )
                )

    # --- A5 locator high counts ---
    by_loc: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sid = _str_field(row, "source_record_id")
        loc = _locator(row)
        if sid and loc:
            by_loc[(sid, loc)].append(row)

    high_locator_groups: list[dict[str, Any]] = []
    for (sid, loc), group in sorted(by_loc.items(), key=lambda kv: -len(kv[1])):
        threshold = (
            _LOCATOR_HIGH_COUNT_SCHEDULE
            if _SCHEDULE_LOCATOR_RE.search(loc)
            else _LOCATOR_HIGH_COUNT_DEFAULT
        )
        if len(group) < threshold:
            continue
        is_table_schedule = _SCHEDULE_LOCATOR_RE.search(loc) or _TABLE_LOCATOR_RE.search(loc)
        is_reg1 = bool(_REG1_BOILERPLATE_RE.search(loc))
        classification: DuplicateClassification = "table_row" if is_table_schedule else "info"
        severity: Severity = "info"
        reason = f"Locator has {len(group)} propositions (high count; review only)"
        if is_reg1:
            reason += " — regulation 1 boilerplate cluster"
        high_locator_groups.append(
            {
                "source_id": sid,
                "source_title": _source_title(sid, sources),
                "locator": loc,
                "count": len(group),
                "classification": classification,
                "note": "expected for tables/schedules" if is_table_schedule else "review split granularity",
            }
        )
        if not is_table_schedule and len(group) >= threshold + 5:
            for row in group[:3]:
                findings.append(
                    _finding_from_row(
                        row,
                        sources,
                        severity=severity,
                        reason=reason,
                        recommended_action="accept",
                        duplicate_classification=classification,
                    )
                )

    # --- B quality sections ---
    unknown_rows: list[dict[str, Any]] = []
    for row in rows:
        tier = _str_field(row, "proposition_tier")
        effect = _str_field(row, "legal_effect_type")
        if tier != PropositionTier.UNKNOWN.value and effect != LegalEffectType.UNKNOWN.value:
            if tier and effect:
                continue
        unknown_rows.append(_row_context(row, sources) | {"recommended_classifier_rule": _unknown_classifier_hint(row)})
        findings.append(
            _finding_from_row(
                row,
                sources,
                severity="warning",
                reason="Unknown proposition_tier or legal_effect_type",
                recommended_action="classifier_fix",
                extra={"recommended_classifier_rule": _unknown_classifier_hint(row)},
            )
        )

    validation_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        errs = _extraction_meta(row).get("validation_errors") or []
        if not isinstance(errs, list) or not errs:
            continue
        types = {_validation_warning_type(str(e)) for e in errs}
        ctx = _row_context(row, sources)
        for wtype in sorted(types):
            validation_by_type[wtype].append(ctx | {"validation_errors": errs})
        findings.append(
            _finding_from_row(
                row,
                sources,
                severity="warning",
                reason=f"Validation warnings: {', '.join(sorted(types))}",
                recommended_action="evidence_matcher_fix"
                if "evidence_traceability" in types
                else "prompt-lab_fixture_needed",
                extra={"warning_types": sorted(types), "validation_errors": errs[:5]},
            )
        )

    trace_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        warns = _extraction_meta(row).get("trace_warnings") or []
        if not isinstance(warns, list) or not warns:
            continue
        for w in warns:
            wstr = str(w)
            trace_by_type[wstr].append(_row_context(row, sources))
        findings.append(
            _finding_from_row(
                row,
                sources,
                severity="info",
                reason=f"Trace warnings: {', '.join(str(w) for w in warns)}",
                recommended_action="evidence_matcher_fix",
                extra={"trace_warnings": warns},
            )
        )

    completeness_by_prop = _load_completeness_by_prop(root)
    fragmentary_rows: list[dict[str, Any]] = []
    for row in rows:
        pid = _str_field(row, "id")
        meta_status = str(_extraction_meta(row).get("completeness_status") or "")
        assess = completeness_by_prop.get(pid, {})
        assess_status = str(assess.get("status") or "")
        status = meta_status or assess_status
        if status not in {"fragmentary", "context_dependent"}:
            continue
        expected = _str_field(row, "legal_effect_type") in {
            LegalEffectType.CROSS_REFERENCE.value,
            LegalEffectType.DEFINITION.value,
        } or "schedule" in _locator(row).lower()
        fragmentary_rows.append(
            _row_context(row, sources)
            | {
                "completeness_status": status,
                "expected_context_dependent": expected,
            }
        )
        if status == "fragmentary" and not expected:
            findings.append(
                _finding_from_row(
                    row,
                    sources,
                    severity="warning",
                    reason="Fragmentary proposition without obvious cross-ref/schedule context",
                    recommended_action="human_legal_review",
                )
            )

    scope_missing: list[dict[str, Any]] = []
    scope_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if _str_field(row, "legal_effect_type") != LegalEffectType.APPLICATION_SCOPE.value:
            continue
        terr = _list_field(row, "territorial_application")
        sid = _str_field(row, "source_record_id")
        inheritable = _infer_territory_from_source(sid, sources)
        ctx = _row_context(row, sources) | {
            "territorial_application": terr,
            "inheritable_territory": inheritable,
            "matters_for_divergence": not terr and not inheritable,
        }
        scope_by_source[sid].append(ctx)
        if terr:
            continue
        scope_missing.append(ctx)
        action: RecommendedAction = "classifier_fix" if inheritable else "human_legal_review"
        findings.append(
            _finding_from_row(
                row,
                sources,
                severity="info" if inheritable else "warning",
                reason="Application-scope row missing territorial_application"
                + (f"; may inherit {inheritable}" if inheritable else ""),
                recommended_action=action,
                extra={"inheritable_territory": inheritable},
            )
        )

    weak_compliance: list[dict[str, Any]] = []
    for row in rows:
        if not _is_strict_weak_compliance(row):
            continue
        weak_compliance.append(_row_context(row, sources))
        findings.append(
            _finding_from_row(
                row,
                sources,
                severity="warning",
                reason="Compliance-relevant row with weak legal_subject/action (strict heuristic)",
                recommended_action="prompt-lab_fixture_needed",
            )
        )

    over_compressed: list[dict[str, Any]] = []
    for row in rows:
        if not _is_over_compressed(row):
            continue
        loc = _locator(row).lower()
        over_compressed.append(_row_context(row, sources) | {"condition_count": len(_list_field(row, "conditions"))})
        sev: Severity = "warning" if "regulation 8" in loc or "regulation:8" in loc else "info"
        findings.append(
            _finding_from_row(
                row,
                sources,
                severity=sev,
                reason="Over-compressed proposition (multiple modals/conditions in one row)",
                recommended_action="human_legal_review",
                duplicate_classification="same_rule_split_into_conditions",
            )
        )

    suspicious_labels: list[dict[str, Any]] = []
    for row in rows:
        label = _str_field(row, "label")
        issues: list[str] = []
        if label and is_generic_display_label(label):
            issues.append("generic_label")
        if len(label) > _LABEL_LONG_CHARS:
            issues.append("label_over_120_chars")
        if _label_misaligned(row):
            issues.append("label_effect_mismatch")
        if not issues:
            continue
        suspicious_labels.append(_row_context(row, sources) | {"label_issues": issues})
        findings.append(
            _finding_from_row(
                row,
                sources,
                severity="info",
                reason=f"Suspicious label: {', '.join(issues)}",
                recommended_action="classifier_fix" if "label_effect_mismatch" in issues else "accept",
                extra={"label_issues": issues},
            )
        )

    table_rows: list[dict[str, Any]] = []
    for row in rows:
        if not _is_table_like(row):
            continue
        effect = _str_field(row, "legal_effect_type")
        meta = _extraction_meta(row)
        table_rows.append(
            _row_context(row, sources)
            | {
                "evidence_match_strategy": meta.get("evidence_match_strategy"),
                "has_numeric_tokens": bool(_NUMERIC_TOKEN_RE.search(_str_field(row, "proposition_text"))),
            }
        )
        if effect == LegalEffectType.UNKNOWN.value:
            findings.append(
                _finding_from_row(
                    row,
                    sources,
                    severity="warning",
                    reason="Table-like row classified as legal_effect_type unknown",
                    recommended_action="classifier_fix",
                    duplicate_classification="table_row",
                )
            )

    # --- D known issues ---
    failures = _load_extraction_failures(root)
    npp_reg2_failure = next(
        (f for f in failures if f.get("source_fragment_id") == "frag-lex-120b4f9c395b3f94-002"),
        None,
    )
    wales_sch2_failure = next(
        (f for f in failures if f.get("source_fragment_id") == "frag-lex-805b03f284dcf364-080"),
        None,
    )

    known_issues = {
        "npp_2015_regulation_2": {
            "present_in_export": any(
                _str_field(r, "source_fragment_id") == "frag-lex-120b4f9c395b3f94-002" for r in rows
            ),
            "extraction_failure": npp_reg2_failure is not None,
            "failure_summary": (npp_reg2_failure or {}).get("failure_reason"),
            "recommendation": "targeted re-extract after JSON parser fix (escaped quotes in evidence_text)",
        },
        "wales_schedule_2": {
            "present_in_export": any(
                _str_field(r, "source_fragment_id") == "frag-lex-805b03f284dcf364-080" for r in rows
            ),
            "extraction_failure": wales_sch2_failure is not None,
            "failure_summary": (wales_sch2_failure or {}).get("failure_reason"),
            "substantive_loss_likely_low": True,
            "note": "Model returned empty propositions plus prose after JSON fence; fragment is fruit species reference table",
        },
        "unknown_classifications": unknown_rows,
        "application_scope_missing_territory": {
            "count": len(scope_missing),
            "by_source": {sid: items for sid, items in scope_by_source.items() if any(not i.get("territorial_application") for i in items)},
            "territory_inheritance_recommendation": (
                "Populate territorial_application from source title/jurisdiction for England/Wales/Scotland instruments"
            ),
        },
    }

    baseline_path = Path(baseline_export_dir) if baseline_export_dir else None
    comparison = _compare_exports(root, baseline_path, current_rows=rows)

    dup_blocker = bool(duplicate_id_groups) or any(
        g["classification"] == "true_duplicate"
        for g in source_scoped_key_groups
        if g["classification"] == "true_duplicate"
    )

    top_dup = sorted(
        [
            *[
                {
                    "kind": "duplicate_id",
                    "detail": g,
                    "severity": "error",
                }
                for g in duplicate_id_groups
            ],
            *[
                {
                    "kind": "exact_text",
                    "detail": g,
                    "severity": "warning",
                }
                for g in exact_dup_groups[:10]
            ],
            *[
                {
                    "kind": "near_dup_same_locator",
                    "detail": p,
                    "severity": p.get("classification"),
                }
                for p in sorted(near_dup_pairs, key=lambda x: -x["similarity"])[:10]
            ],
        ],
        key=lambda x: 0 if x["severity"] == "error" else 1,
    )[:15]

    top_quality = [
        {"kind": "npp_reg2_missing", "severity": "error" if npp_reg2_failure else "info"},
        {"kind": "validation_warnings", "count": sum(len(v) for v in validation_by_type.values())},
        {"kind": "unknown_classifications", "count": len(unknown_rows)},
        {"kind": "weak_compliance", "count": len(weak_compliance)},
        {"kind": "scope_missing_territory", "count": len(scope_missing)},
    ]

    priority_fixes = []
    if npp_reg2_failure:
        priority_fixes.append("Fix JSON extraction repair for quoted evidence_text; targeted re-extract NPP regulation:2")
    if duplicate_id_groups:
        priority_fixes.append("Deduplicate export proposition ids (merge chunk-level duplicates)")
    if validation_by_type.get("evidence_traceability"):
        priority_fixes.append("Tune evidence matcher for table rows / multi-row chunks")
    if unknown_rows:
        priority_fixes.append("Add classifier rules for table numeric rows → obligation + substantive_rule")
    if scope_missing:
        priority_fixes.append("Territory inheritance pass for application_scope rows")
    if failures:
        priority_fixes.append("Harden parser against JSON+prose responses (Wales schedule:2 pattern)")
    if not priority_fixes:
        priority_fixes.append("No P0 blockers; continue divergence review on semantic buckets")

    summary = {
        "proposition_count": len(rows),
        "duplicate_proposition_id_groups": len(duplicate_id_groups),
        "exact_text_duplicate_groups": len(exact_dup_groups),
        "near_duplicate_same_locator_pairs": len(near_dup_pairs),
        "source_scoped_key_multi_groups": len(source_scoped_key_groups),
        "semantic_comparison_buckets_multi": len(semantic_buckets),
        "semantic_buckets_flagged_cross_source": len(flagged_semantic),
        "high_locator_groups": len(high_locator_groups),
        "unknown_classifications": len(unknown_rows),
        "validation_warning_propositions": sum(len(v) for v in validation_by_type.values()),
        "trace_warning_propositions": sum(len(v) for v in trace_by_type.values()),
        "fragmentary_or_context_dependent": len(fragmentary_rows),
        "application_scope_missing_territory": len(scope_missing),
        "weak_compliance_rows": len(weak_compliance),
        "over_compressed_rows": len(over_compressed),
        "suspicious_label_rows": len(suspicious_labels),
        "table_like_rows": len(table_rows),
        "duplicates_are_blocker": dup_blocker,
        "top_duplicate_concerns": top_dup,
        "top_quality_concerns": top_quality,
        "recommended_priority_fixes": priority_fixes,
    }

    return SuspiciousPropositionReview(
        export_dir=str(root),
        proposition_count=len(rows),
        generated_from="propositions.json",
        summary=summary,
        duplicate_analysis={
            "exact_duplicate_text": exact_dup_groups,
            "near_duplicate_same_source_locator": near_dup_pairs,
            "duplicate_proposition_ids": duplicate_id_groups,
            "source_scoped_key_groups": source_scoped_key_groups,
            "semantic_comparison_top_30": [b.to_dict() for b in top_buckets],
            "semantic_comparison_flagged": flagged_semantic,
            "high_locator_counts": high_locator_groups,
        },
        quality_sections={
            "unknown_classifications": unknown_rows,
            "validation_warnings_by_type": dict(validation_by_type),
            "trace_warnings_by_type": dict(trace_by_type),
            "fragmentary_and_context_dependent": fragmentary_rows,
            "application_scope_missing_territory": scope_missing,
            "weak_compliance_actor_action": weak_compliance,
            "over_compressed": over_compressed,
            "suspicious_labels": suspicious_labels,
            "table_numeric_rows": table_rows,
        },
        known_issues=known_issues,
        findings=findings,
        comparison_with_baseline=comparison,
    )


def _unknown_classifier_hint(row: dict[str, Any]) -> str:
    loc = _locator(row).lower()
    text = _str_field(row, "proposition_text").lower()
    if "table row" in loc or "column" in loc:
        if "%" in text or "kg" in text or "grams" in text:
            return "classify table numeric standard values as obligation + substantive_rule (not unknown)"
    if "schedule 1" in loc and "produce" in text:
        return "classify livestock manure production table rows as obligation + substantive_rule"
    if "regulation 30" in loc and "notice" in text:
        return "classify procedural notice scope as procedural_rule + notification or application_scope"
    return "review legal_effect_type and proposition_tier against proposition_text modal verbs"


def render_suspicious_proposition_review_md(review: SuspiciousPropositionReview) -> str:
    """Render markdown report."""
    s = review.summary
    lines = [
        "# Suspicious proposition review",
        "",
        f"Export: `{review.export_dir}`",
        f"Propositions: **{review.proposition_count}**",
        "",
        "_Deterministic review. No LLM. Semantic buckets and cross-jurisdiction matches are hints, not automatic defects._",
        "",
        "## Executive summary",
        "",
        f"- **Duplicates blocker:** {'yes' if s.get('duplicates_are_blocker') else 'no'} "
        f"({s.get('duplicate_proposition_id_groups', 0)} duplicate id group(s), "
        f"{s.get('exact_text_duplicate_groups', 0)} exact-text group(s))",
        f"- **Unknown classifications:** {s.get('unknown_classifications', 0)}",
        f"- **Validation-warning propositions:** {s.get('validation_warning_propositions', 0)}",
        f"- **Trace-warning propositions:** {s.get('trace_warning_propositions', 0)}",
        f"- **Application-scope missing territory:** {s.get('application_scope_missing_territory', 0)}",
        "",
        "### Top duplicate concerns",
        "",
    ]
    for item in s.get("top_duplicate_concerns") or []:
        lines.append(f"- `{item.get('kind')}`: {json.dumps(item.get('detail'), ensure_ascii=False)[:240]}")
    lines.extend(["", "### Top quality concerns", ""])
    for item in s.get("top_quality_concerns") or []:
        lines.append(f"- `{item.get('kind')}`: {item}")
    lines.extend(["", "### Recommended priority fixes", ""])
    for fix in s.get("recommended_priority_fixes") or []:
        lines.append(f"1. {fix}")

    cmp_ = review.comparison_with_baseline
    if cmp_.get("baseline_available"):
        lines.extend(
            [
                "",
                "## Comparison with baseline export",
                "",
                f"Baseline: `{cmp_.get('baseline_export_dir')}`",
                f"Overall: **{cmp_.get('overall_vs_baseline')}**",
                "",
                "| Metric | Current | Baseline |",
                "| --- | ---: | ---: |",
                f"| Propositions | {cmp_.get('current_proposition_count')} | {cmp_.get('baseline_proposition_count')} |",
                f"| Duplicate proposition ids | {cmp_.get('duplicate_id_count_current')} | {cmp_.get('duplicate_id_count_baseline')} |",
                f"| Exact-text duplicate groups | {cmp_.get('exact_text_duplicate_groups_current')} | {cmp_.get('exact_text_duplicate_groups_baseline')} |",
                f"| Validation-warning props | {cmp_.get('validation_warning_propositions_current')} | {cmp_.get('validation_warning_propositions_baseline')} |",
                f"| NPP reg:2 fragment props | {cmp_.get('npp_reg2_fragment_propositions_current')} | {cmp_.get('npp_reg2_fragment_propositions_baseline')} |",
                "",
            ]
        )
        if cmp_.get("improved"):
            lines.append("**Improved:** " + "; ".join(cmp_["improved"]))
        if cmp_.get("worsened"):
            lines.append("**Worsened:** " + "; ".join(cmp_["worsened"]))

    lines.extend(["", "## A. Duplicate / near-duplicate analysis", ""])
    lines.append(f"### A1 Exact duplicate text ({len(review.duplicate_analysis.get('exact_duplicate_text', []))} groups)")
    lines.append("")
    for g in (review.duplicate_analysis.get("exact_duplicate_text") or [])[:20]:
        lines.append(f"- size {g['size']}: " + ", ".join(m["proposition_id"] for m in g["members"]))

    lines.append("")
    lines.append("### A2 Same source + locator + similar text")
    for p in (review.duplicate_analysis.get("near_duplicate_same_source_locator") or [])[:25]:
        lines.append(
            f"- `{p['source_id']}` `{p['locator']}` sim={p['similarity']} "
            f"{p['classification']}: {p['proposition_ids']}"
        )

    lines.append("")
    lines.append("### A3 Duplicate proposition ids")
    for g in review.duplicate_analysis.get("duplicate_proposition_ids") or []:
        lines.append(f"- **{g['proposition_id']}** ×{g['count']} frags={g['source_fragment_ids']}")

    lines.append("")
    lines.append("### A3b Source-scoped key collisions (suspicious only)")
    for g in review.duplicate_analysis.get("source_scoped_key_groups") or []:
        if g["classification"] not in {"true_duplicate", "key_too_coarse"}:
            continue
        lines.append(f"- `{g['source_scoped_key']}` ({g['classification']}, size {g['size']})")

    lines.append("")
    lines.append("### A4 Semantic comparison (top 30 buckets)")
    for b in review.duplicate_analysis.get("semantic_comparison_top_30") or []:
        lines.append(f"- size {b['size']}: `{b['semantic_comparison_key'][:80]}`")

    lines.append("")
    lines.append("### A5 High locator counts")
    for g in review.duplicate_analysis.get("high_locator_counts") or [][:15]:
        lines.append(f"- {g['source_title'][:40]}… `{g['locator']}`: **{g['count']}** ({g['classification']})")

    lines.extend(["", "## B. Suspicious quality", ""])
    ki = review.known_issues
    lines.append("### D1 NPP 2015 regulation:2")
    lines.append(json.dumps(ki.get("npp_2015_regulation_2"), indent=2))
    lines.append("")
    lines.append("### D2 Wales schedule:2")
    lines.append(json.dumps(ki.get("wales_schedule_2"), indent=2))

    qs = review.quality_sections
    lines.append("")
    lines.append("### B1 Unknown classifications")
    for row in qs.get("unknown_classifications") or []:
        lines.append(
            f"- `{row['proposition_id']}` {row['locator']}: {row['label'][:60]} — "
            f"{row.get('recommended_classifier_rule', '')}"
        )

    return "\n".join(lines).rstrip() + "\n"


def write_suspicious_proposition_review(
    export_dir: str | Path,
    review: SuspiciousPropositionReview,
) -> tuple[Path, Path]:
    root = Path(export_dir)
    md_path = root / REVIEW_MD_FILENAME
    json_path = root / REVIEW_JSON_FILENAME
    md_path.write_text(render_suspicious_proposition_review_md(review), encoding="utf-8")
    json_path.write_text(
        json.dumps(review.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return md_path, json_path


def build_review_from_export_dir(
    export_dir: str | Path,
    *,
    baseline_export_dir: str | Path | None = None,
) -> SuspiciousPropositionReview:
    root = Path(export_dir)
    props = load_slurry_export_propositions(root)
    sources = load_export_sources(root)
    baseline = baseline_export_dir
    if baseline is None:
        candidate = root.parent / "slurry-gb-principal-5-frontier-export"
        if candidate.is_dir() and (candidate / "propositions.json").is_file():
            baseline = candidate
    return build_suspicious_proposition_review(
        props,
        export_dir=root,
        sources_by_id=sources,
        baseline_export_dir=baseline,
    )
