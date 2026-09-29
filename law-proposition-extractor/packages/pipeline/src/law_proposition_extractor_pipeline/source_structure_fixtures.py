"""Offline structural-source fixture matrix (Law Proposition Extractor-only, no network)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def judit_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "tests" / "fixtures").is_dir() and (
            candidate / "packages" / "pipeline"
        ).is_dir():
            return candidate
        if (candidate / "law-proposition-extractor" / "tests" / "fixtures").is_dir():
            return candidate / "law-proposition-extractor"
    raise RuntimeError("Could not locate Law Proposition Extractor repository root.")


FIXTURE_DIR_RELATIVE = Path("tests/fixtures/structural_source")
MANIFEST_FILENAME = "manifest.json"
REPORT_RELATIVE = Path("docs/explainability/structural-source-fixtures.md")


@dataclass(frozen=True)
class StructuralSourceFixture:
    fixture_id: str
    relative_path: str
    jurisdiction: str
    instrument_style: str
    clml_root: str
    authority_source_id: str
    patterns: tuple[str, ...]
    heading_kinds: tuple[str, ...]
    expects_unassigned_cross_heading: bool
    source_kind: str
    notes: str

    @property
    def path(self) -> Path:
        return (judit_root() / FIXTURE_DIR_RELATIVE / self.relative_path).resolve()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "relative_path": self.relative_path,
            "jurisdiction": self.jurisdiction,
            "instrument_style": self.instrument_style,
            "clml_root": self.clml_root,
            "authority_source_id": self.authority_source_id,
            "patterns": list(self.patterns),
            "heading_kinds": list(self.heading_kinds),
            "expects_unassigned_cross_heading": self.expects_unassigned_cross_heading,
            "source_kind": self.source_kind,
            "notes": self.notes,
        }


def manifest_path(*, root: Path | None = None) -> Path:
    base = root or judit_root()
    return base / FIXTURE_DIR_RELATIVE / MANIFEST_FILENAME


def load_manifest(*, root: Path | None = None) -> dict[str, Any]:
    path = manifest_path(root=root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Structural-source manifest must be an object: {path}")
    return payload


def load_structural_source_fixtures(*, root: Path | None = None) -> list[StructuralSourceFixture]:
    payload = load_manifest(root=root)
    fixtures_raw = payload.get("fixtures")
    if not isinstance(fixtures_raw, list):
        raise ValueError("Structural-source manifest missing fixtures list.")
    out: list[StructuralSourceFixture] = []
    for row in fixtures_raw:
        if not isinstance(row, dict):
            continue
        out.append(
            StructuralSourceFixture(
                fixture_id=str(row["fixture_id"]),
                relative_path=str(row["relative_path"]),
                jurisdiction=str(row.get("jurisdiction") or ""),
                instrument_style=str(row.get("instrument_style") or ""),
                clml_root=str(row.get("clml_root") or ""),
                authority_source_id=str(row.get("authority_source_id") or ""),
                patterns=tuple(str(p) for p in (row.get("patterns") or [])),
                heading_kinds=tuple(str(k) for k in (row.get("heading_kinds") or [])),
                expects_unassigned_cross_heading=bool(
                    row.get("expects_unassigned_cross_heading")
                ),
                source_kind=str(row.get("source_kind") or "fixture"),
                notes=str(row.get("notes") or ""),
            )
        )
    return out


def known_unrepresented_patterns(*, root: Path | None = None) -> list[str]:
    payload = load_manifest(root=root)
    raw = payload.get("known_unrepresented_patterns") or []
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def fixture_by_id(
    fixture_id: str, *, root: Path | None = None
) -> StructuralSourceFixture:
    for fixture in load_structural_source_fixtures(root=root):
        if fixture.fixture_id == fixture_id:
            return fixture
    raise KeyError(f"Unknown structural-source fixture_id: {fixture_id}")
