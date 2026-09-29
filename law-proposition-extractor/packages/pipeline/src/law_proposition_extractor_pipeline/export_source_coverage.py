"""Compare expected export sources against propositions.json source coverage."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOW_PROPOSITION_BASELINE_RATIO = 0.25
LOW_PROPOSITION_MIN_BASELINE = 5

_METADATA_ONLY_RELATIONSHIPS = frozenset({"contextual_source"})
_METADATA_ONLY_BUNDLE_ROLES = frozenset({"contextual", "metadata_only", "metadata-only"})
_METADATA_ONLY_EXTRACTION_ROLES = frozenset({"metadata_only", "metadata-only", "contextual"})


@dataclass
class ExportSourceCoverageSummary:
    expected_source_count: int
    sources_with_propositions: int
    sources_with_zero_propositions: list[str]
    sources_with_low_proposition_count: list[dict[str, Any]]
    sources_with_zero_compliance_relevant: list[str]
    sources_metadata_only: list[str]
    propositions_by_source: dict[str, int]
    compliance_relevant_by_source: dict[str, int]
    source_titles: dict[str, str] = field(default_factory=dict)
    baseline_propositions_by_source: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_source_count": self.expected_source_count,
            "sources_with_propositions": self.sources_with_propositions,
            "sources_with_zero_propositions": self.sources_with_zero_propositions,
            "sources_with_low_proposition_count": self.sources_with_low_proposition_count,
            "sources_with_zero_compliance_relevant": self.sources_with_zero_compliance_relevant,
            "sources_metadata_only": self.sources_metadata_only,
            "propositions_by_source": self.propositions_by_source,
            "compliance_relevant_by_source": self.compliance_relevant_by_source,
            "source_titles": self.source_titles,
            "baseline_propositions_by_source": self.baseline_propositions_by_source,
        }


def _str_field(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _bool_field(row: dict[str, Any], key: str) -> bool | None:
    val = row.get(key)
    if val is True or val is False:
        return val
    return None


def _load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _source_title(source_id: str, sources_by_id: dict[str, dict[str, Any]]) -> str:
    src = sources_by_id.get(source_id)
    if not isinstance(src, dict):
        return source_id
    return _str_field(src, "title") or _str_field(src, "citation") or source_id


def _load_categorisation_by_source(export_dir: Path) -> dict[str, dict[str, Any]]:
    raw = _load_json(export_dir / "source_categorisation_rationales.json")
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in raw:
        if isinstance(row, dict) and row.get("source_record_id"):
            out[str(row["source_record_id"])] = row
    return out


def _load_contextual_source_ids(export_dir: Path, manifest: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    raw_ids = manifest.get("contextual_source_ids")
    if isinstance(raw_ids, list):
        ids.update(str(x) for x in raw_ids if x)
    bundle_path = export_dir / "source_bundle_intake.json"
    bundle = _load_json(bundle_path)
    if isinstance(bundle, dict):
        contextual = bundle.get("contextual_sources")
        if isinstance(contextual, list):
            for row in contextual:
                if isinstance(row, dict) and row.get("id"):
                    ids.add(str(row["id"]))
                elif row:
                    ids.add(str(row))
    return ids


def is_metadata_only_source(
    source_id: str,
    *,
    source_row: dict[str, Any] | None,
    categorisation: dict[str, Any] | None,
    contextual_source_ids: set[str] | None = None,
) -> bool:
    """True when a source is known to be metadata/contextual only (no compliance extraction expected)."""
    if contextual_source_ids and source_id in contextual_source_ids:
        return True
    if isinstance(source_row, dict):
        if source_row.get("metadata_only") is True:
            return True
        extraction_role = _str_field(source_row, "extraction_role").lower()
        if extraction_role in _METADATA_ONLY_EXTRACTION_ROLES:
            return True
        metadata = source_row.get("metadata")
        if isinstance(metadata, dict):
            if metadata.get("metadata_only") is True:
                return True
            law_discovery_meta = metadata.get("ada_source_bundle")
            if isinstance(law_discovery_meta, dict):
                role = _str_field(law_discovery_meta, "bundle_role").lower()
                if role in _METADATA_ONLY_BUNDLE_ROLES:
                    return True
    if isinstance(categorisation, dict):
        rel = _str_field(categorisation, "relationship_to_analysis").lower()
        if rel in _METADATA_ONLY_RELATIONSHIPS:
            return True
    return False


def load_expected_export_sources(
    export_dir: str | Path,
    *,
    sources_by_id: dict[str, dict[str, Any]] | None = None,
    bundle: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Expected sources from export bundle (sources.json or embedded source_records)."""
    if sources_by_id:
        return dict(sources_by_id)
    root = Path(export_dir)
    if bundle is not None:
        rows = bundle.get("source_records") or bundle.get("sources") or []
        if isinstance(rows, list) and rows:
            return {
                str(row["id"]): row
                for row in rows
                if isinstance(row, dict) and row.get("id")
            }
    raw = _load_json(root / "sources.json")
    if isinstance(raw, list):
        return {
            str(row["id"]): row
            for row in raw
            if isinstance(row, dict) and row.get("id")
        }
    return {}


