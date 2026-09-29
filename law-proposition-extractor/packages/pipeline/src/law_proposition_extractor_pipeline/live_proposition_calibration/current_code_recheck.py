"""Complete current-code recheck of a saved live proposition calibration.

Loads original saved raw responses, replays them through current deterministic
production code, evaluates with the corrected proposition-fidelity evaluator,
and writes a separate ``current_code_recheck`` artifact.

Does not modify historical calibration artifacts. Makes no model or network
calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import load_proposition_fidelity_cases
from law_proposition_extractor_pipeline.proposition_fidelity.matching import match_roles_for_case, prop_by_id
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

from .artifacts import read_json
from .evaluate import evaluate_live_propositions
from .extract_live import run_live_dry_fragment
from .paths import CALIBRATION_CASES, REPETITIONS, call_artifact_name, calls_dir, run_dir
from .replay_article_49a import replay_article_49a_saved_call
from .replay_uk_regulation_12 import (
    raw_response_from_call,
    replay_uk_regulation_12_saved_call,
    summarize_dry_fragment_props,
)

_HISTORICAL_IMMUTABLE = (
    "calibration_result.json",
    "calibration_report.md",
    "calibration_manifest.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint_historical(base: Path) -> dict[str, str]:
    paths = [base / name for name in _HISTORICAL_IMMUTABLE]
    for case_id in CALIBRATION_CASES:
        for rep in REPETITIONS:
            paths.append(base / "calls" / call_artifact_name(case_id, rep))
    return {str(p): _sha256(p) for p in paths if p.is_file()}


def _dim_status(role_result: Any, dimension: str) -> str | None:
    for dim in role_result.dimension_results:
        if dim.dimension == dimension:
            return dim.status
    return None


def _collect_warnings_and_failures(pf: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role in pf.role_results:
        for dim in role.dimension_results:
            if dim.status in {"warning", "fail"}:
                rows.append(
                    {
                        "scope": "role",
                        "role": role.role,
                        "dimension": dim.dimension,
                        "status": dim.status,
                        "detail": dim.detail,
                        "expected": dim.expected,
                        "actual": dim.actual,
                    }
                )
    for dim in pf.dimension_results:
        if dim.status in {"warning", "fail"}:
            rows.append(
                {
                    "scope": "case",
                    "role": None,
                    "dimension": dim.dimension,
                    "status": dim.status,
                    "detail": dim.detail,
                    "expected": dim.expected,
                    "actual": dim.actual,
                }
            )
    return rows


def _classify_remaining(item: dict[str, Any]) -> str:
    dimension = str(item.get("dimension") or "")
    detail = str(item.get("detail") or "").lower()
    if dimension == "completeness_fidelity":
        return "accepted_limitation"
    if "action_fidelity" in dimension:
        return "evaluator_issue"
    if "coverage" in dimension or "unexpected" in detail:
        return "production_legal_output_issue"
    if "context_dependent" in detail:
        return "accepted_limitation"
    return "human_review_question"


def _historical_case_slice(
    historical_result: dict[str, Any], case_id: str, repetition: int
) -> dict[str, Any]:
    for case in historical_result.get("cases") or []:
        if case.get("case_id") != case_id:
            continue
        for rep in case.get("repetitions") or []:
            if int(rep.get("repetition") or 0) != repetition:
                continue
            br = rep.get("benchmark_result") or {}
            fails: list[str] = []
            warns: list[str] = []
            for role in br.get("role_results") or []:
                for dim in role.get("dimension_results") or []:
                    key = f"{role.get('role')}:{dim.get('dimension')}"
                    if dim.get("status") == "fail":
                        fails.append(key)
                    elif dim.get("status") == "warning":
                        warns.append(key)
            for dim in br.get("dimension_results") or []:
                key = f"case:{dim.get('dimension')}"
                if dim.get("status") == "fail":
                    fails.append(key)
                elif dim.get("status") == "warning":
                    warns.append(key)
            detail = rep.get("article_49a_detail") or {}
            return {
                "case_status": br.get("case_status"),
                "produced_count": br.get("produced_count"),
                "matched_roles": list(br.get("matched_roles") or []),
                "unexpected_count": len(br.get("unexpected_propositions") or []),
                "failures": fails,
                "warnings": warns,
                "triggered_by_count": detail.get("triggered_by_count"),
                "exception_to_count": detail.get("exception_to_count"),
            }
    return {}


def _replay_dry_fragment_saved_call(
    call: dict[str, Any],
    *,
    case: Any,
) -> dict[str, Any]:
    """Replay one saved dry-fragment call through current production extract."""
    raw = raw_response_from_call(call)

    class _Call:
        def __init__(self, body: str) -> None:
            self.raw_response = body
            self.is_retry = False
            self.resolved_model = "frontier_extract"

        def to_dict(self) -> dict[str, Any]:
            return {
                "raw_response": self.raw_response,
                "network": False,
                "resolved_model": self.resolved_model,
            }

    class _ReplayLLM:
        class _Settings:
            frontier_extract_model = "frontier_extract"
            local_extract_model = "local_extract"
            max_extract_input_tokens = 150_000
            extract_model_context_limit = 200_000
            skip_llm_preflight = True

        def __init__(self) -> None:
            self.settings = self._Settings()
            self.calls: list[Any] = []

        def complete_text(self, *, prompt: str, model: str, **kwargs: object) -> str:
            return self.complete_text_result(prompt=prompt, model=model, **kwargs).content

        def complete_text_result(
            self, *, prompt: str, model: str, **kwargs: object
        ) -> TextCompletionResult:
            _ = (prompt, model, kwargs)
            self.calls.append(_Call(raw))
            return TextCompletionResult(content=raw, finish_reason="stop")

    llm = _ReplayLLM()
    outcome = run_live_dry_fragment(case, llm_client=llm)  # type: ignore[arg-type]
    summary = summarize_dry_fragment_props(outcome.props, case)
    summary["propositions"] = list(outcome.props)
    summary["operative_text"] = str(outcome.operative_text or "")
    summary["heading_text"] = outcome.heading_text
    summary["heading_boundary"] = dict(outcome.heading_boundary or {})
    summary["diagnostics"] = list(outcome.diagnostics or [])
    summary["model_calls_made"] = 0
    summary["replay_llm_lookups"] = len(llm.calls)
    summary["raw_response_mutated"] = False
    summary["validation_errors"] = list(outcome.validation_errors or [])
    return summary


def _evaluate_replayed(
    *,
    case: Any,
    props: list[dict[str, Any]],
    operative_text: str,
    heading_text: str | None,
    diagnostics: list[str],
    article_49a_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pf = evaluate_live_propositions(
        case,
        props,
        operative_text=operative_text,
        heading_text=heading_text,
        diagnostics=diagnostics,
        article_49a_bundle=article_49a_bundle,
    )
    action_by_role: dict[str, Any] = {}
    for role in pf.role_results:
        for dim in role.dimension_results:
            if dim.dimension == "action_fidelity":
                action_by_role[role.role] = dim.to_dict()
    remaining = _collect_warnings_and_failures(pf)
    for row in remaining:
        row["classification"] = _classify_remaining(row)
    return {
        "case_status": pf.case_status,
        "produced_count": pf.produced_count,
        "matched_roles": list(pf.matched_roles),
        "matched_role_count": len(pf.matched_roles),
        "missing_roles": list(pf.missing_roles),
        "unexpected_count": len(pf.unexpected_propositions),
        "unexpected_propositions": list(pf.unexpected_propositions),
        "action_fidelity_by_role": action_by_role,
        "remaining_warnings_or_failures": remaining,
        "benchmark_result": pf.to_dict(),
    }


def _recheck_article_49a_rep(
    *,
    call: dict[str, Any],
    case: Any,
    work_dir: Path | None,
) -> dict[str, Any]:
    replay = replay_article_49a_saved_call(call, work_dir=work_dir)
    props = list(replay.get("propositions") or [])
    opaque = replay.get("opaque_roles") or {}
    operative = str(replay.get("operative_text") or "") or str(
        call.get("operative_source_excerpt") or ""
    )
    heading = call.get("legislative_heading")
    heading_text = str(heading) if heading else case.heading_text
    evaluation = _evaluate_replayed(
        case=case,
        props=props,
        operative_text=operative,
        heading_text=heading_text,
        diagnostics=["runner=article_49a_current_code_recheck"],
        article_49a_bundle={"propositions": props, "opaque_roles": opaque},
    )
    matches, _ = match_roles_for_case(
        case, props, article_49a_bundle={"propositions": props, "opaque_roles": opaque}
    )
    p2 = next((m for m in matches if m.role == "prohibited-mixing-rule"), None)
    p2_prop = prop_by_id(props, p2.proposition_id) if p2 else None
    heading_rejected = 0
    for p in props:
        meta = p.get("extraction_debug_meta") if isinstance(p.get("extraction_debug_meta"), dict) else {}
        evidence = str(meta.get("evidence_quote") or "")
        text = str(p.get("proposition_text") or "")
        if case.heading_text and case.heading_text.lower() in (evidence + " " + text).lower():
            # Soft diagnostic only — production heading boundary is checked separately.
            if evidence.strip() == str(case.heading_text).strip():
                heading_rejected += 1
    return {
        "replay": {
            "proposition_count": replay.get("proposition_count"),
            "paragraph_1_group_size": replay.get("paragraph_1_group_size"),
            "paragraph_2_group_size": replay.get("paragraph_2_group_size"),
            "exception_to_count": replay.get("exception_to_count"),
            "triggered_by_count": replay.get("triggered_by_count"),
            "p3_trigger_condition_proposition_ids": replay.get(
                "p3_trigger_condition_proposition_ids"
            ),
            "p3_proposition_text": replay.get("p3_proposition_text"),
            "opaque_roles": opaque,
            "model_calls_made": replay.get("model_calls_made"),
            "replay_llm_lookups": replay.get("replay_llm_lookups"),
        },
        "evaluation": evaluation,
        "p2": {
            "proposition_id": (p2.proposition_id if p2 else None),
            "proposition_text": (p2_prop or {}).get("proposition_text"),
            "action": (p2_prop or {}).get("action"),
            "legal_effect_type": (p2_prop or {}).get("legal_effect_type"),
            "action_fidelity": evaluation["action_fidelity_by_role"].get(
                "prohibited-mixing-rule"
            ),
        },
        "heading_boundary_pass": heading_rejected == 0,
    }


def _recheck_dry_fragment_rep(
    *,
    call: dict[str, Any],
    case: Any,
    case_id: str,
) -> dict[str, Any]:
    if case_id == "uk_regulation_12_spread":
        replay = replay_uk_regulation_12_saved_call(call, case=case)
    else:
        replay = _replay_dry_fragment_saved_call(call, case=case)
    props = list(replay.get("propositions") or [])
    evaluation = _evaluate_replayed(
        case=case,
        props=props,
        operative_text=str(replay.get("operative_text") or ""),
        heading_text=replay.get("heading_text") or case.heading_text,
        diagnostics=list(replay.get("diagnostics") or []),
    )
    return {
        "replay": {
            "proposition_count": replay.get("proposition_count"),
            "matched_roles": replay.get("matched_roles"),
            "unexpected_count": replay.get("unexpected_count"),
            "has_organic_manure_spread_prohibition": replay.get(
                "has_organic_manure_spread_prohibition"
            ),
            "threshold_10_metres_preserved": replay.get("threshold_10_metres_preserved"),
            "measurement_basis_preserved": replay.get("measurement_basis_preserved"),
            "evidence_grounded": replay.get("evidence_grounded"),
            "proposition_texts": replay.get("proposition_texts"),
            "conditions": replay.get("conditions"),
            "heading_boundary": replay.get("heading_boundary"),
            "model_calls_made": replay.get("model_calls_made"),
            "replay_llm_lookups": replay.get("replay_llm_lookups"),
        },
        "evaluation": evaluation,
    }


def _build_change_table(
    *,
    historical_result: dict[str, Any],
    cases_payload: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Historical live calibration vs current-code saved-response recheck."""
    a49 = next(c for c in cases_payload if c["case_id"] == "article_49a")
    uk = next(c for c in cases_payload if c["case_id"] == "uk_regulation_12_spread")
    wsi = next(c for c in cases_payload if c["case_id"] == "wsi_regulation_36_4")

    hist_a49 = _historical_case_slice(historical_result, "article_49a", 1)
    hist_uk = _historical_case_slice(historical_result, "uk_regulation_12_spread", 1)
    hist_wsi = _historical_case_slice(historical_result, "wsi_regulation_36_4", 1)

    cur_a49 = a49["repetitions"][0]
    cur_uk = uk["repetitions"][0]
    cur_wsi = wsi["repetitions"][0]

    a49_action = (
        (cur_a49.get("p2") or {}).get("action_fidelity") or {}
    ).get("status")
    hist_action = "fail"  # live-pf-20260715T155907Z P2 action_fidelity fail ×3

    completeness_hist = "warning (context_dependent vs complete on E2 / WSI)"
    remaining = []
    for case in cases_payload:
        for rep in case["repetitions"]:
            remaining.extend(
                (rep.get("evaluation") or {}).get("remaining_warnings_or_failures") or []
            )
    completeness_cur = (
        "warning retained"
        if any(r.get("dimension") == "completeness_fidelity" for r in remaining)
        else "cleared"
    )

    return [
        {
            "finding": "Article 49a triggered_by",
            "historical_result": f"{hist_a49.get('triggered_by_count')} (expected 1)",
            "current_code_result": str(
                (cur_a49.get("replay") or {}).get("triggered_by_count")
            ),
            "change_origin": "relationship.infer_triggered_by v2",
        },
        {
            "finding": "UK regulation 12 proposition count",
            "historical_result": str(hist_uk.get("produced_count")),
            "current_code_result": str(
                (cur_uk.get("replay") or {}).get("proposition_count")
            ),
            "change_origin": "extraction.suppress_dependent_qualification v1",
        },
        {
            "finding": "Article 49a P2 action fidelity",
            "historical_result": hist_action,
            "current_code_result": str(a49_action),
            "change_origin": "structured action_expectation evaluator",
        },
        {
            "finding": "completeness warnings",
            "historical_result": completeness_hist,
            "current_code_result": completeness_cur,
            "change_origin": "unchanged (deferred; not part of this task)",
        },
        {
            "finding": "WSI regulation 36(4) expected proposition",
            "historical_result": f"present; case_status={hist_wsi.get('case_status')}",
            "current_code_result": (
                f"present; case_status={(cur_wsi.get('evaluation') or {}).get('case_status')}"
            ),
            "change_origin": "no production change; recheck confirms stability",
        },
    ]


