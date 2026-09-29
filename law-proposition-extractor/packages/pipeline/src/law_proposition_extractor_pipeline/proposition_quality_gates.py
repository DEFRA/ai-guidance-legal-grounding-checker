"""Structured quality gates for post-extraction proposition normalisation."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import LegalEffectType, Proposition, should_preserve_existing_label
from law_proposition_extractor_domain.proposition_classification import (
    application_scope_requires_territory,
    classify_application_scope_kind,
)
from law_proposition_extractor_domain.proposition_notes import EXTRACTION_META_PREFIX

Severity = Literal["warning", "error"]

GENERIC_QUALITY_GATE_LABELS = frozenset(
    {
        "territorial application",
        "citation",
        "commencement date",
        "extent",
    }
)

DANGEROUS_LEGACY_KEY_PREFIX = "uk:these-regulations:"

_CHECK_MESSAGES: dict[str, str] = {
    "legacy_category_conflict": "legacy category conflicts with normalised classification",
    "scope_application_conflict": "territorial application_scope without territorial_application",
    "extent_conflict": "extent effect without extent values",
    "generic_label_still_present": "generic display label still present after normalisation",
    "dangerous_legacy_relationship_key": "legacy generic cross_reference_key retained after normalisation",
    "debug_leakage": "extraction debug metadata leaked into human-facing notes",
    "missing_source_scoped_key": "missing source_scoped_key for keyed proposition",
    "comparison_anchor_mismatch": "comparison anchor set on citation or commencement row",
}


@dataclass(frozen=True)
class PropositionQualityFinding:
    check_id: str
    severity: Severity
    message: str
    proposition_id: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "message": self.message,
            "proposition_id": self.proposition_id,
            "details": self.details,
        }


@dataclass
class PropositionQualityReport:
    proposition_count: int
    error_count: int
    warning_count: int
    newly_normalised: bool
    findings: list[PropositionQualityFinding] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: _utc_now_iso_z())

    def to_dict(self) -> dict[str, Any]:
        by_check: dict[str, dict[str, int]] = {}
        for finding in self.findings:
            bucket = by_check.setdefault(
                finding.check_id,
                {"warnings": 0, "errors": 0},
            )
            if finding.severity == "error":
                bucket["errors"] += 1
            else:
                bucket["warnings"] += 1
        return {
            "generated_at": self.generated_at,
            "proposition_count": self.proposition_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "newly_normalised": self.newly_normalised,
            "findings": [f.to_dict() for f in self.findings],
            "by_check": by_check,
        }


def _utc_now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _field(prop: Proposition | dict[str, Any], name: str, default: Any = None) -> Any:
    if isinstance(prop, dict):
        return prop.get(name, default)
    return getattr(prop, name, default)


def _legal_effect(prop: Proposition | dict[str, Any]) -> LegalEffectType:
    raw = _field(prop, "legal_effect_type")
    if isinstance(raw, LegalEffectType):
        return raw
    if raw:
        try:
            return LegalEffectType(str(raw))
        except ValueError:
            pass
    return LegalEffectType.UNKNOWN


def _categories(prop: Proposition | dict[str, Any]) -> list[str]:
    raw = _field(prop, "categories", [])
    return [str(c) for c in raw] if isinstance(raw, list) else []


def _non_empty_str(value: Any) -> bool:
    return bool(str(value or "").strip())


def _display_note_texts(prop: Proposition | dict[str, Any]) -> list[str]:
    texts: list[str] = []
    notes = _field(prop, "notes", "")
    if _non_empty_str(notes):
        texts.append(str(notes))
    meta = _field(prop, "extraction_debug_meta")
    if isinstance(meta, dict):
        for key in ("display_label", "display_notes"):
            val = meta.get(key)
            if _non_empty_str(val):
                texts.append(str(val))
    return texts


def _contains_meta_leakage(text: str) -> bool:
    return EXTRACTION_META_PREFIX in text


def check_proposition(
    prop: Proposition | dict[str, Any],
    *,
    newly_normalised: bool = True,
) -> list[PropositionQualityFinding]:
    """Run all normalisation quality checks on one proposition."""
    findings: list[PropositionQualityFinding] = []
    prop_id = str(_field(prop, "id", "proposition-unknown"))

    categories = _categories(prop)
    compliance = _field(prop, "is_compliance_relevant")
    # Warn when legacy LLM categories disagree with normalised compliance flag (not a hard error).
    if "obligation" in categories and compliance is False:
        findings.append(
            PropositionQualityFinding(
                check_id="legacy_category_conflict",
                severity="warning",
                message=_CHECK_MESSAGES["legacy_category_conflict"],
                proposition_id=prop_id,
                details={
                    "categories": categories,
                    "is_compliance_relevant": compliance,
                },
            )
        )

    effect = _legal_effect(prop)
    territorial = _field(prop, "territorial_application", [])
    if effect == LegalEffectType.APPLICATION_SCOPE and not (
        isinstance(territorial, list) and any(_non_empty_str(t) for t in territorial)
    ):
        scope_kind = classify_application_scope_kind(
            proposition_text=str(_field(prop, "proposition_text", "") or ""),
            action=str(_field(prop, "action", "") or ""),
            label=str(_field(prop, "label", "") or ""),
            object_text=str(_field(prop, "object_text", "") or ""),
            legal_subject=str(_field(prop, "legal_subject", "") or ""),
            affected_subjects=_field(prop, "affected_subjects", []) or [],
        )
        if application_scope_requires_territory(
            proposition_text=str(_field(prop, "proposition_text", "") or ""),
            action=str(_field(prop, "action", "") or ""),
            label=str(_field(prop, "label", "") or ""),
            object_text=str(_field(prop, "object_text", "") or ""),
            legal_subject=str(_field(prop, "legal_subject", "") or ""),
            affected_subjects=_field(prop, "affected_subjects", []) or [],
        ):
            findings.append(
                PropositionQualityFinding(
                    check_id="scope_application_conflict",
                    severity="warning",
                    message=_CHECK_MESSAGES["scope_application_conflict"],
                    proposition_id=prop_id,
                    details={
                        "legal_effect_type": effect.value,
                        "territorial_application": territorial,
                        "application_scope_kind": scope_kind,
                    },
                )
            )

    extent_vals = _field(prop, "extent", [])
    if effect == LegalEffectType.EXTENT and not (
        isinstance(extent_vals, list) and any(_non_empty_str(v) for v in extent_vals)
    ):
        findings.append(
            PropositionQualityFinding(
                check_id="extent_conflict",
                severity="warning",
                message=_CHECK_MESSAGES["extent_conflict"],
                proposition_id=prop_id,
                details={"legal_effect_type": effect.value, "extent": extent_vals},
            )
        )

    label = str(_field(prop, "label", "") or "").strip()
    if label.casefold() in GENERIC_QUALITY_GATE_LABELS and not should_preserve_existing_label(label):
        findings.append(
            PropositionQualityFinding(
                check_id="generic_label_still_present",
                severity="warning",
                message=_CHECK_MESSAGES["generic_label_still_present"],
                proposition_id=prop_id,
                details={"label": label},
            )
        )

    xref_key = str(_field(prop, "cross_reference_key") or "").strip()
    if xref_key.startswith(DANGEROUS_LEGACY_KEY_PREFIX):
        severity: Severity = "error" if newly_normalised else "warning"
        findings.append(
            PropositionQualityFinding(
                check_id="dangerous_legacy_relationship_key",
                severity=severity,
                message=_CHECK_MESSAGES["dangerous_legacy_relationship_key"],
                proposition_id=prop_id,
                details={"cross_reference_key": xref_key},
            )
        )

    review_notes = _field(prop, "review_notes")
    if review_notes and _contains_meta_leakage(str(review_notes)):
        findings.append(
            PropositionQualityFinding(
                check_id="debug_leakage",
                severity="error",
                message=_CHECK_MESSAGES["debug_leakage"],
                proposition_id=prop_id,
                details={"field": "review_notes"},
            )
        )
    for note_text in _display_note_texts(prop):
        if _contains_meta_leakage(note_text):
            findings.append(
                PropositionQualityFinding(
                    check_id="debug_leakage",
                    severity="error",
                    message=_CHECK_MESSAGES["debug_leakage"],
                    proposition_id=prop_id,
                    details={"field": "display_notes"},
                )
            )
            break

    if effect not in {LegalEffectType.CITATION, LegalEffectType.COMMENCEMENT}:
        if not _non_empty_str(_field(prop, "source_scoped_key")):
            findings.append(
                PropositionQualityFinding(
                    check_id="missing_source_scoped_key",
                    severity="warning",
                    message=_CHECK_MESSAGES["missing_source_scoped_key"],
                    proposition_id=prop_id,
                    details={"legal_effect_type": effect.value},
                )
            )

    anchor = _field(prop, "is_comparison_anchor")
    if anchor is True and effect in {LegalEffectType.CITATION, LegalEffectType.COMMENCEMENT}:
        findings.append(
            PropositionQualityFinding(
                check_id="comparison_anchor_mismatch",
                severity="warning",
                message=_CHECK_MESSAGES["comparison_anchor_mismatch"],
                proposition_id=prop_id,
                details={
                    "legal_effect_type": effect.value,
                    "is_comparison_anchor": anchor,
                },
            )
        )

    return findings


def run_proposition_quality_gates(
    propositions: list[Proposition | dict[str, Any]],
    *,
    newly_normalised: bool = True,
) -> PropositionQualityReport:
    """Evaluate normalised propositions; warnings by default, selective errors."""
    findings: list[PropositionQualityFinding] = []
    for prop in propositions:
        findings.extend(check_proposition(prop, newly_normalised=newly_normalised))
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    return PropositionQualityReport(
        proposition_count=len(propositions),
        error_count=errors,
        warning_count=warnings,
        newly_normalised=newly_normalised,
        findings=findings,
    )


def render_normalisation_quality_markdown(report: PropositionQualityReport) -> str:
    """Human-readable summary for export dirs."""
    lines = [
        "# Proposition normalisation quality",
        "",
        f"**Generated:** {report.generated_at}",
        f"**Propositions checked:** {report.proposition_count}",
        f"**Newly normalised:** {report.newly_normalised}",
        "",
        "## Summary",
        "",
        f"| Severity | Count |",
        f"| --- | ---: |",
        f"| Errors | {report.error_count} |",
        f"| Warnings | {report.warning_count} |",
        "",
    ]
    if not report.findings:
        lines.extend(
            [
                "No quality findings.",
                "",
            ]
        )
        return "\n".join(lines)

    by_check = Counter(f.check_id for f in report.findings)
    lines.extend(
        [
            "## By check",
            "",
            "| Check | Findings |",
            "| --- | ---: |",
        ]
    )
    for check_id, count in sorted(by_check.items()):
        lines.append(f"| `{check_id}` | {count} |")

    lines.extend(["", "## Findings", ""])
    for finding in report.findings[:200]:
        lines.append(
            f"- **{finding.severity}** `{finding.proposition_id}` "
            f"(`{finding.check_id}`): {finding.message}"
        )
    if len(report.findings) > 200:
        lines.append(f"- … and {len(report.findings) - 200} more (see `normalisation_quality.json`)")
    lines.append("")
    return "\n".join(lines)


def normalisation_quality_check_count(payload: dict[str, Any], check_id: str) -> int:
    """Count findings for a check from ``normalisation_quality.json`` or bundle payload."""
    by_check = payload.get("by_check")
    if isinstance(by_check, dict):
        bucket = by_check.get(check_id)
        if isinstance(bucket, dict):
            return int(bucket.get("warnings") or 0) + int(bucket.get("errors") or 0)
    findings = payload.get("findings")
    if isinstance(findings, list):
        return sum(
            1
            for row in findings
            if isinstance(row, dict) and str(row.get("check_id") or "") == check_id
        )
    return 0


def load_normalisation_quality_payload(
    *,
    bundle: dict[str, Any] | None = None,
    export_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """Read quality summary from bundle field or ``normalisation_quality.json`` on disk."""
    if bundle is not None:
        embedded = bundle.get("proposition_normalisation_quality")
        if isinstance(embedded, dict) and "warning_count" in embedded:
            return embedded
    if export_dir is not None:
        path = Path(export_dir) / "normalisation_quality.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
            if isinstance(data, dict) and "warning_count" in data:
                return data
    return None


def proposition_normalisation_quality_model_lines(
    payload: dict[str, Any] | None,
) -> list[str]:
    """Bullet lines for MODEL.md under the Proposition normalisation subsection."""
    if not payload:
        return ["Proposition normalisation quality: not recorded"]
    return [
        "Proposition normalisation quality:",
        f"- Warnings: {int(payload.get('warning_count') or 0)}",
        f"- Errors: {int(payload.get('error_count') or 0)}",
        (
            "- Legacy category conflicts: "
            f"{normalisation_quality_check_count(payload, 'legacy_category_conflict')}"
        ),
        (
            "- Missing territorial application on application-scope rows: "
            f"{normalisation_quality_check_count(payload, 'scope_application_conflict')}"
        ),
        (
            "- Dangerous legacy keys: "
            f"{normalisation_quality_check_count(payload, 'dangerous_legacy_relationship_key')}"
        ),
        f"- Debug leakage: {normalisation_quality_check_count(payload, 'debug_leakage')}",
    ]


def write_normalisation_quality_artifacts(
    output_dir: str | Path,
    report: PropositionQualityReport,
) -> tuple[Path, Path]:
    """Write NORMALISATION_QUALITY.md and normalisation_quality.json."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "normalisation_quality.json"
    md_path = root / "NORMALISATION_QUALITY.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_normalisation_quality_markdown(report), encoding="utf-8")
    return md_path, json_path