def load_source_proposition_baseline(
    export_dir: str | Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Optional per-source proposition count baseline for low-coverage detection."""
    root = Path(export_dir)
    manifest = manifest if isinstance(manifest, dict) else (_load_json(root / "manifest.json") or {})
    raw = manifest.get("source_proposition_baseline")
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items() if int(v or 0) > 0}
    file_raw = _load_json(root / "source_proposition_baseline.json")
    if isinstance(file_raw, dict):
        return {str(k): int(v) for k, v in file_raw.items() if int(v or 0) > 0}
    return {}


def assess_export_source_coverage(
    export_dir: str | Path,
    propositions: list[dict[str, Any]],
    *,
    sources_by_id: dict[str, dict[str, Any]] | None = None,
    bundle: dict[str, Any] | None = None,
    baseline_by_source: dict[str, int] | None = None,
) -> ExportSourceCoverageSummary:
    """Compare manifest/bundle sources against proposition rows by source_record_id."""
    root = Path(export_dir)
    manifest = _load_json(root / "manifest.json")
    manifest = manifest if isinstance(manifest, dict) else {}
    expected = load_expected_export_sources(root, sources_by_id=sources_by_id, bundle=bundle)
    categorisation_by_source = _load_categorisation_by_source(root)
    contextual_ids = _load_contextual_source_ids(root, manifest)

    prop_counts: dict[str, int] = {sid: 0 for sid in expected}
    compliance_counts: dict[str, int] = {sid: 0 for sid in expected}
    for row in propositions:
        if not isinstance(row, dict):
            continue
        sid = _str_field(row, "source_record_id")
        if sid not in prop_counts:
            continue
        prop_counts[sid] += 1
        if _bool_field(row, "is_compliance_relevant") is True:
            compliance_counts[sid] += 1

    metadata_only: list[str] = []
    for sid, source_row in expected.items():
        if is_metadata_only_source(
            sid,
            source_row=source_row,
            categorisation=categorisation_by_source.get(sid),
            contextual_source_ids=contextual_ids,
        ):
            metadata_only.append(sid)

    zero_props = sorted(
        sid for sid, count in prop_counts.items() if count == 0 and sid not in metadata_only
    )
    zero_compliance = sorted(
        sid
        for sid, count in compliance_counts.items()
        if prop_counts.get(sid, 0) > 0 and count == 0 and sid not in metadata_only
    )

    baseline = dict(baseline_by_source or load_source_proposition_baseline(root, manifest))
    low_counts: list[dict[str, Any]] = []
    for sid, baseline_count in sorted(baseline.items()):
        if sid not in expected or sid in metadata_only:
            continue
        if baseline_count < LOW_PROPOSITION_MIN_BASELINE:
            continue
        current = prop_counts.get(sid, 0)
        if current == 0:
            continue
        ratio = current / baseline_count
        if ratio < LOW_PROPOSITION_BASELINE_RATIO:
            low_counts.append(
                {
                    "source_record_id": sid,
                    "source_title": _source_title(sid, expected),
                    "proposition_count": current,
                    "baseline_proposition_count": baseline_count,
                    "ratio": round(ratio, 4),
                }
            )

    titles = {sid: _source_title(sid, expected) for sid in expected}
    props_by_title = {titles[sid]: prop_counts[sid] for sid in sorted(expected)}
    compliance_by_title = {titles[sid]: compliance_counts[sid] for sid in sorted(expected)}

    return ExportSourceCoverageSummary(
        expected_source_count=len(expected),
        sources_with_propositions=sum(1 for sid in expected if prop_counts.get(sid, 0) > 0),
        sources_with_zero_propositions=zero_props,
        sources_with_low_proposition_count=low_counts,
        sources_with_zero_compliance_relevant=zero_compliance,
        sources_metadata_only=sorted(metadata_only),
        propositions_by_source=props_by_title,
        compliance_relevant_by_source=compliance_by_title,
        source_titles=titles,
        baseline_propositions_by_source=baseline,
    )
