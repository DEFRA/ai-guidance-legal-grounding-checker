"""Cheap verification for regulation paragraph structural fragmentation (no LLM)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import SourceFragment

from .file_input import load_case_file
from .sources import LegislationGovUkAuthorityAdapter, SourceIngestionService

WSI_2021_77_AUTHORITY_SOURCE_ID = "wsi/2021/77"
WSI_2021_77_SOURCE_RECORD_ID = "lex-805b03f284dcf364"
DEFAULT_REGULATION_LOCATOR_PREFIX = "regulation:36"

EXPECTED_REGULATION_36_LOCATORS: tuple[str, ...] = (
    "regulation:36",
    "regulation:36:paragraph:1",
    "regulation:36:paragraph:2",
    "regulation:36:paragraph:3",
    "regulation:36:paragraph:4",
)

VERIFICATION_MD_FILENAME = "REGULATION_PARAGRAPH_FRAGMENTATION_VERIFICATION.md"
VERIFICATION_JSON_FILENAME = "regulation_paragraph_fragmentation_verification.json"

SourceKind = Literal["fixture", "intake", "export"]


@dataclass(frozen=True)
class FragmentLocatorRow:
    fragment_id: str
    locator: str
    parent_fragment_id: str | None
    text_preview: str
    text_length: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "fragment_id": self.fragment_id,
            "locator": self.locator,
            "parent_fragment_id": self.parent_fragment_id,
            "text_preview": self.text_preview,
            "text_length": self.text_length,
        }


@dataclass
class RegulationParagraphFragmentationReport:
    generated_at: str
    source_kind: SourceKind
    authority_source_id: str
    source_record_id: str | None
    locator_prefix: str
    expected_locators: list[str]
    matching_locators: list[str]
    missing_locators: list[str]
    extra_locators: list[str]
    fragment_rows: list[FragmentLocatorRow] = field(default_factory=list)
    passed: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "source_kind": self.source_kind,
            "authority_source_id": self.authority_source_id,
            "source_record_id": self.source_record_id,
            "locator_prefix": self.locator_prefix,
            "expected_locators": self.expected_locators,
            "matching_locators": self.matching_locators,
            "missing_locators": self.missing_locators,
            "extra_locators": self.extra_locators,
            "fragment_rows": [row.to_dict() for row in self.fragment_rows],
            "passed": self.passed,
            "notes": self.notes,
        }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _text_preview(text: str, *, limit: int = 120) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"


def locators_matching_prefix(
    fragments: list[SourceFragment | dict[str, Any]],
    *,
    locator_prefix: str,
    source_record_id: str | None = None,
) -> list[str]:
    prefix = locator_prefix.strip().lower()
    matches: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        if isinstance(fragment, SourceFragment):
            record_id = str(fragment.source_record_id or "").strip()
            locator = str(fragment.locator or "").strip().lower()
            parent_id = fragment.parent_fragment_id
            text = fragment.fragment_text
            fragment_id = str(fragment.id or fragment.fragment_id or "").strip()
        else:
            record_id = str(fragment.get("source_record_id") or "").strip()
            locator = str(fragment.get("locator") or "").strip().lower()
            parent_id = fragment.get("parent_fragment_id")
            text = str(fragment.get("fragment_text") or "")
            fragment_id = str(fragment.get("id") or fragment.get("fragment_id") or "").strip()
        if source_record_id and record_id != source_record_id:
            continue
        if not locator.startswith(prefix):
            continue
        if locator in seen:
            continue
        seen.add(locator)
        matches.append(locator)
        _ = parent_id, text, fragment_id
    return sorted(matches, key=_locator_sort_key)


def _locator_sort_key(locator: str) -> tuple[int, ...]:
    parts: list[int] = []
    for segment in locator.split(":"):
        digits = "".join(ch for ch in segment if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _fragment_rows_for_prefix(
    fragments: list[SourceFragment | dict[str, Any]],
    *,
    locator_prefix: str,
    source_record_id: str | None = None,
) -> list[FragmentLocatorRow]:
    prefix = locator_prefix.strip().lower()
    rows: list[FragmentLocatorRow] = []
    for fragment in fragments:
        if isinstance(fragment, SourceFragment):
            record_id = str(fragment.source_record_id or "").strip()
            locator = str(fragment.locator or "").strip().lower()
            parent_id = fragment.parent_fragment_id
            text = fragment.fragment_text
            fragment_id = str(fragment.id or fragment.fragment_id or "").strip()
        else:
            record_id = str(fragment.get("source_record_id") or "").strip()
            locator = str(fragment.get("locator") or "").strip().lower()
            parent_id = fragment.get("parent_fragment_id")
            text = str(fragment.get("fragment_text") or "")
            fragment_id = str(fragment.get("id") or fragment.get("fragment_id") or "").strip()
        if source_record_id and record_id != source_record_id:
            continue
        if not locator.startswith(prefix):
            continue
        rows.append(
            FragmentLocatorRow(
                fragment_id=fragment_id,
                locator=locator,
                parent_fragment_id=str(parent_id).strip() if parent_id else None,
                text_preview=_text_preview(text),
                text_length=len(str(text or "")),
            )
        )
    rows.sort(key=lambda row: _locator_sort_key(row.locator))
    return rows


def build_regulation_paragraph_fragmentation_report(
    fragments: list[SourceFragment | dict[str, Any]],
    *,
    source_kind: SourceKind,
    authority_source_id: str,
    source_record_id: str | None = None,
    locator_prefix: str = DEFAULT_REGULATION_LOCATOR_PREFIX,
    expected_locators: tuple[str, ...] | list[str] = EXPECTED_REGULATION_36_LOCATORS,
    notes: list[str] | None = None,
) -> RegulationParagraphFragmentationReport:
    expected = [loc.strip().lower() for loc in expected_locators]
    matching = locators_matching_prefix(
        fragments,
        locator_prefix=locator_prefix,
        source_record_id=source_record_id,
    )
    missing = [loc for loc in expected if loc not in matching]
    expected_set = set(expected)
    extra = [loc for loc in matching if loc not in expected_set]
    return RegulationParagraphFragmentationReport(
        generated_at=_now_iso(),
        source_kind=source_kind,
        authority_source_id=authority_source_id,
        source_record_id=source_record_id,
        locator_prefix=locator_prefix.strip().lower(),
        expected_locators=expected,
        matching_locators=matching,
        missing_locators=missing,
        extra_locators=extra,
        fragment_rows=_fragment_rows_for_prefix(
            fragments,
            locator_prefix=locator_prefix,
            source_record_id=source_record_id,
        ),
        passed=not missing,
        notes=list(notes or []),
    )


def _ingest_legislation_source(
    *,
    authority_source_id: str,
    source_record_id: str,
    cache_dir: Path | None,
    fetch_xml: Any | None = None,
) -> list[SourceFragment]:
    adapter = (
        LegislationGovUkAuthorityAdapter(fetch_xml=fetch_xml)
        if fetch_xml
        else LegislationGovUkAuthorityAdapter()
    )
    service = SourceIngestionService(
        cache_dir=cache_dir,
        adapters={"legislation_gov_uk": adapter},
    )
    result = service.ingest_sources(
        [
            {
                "authority": "legislation_gov_uk",
                "authority_source_id": authority_source_id,
                "version_id": "verification",
                "id": source_record_id,
            }
        ]
    )
    return result.fragments


def build_report_from_fixture_xml(
    fixture_path: Path,
    *,
    authority_source_id: str = WSI_2021_77_AUTHORITY_SOURCE_ID,
    source_record_id: str = WSI_2021_77_SOURCE_RECORD_ID,
    locator_prefix: str = DEFAULT_REGULATION_LOCATOR_PREFIX,
    expected_locators: tuple[str, ...] | list[str] = EXPECTED_REGULATION_36_LOCATORS,
) -> RegulationParagraphFragmentationReport:
    xml_payload = fixture_path.read_text(encoding="utf-8")

    def fake_fetch(source_url: str) -> tuple[str, dict[str, object]]:
        return xml_payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml_payload.encode("utf-8")),
            "fetched_url": source_url,
        }

    fragments = _ingest_legislation_source(
        authority_source_id=authority_source_id,
        source_record_id=source_record_id,
        cache_dir=None,
        fetch_xml=fake_fetch,
    )
    return build_regulation_paragraph_fragmentation_report(
        fragments,
        source_kind="fixture",
        authority_source_id=authority_source_id,
        source_record_id=source_record_id,
        locator_prefix=locator_prefix,
        expected_locators=expected_locators,
        notes=[f"fixture={fixture_path.resolve()}"],
    )


def _find_case_source(
    case_data: dict[str, Any],
    *,
    authority_source_id: str | None,
    source_record_id: str | None,
) -> dict[str, Any]:
    sources = case_data.get("sources")
    if not isinstance(sources, list):
        raise ValueError("case file has no sources[] array")
    for raw in sources:
        if not isinstance(raw, dict):
            continue
        if source_record_id and str(raw.get("id") or "").strip() == source_record_id:
            return raw
        if authority_source_id and str(raw.get("authority_source_id") or "").strip().lower() == authority_source_id.lower():
            return raw
    wanted = source_record_id or authority_source_id or "unknown"
    raise ValueError(f"case file has no source matching {wanted!r}")


def build_report_from_case(
    case_path: Path,
    *,
    authority_source_id: str = WSI_2021_77_AUTHORITY_SOURCE_ID,
    source_record_id: str | None = WSI_2021_77_SOURCE_RECORD_ID,
    cache_dir: Path | None = None,
    locator_prefix: str = DEFAULT_REGULATION_LOCATOR_PREFIX,
    expected_locators: tuple[str, ...] | list[str] = EXPECTED_REGULATION_36_LOCATORS,
) -> RegulationParagraphFragmentationReport:
    case_data = load_case_file(case_path)
    raw_source = _find_case_source(
        case_data,
        authority_source_id=authority_source_id,
        source_record_id=source_record_id,
    )
    resolved_source_id = str(raw_source.get("id") or source_record_id or "").strip()
    resolved_authority = str(raw_source.get("authority_source_id") or authority_source_id).strip()
    fragments = _ingest_legislation_source(
        authority_source_id=resolved_authority,
        source_record_id=resolved_source_id,
        cache_dir=cache_dir,
    )
    return build_regulation_paragraph_fragmentation_report(
        fragments,
        source_kind="intake",
        authority_source_id=resolved_authority,
        source_record_id=resolved_source_id,
        locator_prefix=locator_prefix,
        expected_locators=expected_locators,
        notes=[f"case={case_path.resolve()}"],
    )


def build_report_from_export(
    export_dir: Path,
    *,
    source_record_id: str = WSI_2021_77_SOURCE_RECORD_ID,
    locator_prefix: str = DEFAULT_REGULATION_LOCATOR_PREFIX,
    expected_locators: tuple[str, ...] | list[str] = EXPECTED_REGULATION_36_LOCATORS,
) -> RegulationParagraphFragmentationReport:
    fragments_path = export_dir / "source_fragments.json"
    if not fragments_path.is_file():
        raise FileNotFoundError(f"Missing source_fragments.json in {export_dir}")
    payload = json.loads(fragments_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("source_fragments.json must contain a JSON array")
    authority_source_id = WSI_2021_77_AUTHORITY_SOURCE_ID
    sources_path = export_dir / "sources.json"
    if sources_path.is_file():
        sources_payload = json.loads(sources_path.read_text(encoding="utf-8"))
        if isinstance(sources_payload, list):
            for source in sources_payload:
                if isinstance(source, dict) and str(source.get("id") or "").strip() == source_record_id:
                    citation = str(source.get("citation") or "").strip()
                    if citation:
                        authority_source_id = citation
                    break
    return build_regulation_paragraph_fragmentation_report(
        payload,
        source_kind="export",
        authority_source_id=authority_source_id,
        source_record_id=source_record_id,
        locator_prefix=locator_prefix,
        expected_locators=expected_locators,
        notes=[f"export_dir={export_dir.resolve()}"],
    )


def verification_exit_code(report: RegulationParagraphFragmentationReport) -> int:
    return 0 if report.passed else 1


def print_verification_console_summary(report: RegulationParagraphFragmentationReport) -> None:
    status = "PASS" if report.passed else "FAIL"
    print(f"[{status}] regulation paragraph fragmentation ({report.source_kind})")
    print(f"authority_source_id={report.authority_source_id}")
    if report.source_record_id:
        print(f"source_record_id={report.source_record_id}")
    print(f"locator_prefix={report.locator_prefix}")
    print("matching locators:")
    for locator in report.matching_locators:
        print(f"  - {locator}")
    if report.missing_locators:
        print("missing locators:")
        for locator in report.missing_locators:
            print(f"  - {locator}")
    if report.extra_locators:
        print("extra locators under prefix:")
        for locator in report.extra_locators:
            print(f"  - {locator}")
    print("fragment previews:")
    for row in report.fragment_rows:
        parent = f" parent={row.parent_fragment_id}" if row.parent_fragment_id else ""
        print(f"  {row.locator} ({row.text_length} chars){parent}")
        print(f"    {row.text_preview}")


def render_verification_md(report: RegulationParagraphFragmentationReport) -> str:
    lines = [
        "# Regulation paragraph fragmentation verification",
        "",
        f"Generated: {report.generated_at}",
        f"Source kind: `{report.source_kind}`",
        f"Authority: `{report.authority_source_id}`",
    ]
    if report.source_record_id:
        lines.append(f"Source record: `{report.source_record_id}`")
    lines.extend(
        [
            f"Locator prefix: `{report.locator_prefix}`",
            f"Result: **{'PASS' if report.passed else 'FAIL'}**",
            "",
            "## Expected locators",
            "",
        ]
    )
    for locator in report.expected_locators:
        present = locator in report.matching_locators
        lines.append(f"- `{locator}` — {'present' if present else '**missing**'}")
    lines.extend(["", "## Matching locators", ""])
    if report.matching_locators:
        for locator in report.matching_locators:
            lines.append(f"- `{locator}`")
    else:
        lines.append("- _(none)_")
    if report.fragment_rows:
        lines.extend(["", "## Fragment previews", ""])
        for row in report.fragment_rows:
            lines.append(f"### `{row.locator}`")
            lines.append("")
            lines.append(f"- fragment_id: `{row.fragment_id}`")
            if row.parent_fragment_id:
                lines.append(f"- parent_fragment_id: `{row.parent_fragment_id}`")
            lines.append(f"- text_length: {row.text_length}")
            lines.append(f"- preview: {row.text_preview}")
            lines.append("")
    if report.notes:
        lines.extend(["## Notes", ""])
        for note in report.notes:
            lines.append(f"- {note}")
    return "\n".join(lines).rstrip() + "\n"


def write_verification_outputs(
    output_dir: Path,
    report: RegulationParagraphFragmentationReport,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / VERIFICATION_MD_FILENAME
    json_path = output_dir / VERIFICATION_JSON_FILENAME
    md_path.write_text(render_verification_md(report), encoding="utf-8")
    json_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return md_path, json_path
