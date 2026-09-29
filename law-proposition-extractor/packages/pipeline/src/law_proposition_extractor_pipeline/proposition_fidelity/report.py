"""Deterministic Markdown report for proposition-fidelity benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from law_proposition_extractor_pipeline.source_structure_inspector import assert_no_path_leaks

from .fixtures import (
    REPORT_RELATIVE,
    load_manifest_notes,
    load_proposition_fidelity_cases,
    report_path,
)
from .results import FIDELITY_DIMENSIONS, PropositionFidelityBenchmarkResult
from .runner import run_proposition_fidelity_benchmark

BEGIN_MARKER = "<!-- BEGIN GENERATED: proposition-fidelity-benchmark -->"
END_MARKER = "<!-- END GENERATED: proposition-fidelity-benchmark -->"


def _role_findings(result: PropositionFidelityBenchmarkResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for case in result.cases:
        for role in case.role_results:
            for dim in role.dimension_results:
                if dim.status not in {"warning", "fail"}:
                    continue
                rows.append(
                    {
                        "case": case.case_id,
                        "role": role.role,
                        "dimension": dim.dimension,
                        "expected": dim.expected or role.notes,
                        "actual": dim.actual or dim.detail,
                        "locator": "",
                        "severity": dim.status,
                        "stage": dim.likely_pipeline_stage,
                        "note": dim.detail,
                    }
                )
        for dim in case.dimension_results:
            if dim.status not in {"warning", "fail"}:
                continue
            rows.append(
                {
                    "case": case.case_id,
                    "role": "(case)",
                    "dimension": dim.dimension,
                    "expected": dim.expected,
                    "actual": dim.actual or dim.detail,
                    "locator": "",
                    "severity": dim.status,
                    "stage": dim.likely_pipeline_stage,
                    "note": dim.detail,
                }
            )
    return rows


def render_benchmark_report(
    result: PropositionFidelityBenchmarkResult, *, root: Path | None = None
) -> str:
    cases = load_proposition_fidelity_cases(root=root)
    notes = load_manifest_notes(root=root)
    by_id = {c.case_id: c for c in cases}

    lines: list[str] = [
        "# Proposition-fidelity benchmark",
        "",
        "Offline multi-instrument regression for whether Law Proposition Extractor converts structurally",
        "parsed legislation into faithful, atomic, context-aware legal propositions.",
        "",
        "## Distinctions",
        "",
        "| Contract | Question |",
        "| --- | --- |",
        "| Structural-source fidelity | Did Law Proposition Extractor parse the source hierarchy and context correctly? |",
        "| Proposition fidelity | Did Law Proposition Extractor represent the operative legal claims correctly? |",
        "| Legal review | Is the interpretation acceptable for the intended legal use? |",
        "",
        "Passing this benchmark does **not** replace legal review.",
        "",
        "## Action fidelity",
        "",
        "Action fidelity is based on the **legal action**, **polarity**, **legal",
        "effect**, and **material objects**—not exact modal wording alone.",
        "",
        "Example (Article 49a prohibited mixing):",
        "",
        "- Source / live wording: catches “shall not be mixed”",
        "- Gold invariant: negative `mix` action, classified as a **prohibition**,",
        "  applying to catches",
        "",
        "“shall not be mixed” and “must not mix” can represent the same prohibition",
        "when predicate, polarity, legal effect, and material objects align. Active",
        "and passive voice are treated as non-material only where semantic roles",
        "remain preserved.",
        "",
        "Modal differences are **not** always immaterial:",
        "",
        "- `need not`, `should not`, and `must not` are **not** automatically equivalent",
        "- the evaluator may disregard shall/must surface form only after confirming",
        "  the expected legal effect and polarity",
        "",
        "Structured `action_expectation` fields are **evaluation gold only**. They do",
        "not alter Law Proposition Extractor proposition text, production extraction, or prompts.",
        "Benchmark gold remains human-authored.",
        "",
        "Legacy gold rows that only set `required_action` keep the historical",
        "substring / token-overlap matcher (no aggressive reinterpretation).",
        "",
        BEGIN_MARKER,
        "",
        "## Benchmark summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| cases | {result.totals.get('cases', 0)} |",
        f"| expected propositions | {result.totals.get('expected_propositions', 0)} |",
        f"| produced propositions | {result.totals.get('produced_propositions', 0)} |",
        f"| fully passing roles | {result.totals.get('fully_passing_roles', 0)} |",
        f"| warning roles | {result.totals.get('warning_roles', 0)} |",
        f"| failed roles | {result.totals.get('failed_roles', 0)} |",
        f"| unexpected propositions | {result.totals.get('unexpected_propositions', 0)} |",
        f"| benchmark version | {result.benchmark_version} |",
        "",
        "Runtime is printed on the terminal summary only (not committed), so check",
        "mode stays deterministic across machines.",
        "",
        "## Dimension summary",
        "",
        "| dimension | pass | warning | fail | not applicable |",
        "| --- | --- | --- | --- | --- |",
    ]
    for dim in FIDELITY_DIMENSIONS:
        counts = result.dimension_totals.get(dim) or {}
        lines.append(
            f"| {dim} | {counts.get('pass', 0)} | {counts.get('warning', 0)} | "
            f"{counts.get('fail', 0)} | {counts.get('not_applicable', 0)} |"
        )

    lines.extend(
        [
            "",
            "## Fixture matrix",
            "",
            "| case | structure | jurisdiction | heading | expected | provenance |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in cases:
        lines.append(
            f"| `{case.case_id}` | {case.structural_pattern} | {case.jurisdiction} | "
            f"{'yes' if case.heading_present else 'no'} | "
            f"{case.expected_proposition_count} | {case.provenance_kind} |"
        )

    lines.extend(
        [
            "",
            "## Per-case table",
            "",
            "| case | structure | expected | produced | result | material findings |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case_result in result.cases:
        findings = []
        if case_result.missing_roles:
            findings.append("missing: " + ", ".join(case_result.missing_roles))
        if case_result.unexpected_propositions:
            findings.append(f"unexpected×{len(case_result.unexpected_propositions)}")
        fail_dims = sorted(
            {
                d.dimension
                for r in case_result.role_results
                for d in r.dimension_results
                if d.status == "fail"
            }
            | {d.dimension for d in case_result.dimension_results if d.status == "fail"}
        )
        if fail_dims:
            findings.append("fail: " + ", ".join(fail_dims[:4]))
        if case_result.accepted_limitations:
            findings.append("accepted limitation recorded")
        finding_txt = "; ".join(findings) if findings else "—"
        lines.append(
            f"| `{case_result.case_id}` | {case_result.structural_pattern} | "
            f"{len(case_result.expected_roles)} | {case_result.produced_count} | "
            f"{case_result.case_status} | {finding_txt} |"
        )

    lines.extend(["", "## Role-level warnings and failures", ""])
    findings = _role_findings(result)
    if not findings:
        lines.append("None.")
    else:
        lines.extend(
            [
                "| case | role | dimension | expected invariant | actual | severity | stage | note |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in findings:
            lines.append(
                f"| `{row['case']}` | `{row['role']}` | {row['dimension']} | "
                f"{_cell(row['expected'])} | {_cell(row['actual'])} | "
                f"{row['severity']} | {row['stage']} | {_cell(row['note'])} |"
            )

    lines.extend(
        [
            "",
            "## Provenance notes",
            "",
        ]
    )
    for case in cases:
        lines.append(f"### `{case.case_id}`")
        lines.append("")
        lines.append(f"- Source fixture: `{case.source_fixture_relative}`")
        lines.append(f"- Provenance: **{case.provenance_kind}** — {case.provenance_note}")
        lines.append(f"- Locator: `{case.source_locator}`")
        if case.response:
            lines.append(
                f"- Response fixture prompt: {case.response.prompt_version} "
                f"(reflects_prompt_v3={case.response.reflects_prompt_v3}); "
                f"model alias `{case.response.model_alias}`"
            )
        if case.accepted_limitations:
            lines.append(
                "- Accepted limitations: " + "; ".join(case.accepted_limitations)
            )
        lines.append("")

    lines.extend(
        [
            "## Known corpus gaps",
            "",
        ]
    )
    for gap in notes.known_gaps:
        lines.append(f"- {gap}")
    if not notes.known_gaps:
        lines.append("- (none recorded)")

    lines.extend(
        [
            "",
            "## Limits",
            "",
            "- This is an **offline regression benchmark**.",
            "- Gold contracts are curated human invariants, not authoritative law.",
            "- Fixture responses do **not** measure current frontier-model success rate.",
            "- Passing does **not** establish authoritative legal correctness.",
            "- Human legal review remains required.",
            "- Do not treat a single aggregate percentage as the acceptance signal;",
            "  use the dimension summary above.",
            "",
            "## Commands",
            "",
            "```bash",
            "just run-proposition-fidelity-benchmark",
            "just check-proposition-fidelity-benchmark",
            "```",
            "",
            END_MARKER,
            "",
        ]
    )
    body = "\n".join(lines)
    assert_no_path_leaks(body, label="proposition-fidelity-benchmark.md")
    return body


def _cell(text: str) -> str:
    return " ".join(str(text or "").replace("|", "/").split())[:180] or "—"


def write_benchmark_report(
    result: PropositionFidelityBenchmarkResult | None = None, *, root: Path | None = None
) -> Path:
    payload = result or run_proposition_fidelity_benchmark(root=root)
    path = report_path(root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_benchmark_report(payload, root=root), encoding="utf-8")
    return path


def check_benchmark_report(*, root: Path | None = None) -> None:
    """Fail if committed report differs; does not modify the working tree."""
    result = run_proposition_fidelity_benchmark(root=root)
    expected = render_benchmark_report(result, root=root)
    path = report_path(root=root)
    if not path.is_file():
        raise AssertionError(
            f"Missing proposition-fidelity report: {REPORT_RELATIVE}. "
            "Run: just run-proposition-fidelity-benchmark"
        )
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        raise AssertionError(
            f"Stale proposition-fidelity report: {REPORT_RELATIVE}. "
            "Run: just run-proposition-fidelity-benchmark"
        )


def load_baseline(*, root: Path | None = None) -> dict[str, Any] | None:
    from .fixtures import baseline_path

    path = baseline_path(root=root)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(
    result: PropositionFidelityBenchmarkResult, *, root: Path | None = None
) -> Path:
    from .fixtures import baseline_path

    path = baseline_path(root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return path


def check_against_baseline(
    result: PropositionFidelityBenchmarkResult, *, root: Path | None = None
) -> list[str]:
    """Return regression failures vs committed baseline (empty if ok / no baseline)."""
    baseline = load_baseline(root=root)
    if baseline is None:
        return []
    regressions: list[str] = []
    base_cases = {c["case_id"]: c for c in baseline.get("cases") or [] if isinstance(c, dict)}
    for case in result.cases:
        prev = base_cases.get(case.case_id)
        if prev is None:
            continue
        prev_fail_roles = set(prev.get("missing_roles") or [])
        for role in case.role_results:
            role_fails = {
                d.dimension for d in role.dimension_results if d.status == "fail"
            }
            prev_role = next(
                (
                    r
                    for r in (prev.get("role_results") or [])
                    if isinstance(r, dict) and r.get("role") == role.role
                ),
                None,
            )
            prev_fail_dims = set()
            if isinstance(prev_role, dict):
                prev_fail_dims = {
                    d.get("dimension")
                    for d in (prev_role.get("dimension_results") or [])
                    if isinstance(d, dict) and d.get("status") == "fail"
                }
            new_fails = role_fails - prev_fail_dims
            if new_fails and role.role not in prev_fail_roles:
                # Critical contamination always fails
                critical = {
                    "evidence_fidelity",
                    "structural_context_boundary",
                    "actor_fidelity",
                    "legal_effect_fidelity",
                }
                hit = new_fails & critical
                if hit or role.status == "missing" and role.role not in prev_fail_roles:
                    regressions.append(
                        f"regression {case.case_id}/{role.role}: new fails {sorted(new_fails)}"
                    )
            if role.status == "missing" and role.role not in set(prev.get("missing_roles") or []):
                if case.case_id == "article_49a":
                    regressions.append(
                        f"regression {case.case_id}: Article 49a role missing: {role.role}"
                    )
    # Article 49a must remain fully green on hard dims
    a49 = next((c for c in result.cases if c.case_id == "article_49a"), None)
    if a49 is not None:
        for role in a49.role_results:
            if role.status != "matched":
                regressions.append(f"article_49a role not matched: {role.role}")
            for dim in role.dimension_results:
                if dim.status == "fail" and dim.dimension in {
                    "coverage",
                    "actor_fidelity",
                    "action_fidelity",
                    "legal_effect_fidelity",
                    "evidence_fidelity",
                    "structural_context_boundary",
                    "threshold_fidelity",
                    "exception_fidelity",
                }:
                    regressions.append(
                        f"article_49a hard fail: {role.role}/{dim.dimension}: {dim.detail}"
                    )
    return regressions
