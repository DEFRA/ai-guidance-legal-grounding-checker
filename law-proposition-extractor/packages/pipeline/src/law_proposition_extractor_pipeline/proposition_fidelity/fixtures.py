"""Manifest + case loading for the proposition-fidelity benchmark."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

from .action_fidelity import ActionExpectation, load_action_expectation

FIXTURE_DIR_RELATIVE = Path("tests/fixtures/proposition_fidelity")
MANIFEST_FILENAME = "manifest.json"
BASELINE_FILENAME = "baseline.json"
REPORT_RELATIVE = Path("docs/explainability/proposition-fidelity-benchmark.md")
BENCHMARK_VERSION = "1"

ProvenanceKind = Literal[
    "reduced_real",
    "adapted_repository_fixture",
    "synthetic_structural_edge",
]


@dataclass(frozen=True)
class ExpectedProposition:
    role: str
    source_locator: str
    short_legal_description: str
    legal_effect_type: str
    required_actor: str | None = None
    required_action: str | None = None
    action_expectation: ActionExpectation | None = None
    object: str | None = None
    conditions: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    thresholds: tuple[str, ...] = ()
    cross_references: tuple[str, ...] = ()
    structured_list_path: str | None = None
    evidence_markers: tuple[str, ...] = ()
    context_dependencies: tuple[str, ...] = ()
    expected_completeness: str | None = None
    may_share_source_fragment_with: tuple[str, ...] = ()
    completeness_severity: Literal["fail", "warning", "informational"] = "warning"
    article_49a_role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "role": self.role,
            "source_locator": self.source_locator,
            "short_legal_description": self.short_legal_description,
            "legal_effect_type": self.legal_effect_type,
        }
        optional = {
            "required_actor": self.required_actor,
            "required_action": self.required_action,
            "action_expectation": (
                self.action_expectation.to_dict() if self.action_expectation else None
            ),
            "object": self.object,
            "conditions": list(self.conditions) or None,
            "exceptions": list(self.exceptions) or None,
            "thresholds": list(self.thresholds) or None,
            "cross_references": list(self.cross_references) or None,
            "structured_list_path": self.structured_list_path,
            "evidence_markers": list(self.evidence_markers) or None,
            "context_dependencies": list(self.context_dependencies) or None,
            "expected_completeness": self.expected_completeness,
            "may_share_source_fragment_with": list(self.may_share_source_fragment_with)
            or None,
            "completeness_severity": self.completeness_severity,
            "article_49a_role": self.article_49a_role,
        }
        for key, value in optional.items():
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True)
class ResponseFixtureMeta:
    relative_path: str
    prompt_version: str
    model_alias: str
    reflects_prompt_v3: bool
    notes: str = ""


@dataclass(frozen=True)
class PropositionFidelityCase:
    case_id: str
    source_fixture_relative: str
    jurisdiction: str
    instrument_style: str
    source_locator: str
    structural_pattern: str
    heading_present: bool
    expected_proposition_count: int
    expected_legal_effect_types: tuple[str, ...]
    expected_relationship_features: tuple[str, ...]
    provenance_kind: ProvenanceKind
    provenance_note: str
    runner: Literal["article_49a_pipeline", "dry_fragment"]
    gold: tuple[ExpectedProposition, ...]
    response: ResponseFixtureMeta | None = None
    fragment_text_override: str | None = None
    heading_text: str | None = None
    sibling_heading_forbidden: tuple[str, ...] = ()
    accepted_limitations: tuple[str, ...] = ()
    notes: str = ""
    case_dir_relative: str = ""

    @property
    def source_path(self) -> Path:
        return (judit_root() / self.source_fixture_relative).resolve()

    @property
    def response_path(self) -> Path | None:
        if self.response is None:
            return None
        return (judit_root() / FIXTURE_DIR_RELATIVE / self.response.relative_path).resolve()

    def to_manifest_entry(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "source_fixture": self.source_fixture_relative,
            "jurisdiction": self.jurisdiction,
            "instrument_style": self.instrument_style,
            "source_locator": self.source_locator,
            "structural_pattern": self.structural_pattern,
            "heading_present": self.heading_present,
            "expected_proposition_count": self.expected_proposition_count,
            "expected_legal_effect_types": list(self.expected_legal_effect_types),
            "expected_relationship_features": list(self.expected_relationship_features),
            "provenance_kind": self.provenance_kind,
            "provenance_note": self.provenance_note,
            "runner": self.runner,
            "case_dir": self.case_dir_relative,
            "accepted_limitations": list(self.accepted_limitations),
            "notes": self.notes,
        }


def fixture_dir(*, root: Path | None = None) -> Path:
    return (root or judit_root()) / FIXTURE_DIR_RELATIVE


def manifest_path(*, root: Path | None = None) -> Path:
    return fixture_dir(root=root) / MANIFEST_FILENAME


def baseline_path(*, root: Path | None = None) -> Path:
    return fixture_dir(root=root) / BASELINE_FILENAME


def report_path(*, root: Path | None = None) -> Path:
    return (root or judit_root()) / REPORT_RELATIVE


def _tuple_str(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, str):
        return (raw,)
    return tuple(str(x) for x in raw if str(x).strip())


def _load_expected(row: dict[str, Any]) -> ExpectedProposition:
    return ExpectedProposition(
        role=str(row["role"]),
        source_locator=str(row["source_locator"]),
        short_legal_description=str(row["short_legal_description"]),
        legal_effect_type=str(row["legal_effect_type"]),
        required_actor=str(row["required_actor"]) if row.get("required_actor") else None,
        required_action=str(row["required_action"]) if row.get("required_action") else None,
        action_expectation=load_action_expectation(row.get("action_expectation")),
        object=str(row["object"]) if row.get("object") else None,
        conditions=_tuple_str(row.get("conditions")),
        exceptions=_tuple_str(row.get("exceptions")),
        thresholds=_tuple_str(row.get("thresholds")),
        cross_references=_tuple_str(row.get("cross_references")),
        structured_list_path=(
            str(row["structured_list_path"]) if row.get("structured_list_path") else None
        ),
        evidence_markers=_tuple_str(row.get("evidence_markers")),
        context_dependencies=_tuple_str(row.get("context_dependencies")),
        expected_completeness=(
            str(row["expected_completeness"]) if row.get("expected_completeness") else None
        ),
        may_share_source_fragment_with=_tuple_str(row.get("may_share_source_fragment_with")),
        completeness_severity=row.get("completeness_severity") or "warning",  # type: ignore[arg-type]
        article_49a_role=str(row["article_49a_role"]) if row.get("article_49a_role") else None,
    )


def load_manifest(*, root: Path | None = None) -> dict[str, Any]:
    path = manifest_path(root=root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Proposition-fidelity manifest must be an object: {path}")
    return payload


def load_gold_contract(case_dir: Path) -> tuple[ExpectedProposition, ...]:
    gold_path = case_dir / "gold.json"
    payload = json.loads(gold_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Gold contract must be an object: {gold_path}")
    rows = payload.get("expected_propositions")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Gold contract missing expected_propositions: {gold_path}")
    return tuple(_load_expected(row) for row in rows if isinstance(row, dict))


def load_proposition_fidelity_cases(*, root: Path | None = None) -> list[PropositionFidelityCase]:
    base = root or judit_root()
    payload = load_manifest(root=base)
    cases_raw = payload.get("cases")
    if not isinstance(cases_raw, list):
        raise ValueError("Proposition-fidelity manifest missing cases list.")
    out: list[PropositionFidelityCase] = []
    for row in cases_raw:
        if not isinstance(row, dict):
            continue
        case_dir_rel = str(row["case_dir"])
        case_dir = base / FIXTURE_DIR_RELATIVE / case_dir_rel
        gold = load_gold_contract(case_dir)
        response_meta = None
        response_raw = row.get("response")
        if isinstance(response_raw, dict):
            response_meta = ResponseFixtureMeta(
                relative_path=str(response_raw["relative_path"]),
                prompt_version=str(response_raw.get("prompt_version") or "v2"),
                model_alias=str(response_raw.get("model_alias") or "fixture"),
                reflects_prompt_v3=bool(response_raw.get("reflects_prompt_v3")),
                notes=str(response_raw.get("notes") or ""),
            )
        fragment_override = None
        override_path = case_dir / "fragment_text.txt"
        if override_path.is_file():
            fragment_override = override_path.read_text(encoding="utf-8")
        out.append(
            PropositionFidelityCase(
                case_id=str(row["case_id"]),
                source_fixture_relative=str(row["source_fixture"]),
                jurisdiction=str(row.get("jurisdiction") or ""),
                instrument_style=str(row.get("instrument_style") or ""),
                source_locator=str(row["source_locator"]),
                structural_pattern=str(row.get("structural_pattern") or ""),
                heading_present=bool(row.get("heading_present")),
                expected_proposition_count=int(row["expected_proposition_count"]),
                expected_legal_effect_types=_tuple_str(row.get("expected_legal_effect_types")),
                expected_relationship_features=_tuple_str(
                    row.get("expected_relationship_features")
                ),
                provenance_kind=row.get("provenance_kind") or "adapted_repository_fixture",  # type: ignore[arg-type]
                provenance_note=str(row.get("provenance_note") or ""),
                runner=row.get("runner") or "dry_fragment",  # type: ignore[arg-type]
                gold=gold,
                response=response_meta,
                fragment_text_override=fragment_override,
                heading_text=str(row["heading_text"]) if row.get("heading_text") else None,
                sibling_heading_forbidden=_tuple_str(row.get("sibling_heading_forbidden")),
                accepted_limitations=_tuple_str(row.get("accepted_limitations")),
                notes=str(row.get("notes") or ""),
                case_dir_relative=case_dir_rel,
            )
        )
    return out


def validate_manifest_inventory(*, root: Path | None = None) -> list[str]:
    """Return human-readable validation errors (empty if valid)."""
    base = root or judit_root()
    errors: list[str] = []
    try:
        cases = load_proposition_fidelity_cases(root=base)
    except Exception as exc:  # noqa: BLE001 — inventory surface
        return [f"manifest load failed: {exc}"]
    ids = [c.case_id for c in cases]
    if len(ids) != len(set(ids)):
        errors.append("duplicate case_id values in manifest")
    for case in cases:
        if not case.source_path.is_file():
            errors.append(f"{case.case_id}: missing source fixture {case.source_fixture_relative}")
        if case.runner == "dry_fragment":
            if case.response is None:
                errors.append(f"{case.case_id}: dry_fragment runner requires response fixture")
            elif case.response_path is None or not case.response_path.is_file():
                errors.append(f"{case.case_id}: missing response fixture")
        roles = [g.role for g in case.gold]
        if len(roles) != len(set(roles)):
            errors.append(f"{case.case_id}: duplicate semantic roles in gold contract")
        if len(case.gold) != case.expected_proposition_count:
            errors.append(
                f"{case.case_id}: expected_proposition_count "
                f"{case.expected_proposition_count} != gold size {len(case.gold)}"
            )
    return errors


@dataclass
class ManifestNotes:
    known_gaps: list[str] = field(default_factory=list)
    inventory_notes: dict[str, Any] = field(default_factory=dict)


def load_manifest_notes(*, root: Path | None = None) -> ManifestNotes:
    payload = load_manifest(root=root)
    gaps = payload.get("known_corpus_gaps") or []
    notes = payload.get("inventory_notes") or {}
    return ManifestNotes(
        known_gaps=[str(x) for x in gaps] if isinstance(gaps, list) else [],
        inventory_notes=notes if isinstance(notes, dict) else {},
    )
