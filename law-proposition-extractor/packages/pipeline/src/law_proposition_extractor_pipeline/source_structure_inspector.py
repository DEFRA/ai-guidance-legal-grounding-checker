"""Deterministic structural-source inspector (domain objects, not raw XML dumps)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree

from .source_structure_audit import (
    StructuralSourceAudit,
    assert_hierarchy_sound,
    assert_no_heading_leak,
    audit_structural_fragments,
    structural_rows_to_fragments,
    text_preview,
)
from .source_structure_fixtures import (
    REPORT_RELATIVE,
    StructuralSourceFixture,
    judit_root,
    known_unrepresented_patterns,
    load_structural_source_fixtures,
)
from .sources.adapters import _build_legislation_structural_fragments
from .structural_headings import (
    format_heading_contexts_for_prompt,
    format_structural_heading_display,
    resolve_structural_heading_contexts,
)

OutputFormat = Literal["json", "markdown", "tree"]

_ABS_PATH_RE = re.compile(r"(/Users/|/home/|/private/var/|C:\\\\|file://)")


@dataclass(frozen=True)
class StructuralInspectResult:
    fixture_id: str | None
    authority_source_id: str | None
    relative_source: str | None
    audit: StructuralSourceAudit
    tree_markdown: str
    prompt_context_samples: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "authority_source_id": self.authority_source_id,
            "relative_source": self.relative_source,
            "audit": self.audit.to_dict(),
            "tree_markdown": self.tree_markdown,
            "prompt_context_samples": list(self.prompt_context_samples),
        }


def _instrument_title_from_root(root: ElementTree.Element) -> str | None:
    # Prefer a direct child Title on the Legislation root (instrument title).
    for child in list(root):
        tag = child.tag.split("}", maxsplit=1)[-1]
        if tag == "Title":
            text = " ".join("".join(child.itertext()).split()).strip()
            if text:
                return text
    for node in root.iter():
        tag = node.tag.split("}", maxsplit=1)[-1]
        if tag in {"DocumentTitle", "LongTitle"}:
            text = " ".join("".join(node.itertext()).split()).strip()
            if text and len(text) < 300:
                return text
    return None


def parse_structural_source_xml(
    xml_text: str,
    *,
    source_url: str = "https://www.legislation.gov.uk/offline/fixture/data.xml",
    source_record_id: str = "src-structural-audit",
    source_snapshot_id: str = "snap-structural-audit",
) -> tuple[list[Any], StructuralSourceAudit, str | None]:
    """Parse CLML XML into fragments + audit. Never returns absolute paths."""
    root = ElementTree.fromstring(xml_text)
    rows, _links = _build_legislation_structural_fragments(root=root, source_url=source_url)
    fragments = structural_rows_to_fragments(
        rows,
        source_record_id=source_record_id,
        source_snapshot_id=source_snapshot_id,
    )
    title = _instrument_title_from_root(root)
    audit = audit_structural_fragments(
        fragments,
        source_record_id=source_record_id,
        source_snapshot_id=source_snapshot_id,
        instrument_title=title,
        manifestation=None,
    )
    return fragments, audit, title


def render_structure_tree(audit: StructuralSourceAudit) -> str:
    """Render outermost→leaf tree with number/heading labels."""
    by_id = {row.fragment_id: row for row in audit.fragment_rows}
    children: dict[str | None, list[str]] = {}
    for row in audit.fragment_rows:
        children.setdefault(row.parent_fragment_id, []).append(row.fragment_id)

    def label(row_id: str) -> str:
        row = by_id[row_id]
        display = format_structural_heading_display(
            number_label=row.number_label, heading_text=row.direct_heading_text
        )
        if display:
            return display
        if row.number_label:
            return row.number_label
        return row.locator

    lines: list[str] = []

    def walk(row_id: str, prefix: str, is_last: bool) -> None:
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{label(row_id)}")
        kids = children.get(row_id) or []
        # Preserve deterministic order from fragment_rows order_index.
        kids_sorted = sorted(
            kids, key=lambda kid: audit.fragment_rows.index(by_id[kid])
        )
        child_prefix = prefix + ("    " if is_last else "│   ")
        for index, kid in enumerate(kids_sorted):
            walk(kid, child_prefix, index == len(kids_sorted) - 1)

    roots = children.get(None) or []
    roots_sorted = sorted(roots, key=lambda kid: audit.fragment_rows.index(by_id[kid]))
    if not roots_sorted and audit.fragment_rows:
        # Orphan-only fallback.
        for row in audit.fragment_rows:
            lines.append(label(row.fragment_id))
        return "\n".join(lines)

    for index, root_id in enumerate(roots_sorted):
        row = by_id[root_id]
        lines.append(label(root_id))
        kids = children.get(root_id) or []
        kids_sorted = sorted(
            kids, key=lambda kid: audit.fragment_rows.index(by_id[kid])
        )
        for kid_index, kid in enumerate(kids_sorted):
            walk(kid, "", kid_index == len(kids_sorted) - 1)
        if index != len(roots_sorted) - 1:
            lines.append("")
    return "\n".join(lines)


def _prompt_context_samples(
    fragments: list[Any], *, limit: int = 5
) -> list[dict[str, Any]]:
    by_id = {f.id: f for f in fragments}
    samples: list[dict[str, Any]] = []
    for frag in fragments:
        contexts = resolve_structural_heading_contexts(frag, by_id)
        if not contexts:
            continue
        samples.append(
            {
                "locator": frag.locator,
                "heading_path": [
                    format_structural_heading_display(
                        number_label=c.number_label, heading_text=c.heading_text
                    )
                    for c in contexts
                ],
                "prompt_block": format_heading_contexts_for_prompt(contexts),
                "operative_preview": text_preview(frag.fragment_text, limit=80),
            }
        )
        if len(samples) >= limit:
            break
    return samples


def inspect_structural_xml(
    xml_text: str,
    *,
    fixture_id: str | None = None,
    authority_source_id: str | None = None,
    relative_source: str | None = None,
    source_url: str = "https://www.legislation.gov.uk/offline/fixture/data.xml",
) -> StructuralInspectResult:
    record_slug = (fixture_id or authority_source_id or "offline").replace("/", "-")
    fragments, audit, _title = parse_structural_source_xml(
        xml_text,
        source_url=source_url,
        source_record_id=f"src-{record_slug}",
        source_snapshot_id=f"snap-{record_slug}",
    )
    return StructuralInspectResult(
        fixture_id=fixture_id,
        authority_source_id=authority_source_id,
        relative_source=relative_source,
        audit=audit,
        tree_markdown=render_structure_tree(audit),
        prompt_context_samples=_prompt_context_samples(fragments),
    )


def inspect_structural_fixture(
    fixture: StructuralSourceFixture,
) -> StructuralInspectResult:
    xml_text = fixture.path.read_text(encoding="utf-8")
    # Synthetic legislation.gov.uk URL — never an absolute filesystem path.
    source_url = (
        f"https://www.legislation.gov.uk/{fixture.authority_source_id.strip('/')}/data.xml"
    )
    return inspect_structural_xml(
        xml_text,
        fixture_id=fixture.fixture_id,
        authority_source_id=fixture.authority_source_id,
        relative_source=f"tests/fixtures/structural_source/{fixture.relative_path}",
        source_url=source_url,
    )


def render_inspect_markdown(result: StructuralInspectResult) -> str:
    audit = result.audit
    lines = [
        f"# Structural source inspection: {result.fixture_id or 'adhoc'}",
        "",
        f"- Authority source: `{result.authority_source_id or 'n/a'}`",
        f"- Relative source: `{result.relative_source or 'n/a'}`",
        f"- Instrument title: {audit.instrument_title or 'n/a'}",
        f"- Fragment count: {audit.fragment_count}",
        f"- Heading count: {audit.heading_count}",
        f"- Heading kinds: {audit.heading_counts_by_kind or '{}'}",
        f"- Audit passed: {audit.passed}",
        "",
        "## Structure tree",
        "",
        "```text",
        result.tree_markdown,
        "```",
        "",
        "## Unassigned headings",
        "",
    ]
    if audit.unassigned_headings:
        for item in audit.unassigned_headings:
            lines.append(f"- `{item.locator}`: `{item.diagnostic}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Diagnostics", ""])
    if audit.diagnostics:
        for diag in audit.diagnostics:
            lines.append(f"- `{diag.code}` @ `{diag.locator}`: {diag.message}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Caution",
            "",
            "Legislative headings are source-provided structural context. They are "
            "not treated as standalone operative rules.",
            "",
        ]
    )
    return "\n".join(lines)


def assert_no_path_leaks(text: str, *, label: str = "output") -> None:
    if _ABS_PATH_RE.search(text):
        raise AssertionError(f"{label} contains an absolute path or file:// link")
    if "<Legislation" in text and "xmlns=" in text and len(text) > 5000:
        # Full CLML dump heuristic.
        raise AssertionError(f"{label} appears to contain raw complete XML")


def check_structural_fixture(fixture: StructuralSourceFixture) -> StructuralInspectResult:
    result = inspect_structural_fixture(fixture)
    assert_no_heading_leak(result.audit)
    assert_hierarchy_sound(result.audit)
    if fixture.expects_unassigned_cross_heading:
        if not result.audit.unassigned_headings:
            raise AssertionError(
                f"Source-fidelity failure: expected unassigned cross-heading "
                f"diagnostic for fixture {fixture.fixture_id}"
            )
        for row in result.audit.fragment_rows:
            if row.direct_heading_text and "cross-heading" in (
                row.direct_heading_text or ""
            ).lower():
                raise AssertionError(
                    "Source-fidelity failure: multi-provision cross-heading was "
                    f"assigned to {row.locator}"
                )
    else:
        # No arbitrary assignment of multi-provision diagnostics expected as errors.
        pass
    payload = json.dumps(result.to_dict(), sort_keys=True, indent=2)
    assert_no_path_leaks(payload, label=f"fixture:{fixture.fixture_id}")
    assert_no_path_leaks(result.tree_markdown, label=f"tree:{fixture.fixture_id}")
    return result


def check_all_structural_fixtures(
    *, root: Path | None = None
) -> list[StructuralInspectResult]:
    results: list[StructuralInspectResult] = []
    for fixture in load_structural_source_fixtures(root=root):
        if not fixture.path.is_file():
            raise FileNotFoundError(
                f"Missing structural-source fixture file for {fixture.fixture_id}: "
                f"{fixture.relative_path}"
            )
        results.append(check_structural_fixture(fixture))
    return results


def render_fixture_suite_report(*, root: Path | None = None) -> str:
    """Human-readable regression report for the structural-source fixture matrix."""
    base = root or judit_root()
    fixtures = load_structural_source_fixtures(root=base)
    results = [inspect_structural_fixture(f) for f in fixtures]
    by_id = {r.fixture_id: r for r in results}

    lines = [
        "<!-- Generated by law_proposition_extractor_pipeline.source_structure_inspector; do not edit by hand. -->",
        "",
        "# Structural-source fixture contract",
        "",
        "Law Proposition Extractor keeps legislative headings as **structural context**. It does not",
        "silently convert them into legal rules or evidence quotes.",
        "",
        "This report summarises the offline multi-instrument fixture matrix used to",
        "regress hierarchy, heading ownership, inheritance, and operative-text",
        "boundaries. No live legislation is fetched.",
        "",
        "Legislative headings are source-provided structural context. They are not",
        "treated as standalone operative rules.",
        "",
        "## Fixture matrix",
        "",
        "| Fixture | Style | Patterns | Headings | Unassigned | Audit |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for fixture in fixtures:
        result = by_id[fixture.fixture_id]
        patterns = ", ".join(fixture.patterns[:4])
        if len(fixture.patterns) > 4:
            patterns += ", …"
        heads = ", ".join(
            f"{k}×{v}" for k, v in result.audit.heading_counts_by_kind.items()
        ) or "—"
        unassigned = str(len(result.audit.unassigned_headings))
        lines.append(
            f"| `{fixture.fixture_id}` | {fixture.instrument_style} | {patterns} | "
            f"{heads} | {unassigned} | {'pass' if result.audit.passed else 'FAIL'} |"
        )

    lines.extend(["", "## Per-fixture hierarchy summaries", ""])
    for fixture in fixtures:
        result = by_id[fixture.fixture_id]
        lines.extend(
            [
                f"### `{fixture.fixture_id}`",
                "",
                f"- Jurisdiction: {fixture.jurisdiction}",
                f"- Instrument style: {fixture.instrument_style}",
                f"- CLML root: `{fixture.clml_root}`",
                f"- Relative path: `tests/fixtures/structural_source/{fixture.relative_path}`",
                f"- Patterns: {', '.join(fixture.patterns)}",
                f"- Notes: {fixture.notes}",
                "",
                "```text",
                result.tree_markdown,
                "```",
                "",
            ]
        )
        if result.audit.unassigned_headings:
            lines.append("Expected / observed unassigned headings:")
            for item in result.audit.unassigned_headings:
                lines.append(f"- `{item.locator}` — `{item.diagnostic}`")
            lines.append("")
        if result.prompt_context_samples:
            sample = result.prompt_context_samples[0]
            lines.extend(
                [
                    "Sample extraction heading path "
                    f"(`{sample['locator']}`):",
                    "",
                    "```text",
                    sample["prompt_block"] or "(none)",
                    "```",
                    "",
                ]
            )

    lines.extend(
        [
            "## Prompt-context coverage",
            "",
            "- EU Article with inherited Title + Article heading "
            "(`article_49a_eur_2009_1224`, `single_provision_headed_group`)",
            "- UK regulation with Part + regulation heading (`uk_regulation_headed`)",
            "- Provision without heading (`wsi_regulation_36_paragraphs`, "
            "`regulation:13` in `uk_regulation_headed`)",
            "- Multi-provision unassigned heading (`multi_provision_cross_heading`)",
            "",
            "## Proposition-boundary coverage",
            "",
            "- Headings are absent from operative `fragment_text` (audit field "
            "`operative_text_heading_leak`).",
            "- Prompt v3 places headings in a labelled non-operative block.",
            "- Evidence validation requires verbatim operative-source spans; "
            "heading-only quotes fail.",
            "- Article 49a acceptance remains six operative propositions "
            "(no seventh heading proposition).",
            "",
            "## Known structural patterns not yet represented offline",
            "",
        ]
    )
    for item in known_unrepresented_patterns(root=base):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            "just inspect-structural-fixtures",
            "just check-structural-fixtures",
            "```",
            "",
            "## Materiality note",
            "",
            "This contract does **not** classify heading materiality, completeness,",
            "or scope-bearing roles. Heading context may improve retrieval and",
            "reviewer orientation later, but a heading-only match is not substantive",
            "evidence that guidance matches a legal proposition.",
            "",
            "## Related: proposition fidelity",
            "",
            "Structural-source fidelity asks whether Law Proposition Extractor parsed hierarchy and",
            "heading context correctly. Operative-claim fidelity is a separate",
            "contract — see [proposition-fidelity-benchmark.md]"
            "(proposition-fidelity-benchmark.md) and",
            "`just check-proposition-fidelity-benchmark`.",
            "",
        ]
    )
    body = "\n".join(lines)
    assert_no_path_leaks(body, label="structural-source-fixtures.md")
    return body


def write_fixture_suite_report(*, root: Path | None = None) -> Path:
    base = root or judit_root()
    path = base / REPORT_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_fixture_suite_report(root=base), encoding="utf-8")
    return path


def check_fixture_suite_report(*, root: Path | None = None) -> None:
    base = root or judit_root()
    path = base / REPORT_RELATIVE
    expected = render_fixture_suite_report(root=base)
    if not path.is_file():
        raise AssertionError(
            f"Missing structural-source fixture report: {REPORT_RELATIVE}. "
            "Run: just inspect-structural-fixtures"
        )
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        raise AssertionError(
            f"Stale structural-source fixture report: {REPORT_RELATIVE}. "
            "Run: just inspect-structural-fixtures"
        )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Inspect Law Proposition Extractor structural-source fixtures (offline)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Inspect one XML source or fixture id.")
    inspect_p.add_argument("source", help="Fixture id or path to offline XML.")
    inspect_p.add_argument(
        "--format",
        choices=("json", "markdown", "tree"),
        default="json",
        dest="fmt",
    )

    sub.add_parser("inspect-suite", help="Inspect every registered fixture.")
    sub.add_parser("check", help="Run structural-source fidelity checks.")
    sub.add_parser("generate-report", help="Write structural-source-fixtures.md.")
    sub.add_parser("check-report", help="Check committed report is current.")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        source = str(args.source)
        fixture_match = None
        for fixture in load_structural_source_fixtures():
            if fixture.fixture_id == source:
                fixture_match = fixture
                break
        if fixture_match is not None:
            result = inspect_structural_fixture(fixture_match)
        else:
            path = Path(source)
            if not path.is_file():
                print(f"Unknown fixture id or missing file: {source}", file=sys.stderr)
                return 2
            # Emit relative-looking label only.
            result = inspect_structural_xml(
                path.read_text(encoding="utf-8"),
                fixture_id=path.stem,
                relative_source=path.name,
            )
        if args.fmt == "json":
            print(json.dumps(result.to_dict(), sort_keys=True, indent=2))
        elif args.fmt == "tree":
            print(result.tree_markdown)
        else:
            print(render_inspect_markdown(result))
        return 0 if result.audit.passed else 1

    if args.command == "inspect-suite":
        payload = [inspect_structural_fixture(f).to_dict() for f in load_structural_source_fixtures()]
        print(json.dumps(payload, sort_keys=True, indent=2))
        return 0

    if args.command == "check":
        results = check_all_structural_fixtures()
        check_fixture_suite_report()
        print(
            json.dumps(
                {
                    "checked": len(results),
                    "passed": all(r.audit.passed for r in results),
                    "fixture_ids": [r.fixture_id for r in results],
                },
                sort_keys=True,
                indent=2,
            )
        )
        return 0

    if args.command == "generate-report":
        path = write_fixture_suite_report()
        # Print repo-relative path only.
        print(str(REPORT_RELATIVE))
        return 0 if path.is_file() else 1

    if args.command == "check-report":
        check_fixture_suite_report()
        print("structural-source fixture report is current")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
