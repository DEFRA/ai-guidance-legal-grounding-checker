"""Human-readable live calibration report (evaluation-only)."""

from __future__ import annotations

from typing import Any

from .models import LivePropositionCalibrationResult


def render_calibration_report(
    result: LivePropositionCalibrationResult | dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    call_summaries: list[dict[str, Any]] | None = None,
) -> str:
    data = result.to_dict() if isinstance(result, LivePropositionCalibrationResult) else dict(result)
    lines: list[str] = []
    lines.append("# Live proposition calibration report")
    lines.append("")
    lines.append(
        "This report measures **current frontier model + prompt v3** against "
        "proposition-fidelity gold contracts. It is distinct from the offline "
        "curated-response benchmark."
    )
    lines.append("")
    lines.append("## Run provenance")
    lines.append("")
    model = data.get("model") or {}
    lines.append(f"- calibration_run_id: `{data.get('calibration_run_id')}`")
    lines.append(f"- prompt_version: `{data.get('prompt_version')}`")
    lines.append(f"- model alias: `{model.get('configured_model_alias')}`")
    lines.append(f"- resolved provider/model: `{model.get('resolved_provider_model')}`")
    lines.append(f"- temperature: `{model.get('temperature')}`")
    lines.append(f"- seed: `{model.get('seed')}` ({model.get('seed_note')})")
    if manifest:
        lines.append(f"- calibration_timestamp: `{manifest.get('calibration_timestamp')}`")
        lines.append(f"- artifact_location: `calibration/proposition_fidelity/{data.get('calibration_run_id')}/`")
    lines.append(f"- provider_call_count: `{data.get('provider_call_count')}`")
    lines.append(f"- provider_retry_count: `{data.get('provider_retry_count')}`")
    lines.append(f"- runtime_seconds: `{data.get('runtime_seconds')}`")
    if data.get("estimated_cost_usd") is not None:
        lines.append(f"- estimated_cost_usd: `{data.get('estimated_cost_usd')}`")
    lines.append("")

    totals = data.get("totals") or {}
    lines.append("## Totals")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("| --- | --- |")
    for key in (
        "cases",
        "case_repetitions",
        "critical_gate_failures",
        "case_fidelity_failures",
        "repeatability_failures",
        "warnings",
    ):
        if key in totals:
            lines.append(f"| {key} | {totals[key]} |")
    lines.append("")

    lines.append("## Gates")
    lines.append("")
    lines.append("### Critical gate")
    lines.append("")
    crit = data.get("critical_failures") or []
    if crit:
        for row in crit:
            lines.append(f"- FAIL: {row}")
    else:
        lines.append("- PASS: all repetitions parseable; no heading-only / invented / unsupported threshold criticals recorded in gate list.")
    lines.append("")
    lines.append("### Warnings")
    lines.append("")
    warns = data.get("warnings") or []
    if warns:
        for row in warns:
            lines.append(f"- {row}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Dimension totals")
    lines.append("")
    lines.append("| dimension | pass | warning | fail | not_applicable |")
    lines.append("| --- | --- | --- | --- | --- |")
    for dim, counts in sorted((data.get("dimension_totals") or {}).items()):
        lines.append(
            f"| {dim} | {counts.get('pass', 0)} | {counts.get('warning', 0)} | "
            f"{counts.get('fail', 0)} | {counts.get('not_applicable', 0)} |"
        )
    lines.append("")

    lines.append("## Repeatability")
    lines.append("")
    rep = data.get("repeatability") or {}
    lines.append("| case | stability | fidelity gate | repeatability gate |")
    lines.append("| --- | --- | --- | --- |")
    for row in rep.get("cases") or []:
        lines.append(
            f"| `{row.get('case_id')}` | {row.get('stability')} | "
            f"{row.get('case_fidelity_gate')} | {row.get('repeatability_gate')} |"
        )
    lines.append("")

    lines.append("## Per-case / per-repetition")
    lines.append("")
    for case in data.get("cases") or []:
        lines.append(f"### `{case.get('case_id')}`")
        lines.append("")
        lines.append(
            f"stability=`{case.get('stability')}` successful={case.get('successful_repetitions')}/3 "
            f"stable_roles={case.get('stable_role_coverage')} count_variance={case.get('proposition_count_variance')}"
        )
        for finding in case.get("findings") or []:
            lines.append(f"- finding: {finding}")
        lines.append("")
        for rep_row in case.get("repetitions") or []:
            br = rep_row.get("benchmark_result") or {}
            lines.append(f"#### Repetition {rep_row.get('repetition')}")
            lines.append("")
            lines.append(
                f"- raw={rep_row.get('raw_response_status')} parse={rep_row.get('parse_status')} "
                f"validation={rep_row.get('validation_status')} props={rep_row.get('proposition_count')} "
                f"pf_status={br.get('case_status')} latency_s={rep_row.get('latency_seconds')}"
            )
            lines.append(
                f"- matched={br.get('matched_roles')} missing={br.get('missing_roles')} "
                f"unexpected={len(br.get('unexpected_propositions') or [])}"
            )
            hb = rep_row.get("heading_boundary") or {}
            if hb.get("heading_present"):
                lines.append(
                    f"- heading_boundary: only_prop={hb.get('heading_only_proposition')} "
                    f"only_evidence={hb.get('heading_only_evidence')} "
                    f"expansion={hb.get('heading_material_expansion')}"
                )
            a49 = rep_row.get("article_49a_detail")
            if a49:
                lines.append(
                    f"- article_49a: raw_rows={a49.get('model_proposed_row_count')} "
                    f"final={a49.get('final_proposition_count')} "
                    f"p1_group={a49.get('paragraph_1_group_ok')} "
                    f"p2_group={a49.get('paragraph_2_group_ok')} "
                    f"exception_to={a49.get('exception_to_count')} "
                    f"triggered_by={a49.get('triggered_by_count')}"
                )
            for fo in rep_row.get("failure_origins") or []:
                lines.append(
                    f"- origin/{fo.get('severity')}: {fo.get('likely_origin')} "
                    f"dim={fo.get('dimension')} role={fo.get('role')} — {fo.get('detail')}"
                )
            lines.append("")

    lines.append("## Human inspection pack")
    lines.append("")
    if call_summaries:
        for summary in call_summaries:
            lines.append(f"### {summary.get('case_id')} / rep {summary.get('repetition')}")
            lines.append("")
            lines.append("#### Source")
            lines.append("")
            lines.append(f"- locator: `{summary.get('source_locator')}`")
            if summary.get("legislative_heading"):
                lines.append(f"- legislative heading: {summary.get('legislative_heading')}")
            excerpt = summary.get("operative_source_excerpt") or ""
            lines.append("")
            lines.append("```text")
            lines.append(excerpt[:1200])
            lines.append("```")
            lines.append("")
            lines.append("#### Expected semantic roles")
            lines.append("")
            for role in summary.get("expected_roles") or []:
                lines.append(f"- `{role}`")
            lines.append("")
            lines.append("#### Model proposal (raw rows)")
            lines.append("")
            lines.append("```json")
            lines.append(summary.get("raw_model_rows_json") or "[]")
            lines.append("```")
            lines.append("")
            lines.append("#### Deterministic retained output")
            lines.append("")
            lines.append("```json")
            lines.append(summary.get("retained_propositions_json") or "[]")
            lines.append("```")
            lines.append("")
            lines.append("#### Rejected rows / diagnostics")
            lines.append("")
            for d in summary.get("diagnostics") or []:
                lines.append(f"- {d}")
            if summary.get("rejected_rows"):
                lines.append(f"- rejected_rows: {summary.get('rejected_rows')}")
            lines.append("")
            lines.append("#### Evaluator judgment")
            lines.append("")
            lines.append(f"- case_status: `{summary.get('case_status')}`")
            for dim in summary.get("dimension_highlights") or []:
                lines.append(f"- {dim}")
            lines.append("")
    else:
        lines.append(
            "See `calls/<case>-<repetition>.json` for source / raw / retained / judgment separation."
        )
        lines.append("")

    lines.append("## Promotion candidates")
    lines.append("")
    cands = data.get("promotion_candidates") or []
    if cands:
        for c in cands:
            lines.append(
                f"- `{c.get('case_id')}` rep {c.get('repetition')}: {c.get('reason')}"
            )
    else:
        lines.append("- none (no fully green representative responses identified)")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- Snapshot of one model/provider configuration at calibration time; not permanent proof of future behaviour."
    )
    lines.append(
        "- Article 49a uses three production required-locator extractions per case-repetition."
    )
    lines.append("- No LLM judge was used; scoring is the offline proposition-fidelity evaluator.")
    lines.append("- Curated response fixtures were not modified or promoted.")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_docs_page(
    result: LivePropositionCalibrationResult | dict[str, Any],
    *,
    manifest: dict[str, Any],
) -> str:
    data = result.to_dict() if isinstance(result, LivePropositionCalibrationResult) else dict(result)
    model = data.get("model") or {}
    lines = [
        "# Live proposition calibration",
        "",
        "Evaluation-only measurement of Law Proposition Extractor **prompt v3 + configured frontier model**",
        "against the proposition-fidelity gold contracts.",
        "",
        "## Offline benchmark vs live calibration",
        "",
        "| Contract | Question |",
        "| --- | --- |",
        "| Offline proposition-fidelity benchmark | Do curated extraction responses survive validation/reconciliation into faithful propositions? |",
        "| Live proposition calibration | Does the current frontier model, given prompt v3, produce extraction responses that survive the same path? |",
        "",
        "The offline benchmark remains the stable deterministic regression contract.",
        "Live calibration does **not** overwrite `tests/fixtures/proposition_fidelity/**`.",
        "",
        "## Latest calibration",
        "",
        f"- **Date / run id:** `{data.get('calibration_run_id')}`",
        f"- **Timestamp:** `{manifest.get('calibration_timestamp')}`",
        f"- **Model alias:** `{model.get('configured_model_alias')}`",
        f"- **Resolved provider/model:** `{model.get('resolved_provider_model')}`",
        f"- **Prompt version:** `{data.get('prompt_version')}`",
        f"- **Request parameters:** temperature=`{model.get('temperature')}`, seed=`{model.get('seed')}`",
        f"- **Case matrix:** `article_49a`, `uk_regulation_12_spread`, `wsi_regulation_36_4`",
        f"- **Repetitions:** 3 per case (9 case-repetitions)",
        f"- **Provider calls:** `{data.get('provider_call_count')}` (retries: `{data.get('provider_retry_count')}`)",
        f"- **Artifacts:** `calibration/proposition_fidelity/{data.get('calibration_run_id')}/`",
        "",
        "## Pass/fail summary",
        "",
        f"- critical failures: {len(data.get('critical_failures') or [])}",
        f"- warnings: {len(data.get('warnings') or [])}",
        "",
        "## Semantic stability",
        "",
    ]
    for row in (data.get("repeatability") or {}).get("cases") or []:
        lines.append(
            f"- `{row.get('case_id')}`: {row.get('stability')} "
            f"(fidelity={row.get('case_fidelity_gate')}, repeatability={row.get('repeatability_gate')})"
        )
    lines.extend(
        [
            "",
            "## Promotion status",
            "",
            "No automatic fixture promotion. Candidates (if any) are listed in the run report only.",
            "",
            "## Historical result vs current-code recheck",
            "",
            "The live calibration artifacts are an immutable historical record of what the",
            "frontier model produced under the code and evaluator **at run time**.",
            "",
            "A separate offline command can replay the exact saved raw responses through",
            "**current** deterministic production code and the corrected",
            "proposition-fidelity evaluator:",
            "",
            "```bash",
            f"just recheck-live-proposition-calibration {data.get('calibration_run_id')}",
            "```",
            "",
            "That writes only `current_code_recheck.json` / `current_code_recheck.md`.",
            "It does **not** overwrite historical `calibration_result.json`,",
            "`calibration_report.md`, or saved `calls/*.json`. No model/network calls.",
            "",
            "## Limitations",
            "",
            "- External model behaviour can change without notice.",
            "- Article 49a production path issues three fragment calls per repetition.",
            "- This page records one calibration event; re-run to refresh.",
            "- Current-code recheck is not a new model calibration; it only measures current",
            "  deterministic code against saved responses.",
            "",
            "## Commands",
            "",
            "```bash",
            "just run-live-proposition-calibration",
            "just inspect-live-proposition-calibration <run-id>",
            "just check-live-proposition-calibration <run-id>",
            "just recheck-live-proposition-calibration <run-id>",
            "just replay-live-article-49a-relationships <run-id>",
            "just replay-live-uk-regulation-12 <run-id>",
            "```",
            "",
            "Live run requires model credentials and network. Inspect/check/recheck/replay",
            "are offline.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