def render_current_code_recheck_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Current-code saved-response recheck",
        "",
        "This report is **not** a new live model run. It replays the exact saved",
        "raw responses from a historical live calibration through current",
        "deterministic production code and the corrected proposition-fidelity",
        "evaluator.",
        "",
        f"- **calibration_run_id:** `{payload.get('calibration_run_id')}`",
        f"- **model_calls_made:** `{payload.get('model_calls_made')}`",
        f"- **network_calls_made:** `{payload.get('network_calls_made')}`",
        f"- **historical_artifacts_modified:** `{payload.get('historical_artifacts_modified')}`",
        "",
        "## Historical live calibration vs current-code recheck",
        "",
        "| finding | historical result | current-code result | change origin |",
        "| --- | --- | --- | --- |",
    ]
    for row in payload.get("change_table") or []:
        lines.append(
            f"| {row.get('finding')} | {row.get('historical_result')} | "
            f"{row.get('current_code_result')} | {row.get('change_origin')} |"
        )

    lines.extend(
        [
            "",
            "## Distinctions",
            "",
            "### Historical live calibration",
            "",
            "What happened under the code and evaluator at run time",
            f"(`{payload.get('calibration_run_id')}`).",
            "Recorded in immutable `calibration_result.json` / `calibration_report.md`.",
            "",
            "### Current-code saved-response recheck",
            "",
            "What the exact same model responses produce under:",
            "",
            "- `relationship.infer_triggered_by` v2",
            "- `extraction.suppress_dependent_qualification` v1",
            "- corrected structured action-fidelity evaluation",
            "",
            "Written only to `current_code_recheck.json` / `current_code_recheck.md`.",
            "",
            "## Case results",
            "",
        ]
    )

    for case in payload.get("cases") or []:
        lines.append(f"### `{case.get('case_id')}`")
        lines.append("")
        for rep in case.get("repetitions") or []:
            ev = rep.get("evaluation") or {}
            replay = rep.get("replay") or {}
            lines.append(f"- repetition `{rep.get('repetition')}`:")
            lines.append(
                f"  - produced={ev.get('produced_count')} "
                f"matched={ev.get('matched_role_count')}/"
                f"{len(ev.get('matched_roles') or [])} "
                f"unexpected={ev.get('unexpected_count')} "
                f"status={ev.get('case_status')}"
            )
            if case.get("case_id") == "article_49a":
                p2 = (rep.get("p2") or {}).get("action_fidelity") or {}
                lines.append(
                    f"  - triggered_by={replay.get('triggered_by_count')} "
                    f"exception_to={replay.get('exception_to_count')} "
                    f"p1_group={replay.get('paragraph_1_group_size')} "
                    f"p2_group={replay.get('paragraph_2_group_size')} "
                    f"P2_action_fidelity={p2.get('status')}"
                )
            if case.get("case_id") == "uk_regulation_12_spread":
                lines.append(
                    f"  - threshold_10m={replay.get('threshold_10_metres_preserved')} "
                    f"measurement_basis={replay.get('measurement_basis_preserved')} "
                    f"evidence={replay.get('evidence_grounded')}"
                )
        lines.append("")

    lines.extend(["## Remaining warnings / failures", ""])
    remaining = payload.get("remaining_inventory") or []
    if not remaining:
        lines.append("None.")
    else:
        lines.append("| case | rep | role | dimension | status | classification | detail |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for row in remaining:
            lines.append(
                f"| {row.get('case_id')} | {row.get('repetition')} | "
                f"{row.get('role') or '—'} | {row.get('dimension')} | "
                f"{row.get('status')} | {row.get('classification')} | "
                f"{(row.get('detail') or '').replace('|', '/')} |"
            )
    lines.append("")
    lines.extend(
        [
            "## Limitations intentionally deferred",
            "",
            "- Completeness `context_dependent` vs `complete` mismatches are not fixed here.",
            "- No production prompt or proposition-text changes.",
            "- Historical calibration verdict remains the immutable record of the live run.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def recheck_live_proposition_calibration(
    calibration_run_id: str,
    *,
    root: Path | None = None,
    write_result: bool = True,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Replay all saved live-calibration responses under current deterministic code."""
    base = run_dir(calibration_run_id, root=root)
    if not base.is_dir():
        raise FileNotFoundError(f"Calibration run not found: {base}")

    before = _fingerprint_historical(base)
    historical_result = read_json(base / "calibration_result.json")
    cases_by_id = {c.case_id: c for c in load_proposition_fidelity_cases(root=root)}

    cases_payload: list[dict[str, Any]] = []
    remaining_inventory: list[dict[str, Any]] = []
    raw_fingerprints: list[dict[str, Any]] = []

    for case_id in CALIBRATION_CASES:
        case = cases_by_id[case_id]
        repetitions: list[dict[str, Any]] = []
        for rep in REPETITIONS:
            call_path = calls_dir(calibration_run_id, root=root) / call_artifact_name(
                case_id, rep
            )
            call = read_json(call_path)
            call_before = json.dumps(call.get("provider_calls"), sort_keys=True)
            fingerprints = [
                {
                    "case_id": case_id,
                    "repetition": rep,
                    "call_index": row.get("call_index"),
                    "fragment_locator_hint": row.get("fragment_locator_hint"),
                    "raw_response_sha256": hashlib.sha256(
                        str(row.get("raw_response") or "").encode("utf-8")
                    ).hexdigest(),
                }
                for row in (call.get("provider_calls") or [])
                if isinstance(row, dict)
            ]
            raw_fingerprints.extend(fingerprints)

            historical = _historical_case_slice(historical_result, case_id, rep)
            if case_id == "article_49a":
                current = _recheck_article_49a_rep(
                    call=call,
                    case=case,
                    work_dir=(work_dir / f"{case_id}-{rep}") if work_dir else None,
                )
            else:
                current = _recheck_dry_fragment_rep(
                    call=call, case=case, case_id=case_id
                )

            after_call = read_json(call_path)
            if call_before != json.dumps(after_call.get("provider_calls"), sort_keys=True):
                raise AssertionError(
                    f"Historical call artifact mutated: {case_id} rep {rep}"
                )

            row = {
                "repetition": rep,
                "historical_live_calibration": historical,
                **current,
                "raw_response_fingerprints": fingerprints,
            }
            repetitions.append(row)
            for item in (current.get("evaluation") or {}).get(
                "remaining_warnings_or_failures"
            ) or []:
                remaining_inventory.append(
                    {
                        "case_id": case_id,
                        "repetition": rep,
                        **item,
                    }
                )

        cases_payload.append(
            {
                "case_id": case_id,
                "repetitions": repetitions,
            }
        )

    after = _fingerprint_historical(base)
    if before != after:
        raise AssertionError("Historical calibration artifacts were mutated during recheck.")

    change_table = _build_change_table(
        historical_result=historical_result,
        cases_payload=cases_payload,
    )

    payload: dict[str, Any] = {
        "schema": "law-proposition-extractor.live_proposition_calibration.current_code_recheck.v1",
        "calibration_run_id": calibration_run_id,
        "kind": "saved_response_replay_under_current_deterministic_code_and_corrected_evaluator",
        "distinguished_from": "original live calibration result",
        "historical_record": {
            "calibration_result": "calibration_result.json",
            "calibration_report": "calibration_report.md",
            "note": "immutable historical live-calibration verdict",
        },
        "applied_current_code": [
            "relationship.infer_triggered_by v2",
            "extraction.suppress_dependent_qualification v1",
            "structured action_expectation action fidelity",
        ],
        "model_calls_made": 0,
        "network_calls_made": 0,
        "historical_artifacts_modified": False,
        "cases": cases_payload,
        "change_table": change_table,
        "remaining_inventory": remaining_inventory,
        "raw_response_fingerprints": raw_fingerprints,
        "totals": {
            "cases": len(cases_payload),
            "case_repetitions": sum(len(c["repetitions"]) for c in cases_payload),
            "remaining_warnings": sum(
                1 for r in remaining_inventory if r.get("status") == "warning"
            ),
            "remaining_failures": sum(
                1 for r in remaining_inventory if r.get("status") == "fail"
            ),
        },
    }

    if write_result:
        json_path = base / "current_code_recheck.json"
        md_path = base / "current_code_recheck.md"
        json_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        md_path.write_text(render_current_code_recheck_markdown(payload), encoding="utf-8")
        # Confirm historical still untouched after write of sibling artifacts.
        after_write = _fingerprint_historical(base)
        if before != after_write:
            raise AssertionError(
                "Writing current_code_recheck mutated historical calibration artifacts."
            )
        payload["written_to"] = {
            "json": str(json_path),
            "markdown": str(md_path),
        }

    return payload


def assert_current_code_recheck(payload: dict[str, Any]) -> None:
    """Assert expected current-code recheck invariants for the live calibration matrix."""
    if payload.get("model_calls_made") != 0:
        raise AssertionError("Current-code recheck must not call the model.")
    if payload.get("network_calls_made") != 0:
        raise AssertionError("Current-code recheck must not make network calls.")
    if payload.get("historical_artifacts_modified"):
        raise AssertionError("Current-code recheck must not modify historical artifacts.")

    cases = {c["case_id"]: c for c in payload.get("cases") or []}
    if set(cases) != set(CALIBRATION_CASES):
        raise AssertionError(f"Expected cases {CALIBRATION_CASES}; got {sorted(cases)}")

    for case_id in CALIBRATION_CASES:
        reps = cases[case_id].get("repetitions") or []
        if len(reps) != 3:
            raise AssertionError(f"{case_id}: expected 3 repetitions; got {len(reps)}")

    for rep in cases["article_49a"]["repetitions"]:
        replay = rep.get("replay") or {}
        evaluation = rep.get("evaluation") or {}
        p2 = (rep.get("p2") or {}).get("action_fidelity") or {}
        if replay.get("proposition_count") != 6:
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: props="
                f"{replay.get('proposition_count')}"
            )
        if evaluation.get("matched_role_count") != 6:
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: matched="
                f"{evaluation.get('matched_role_count')}"
            )
        if evaluation.get("unexpected_count") != 0:
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: unexpected="
                f"{evaluation.get('unexpected_count')}"
            )
        if p2.get("status") != "pass":
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: P2 action_fidelity="
                f"{p2.get('status')} detail={p2.get('detail')}"
            )
        if replay.get("triggered_by_count") != 1:
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: triggered_by="
                f"{replay.get('triggered_by_count')}"
            )
        if replay.get("exception_to_count") != 3:
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: exception_to="
                f"{replay.get('exception_to_count')}"
            )
        if replay.get("paragraph_1_group_size") != 2:
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: paragraph_1_group="
                f"{replay.get('paragraph_1_group_size')}"
            )
        if replay.get("paragraph_2_group_size") != 3:
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: paragraph_2_group="
                f"{replay.get('paragraph_2_group_size')}"
            )
        triggers = replay.get("p3_trigger_condition_proposition_ids") or []
        if len(triggers) != 3:
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: P3 triggers={len(triggers)}"
            )
        if not rep.get("heading_boundary_pass", True):
            raise AssertionError(
                f"article_49a rep {rep.get('repetition')}: heading boundary failed"
            )

    for rep in cases["uk_regulation_12_spread"]["repetitions"]:
        replay = rep.get("replay") or {}
        evaluation = rep.get("evaluation") or {}
        if replay.get("proposition_count") != 1:
            raise AssertionError(
                f"uk_regulation_12 rep {rep.get('repetition')}: props="
                f"{replay.get('proposition_count')}; texts={replay.get('proposition_texts')}"
            )
        if evaluation.get("unexpected_count") != 0:
            raise AssertionError(
                f"uk_regulation_12 rep {rep.get('repetition')}: unexpected="
                f"{evaluation.get('unexpected_count')}"
            )
        if not replay.get("has_organic_manure_spread_prohibition"):
            raise AssertionError(
                f"uk_regulation_12 rep {rep.get('repetition')}: prohibition missing"
            )
        if not replay.get("threshold_10_metres_preserved"):
            raise AssertionError(
                f"uk_regulation_12 rep {rep.get('repetition')}: threshold missing"
            )
        if not replay.get("measurement_basis_preserved"):
            raise AssertionError(
                f"uk_regulation_12 rep {rep.get('repetition')}: measurement basis missing"
            )
        if not replay.get("evidence_grounded"):
            raise AssertionError(
                f"uk_regulation_12 rep {rep.get('repetition')}: evidence not grounded"
            )

    for rep in cases["wsi_regulation_36_4"]["repetitions"]:
        evaluation = rep.get("evaluation") or {}
        if "record-retention-calculations" not in (evaluation.get("matched_roles") or []):
            raise AssertionError(
                f"wsi rep {rep.get('repetition')}: expected recordkeeping role missing"
            )
        if evaluation.get("unexpected_count") != 0:
            raise AssertionError(
                f"wsi rep {rep.get('repetition')}: unexpected="
                f"{evaluation.get('unexpected_count')}"
            )
        # Completeness warnings may remain.
        fails = [
            r
            for r in evaluation.get("remaining_warnings_or_failures") or []
            if r.get("status") == "fail"
        ]
        if fails:
            raise AssertionError(
                f"wsi rep {rep.get('repetition')}: unexpected failures={fails}"
            )


def current_code_recheck_available(calibration_run_id: str, *, root: Path | None = None) -> bool:
    return run_dir(calibration_run_id, root=root or judit_root()).is_dir()
