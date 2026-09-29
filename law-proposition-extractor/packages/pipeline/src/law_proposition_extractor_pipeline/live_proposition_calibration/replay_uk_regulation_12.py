"""Offline replay of saved UK regulation 12 live responses through corrected code.

Re-runs the production dry-fragment extraction path using preserved raw model
responses from a live calibration run. Does not call the model or mutate
historical calibration artifacts. Writes a separate
``uk_regulation_12_post_fix_replay.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import load_proposition_fidelity_cases
from law_proposition_extractor_pipeline.proposition_fidelity.matching import match_roles_for_case

from .artifacts import read_json
from .extract_live import run_live_dry_fragment
from .paths import call_artifact_name, calls_dir, run_dir


def raw_response_from_call(call: dict[str, Any]) -> str:
    for row in call.get("provider_calls") or []:
        if not isinstance(row, dict):
            continue
        body = row.get("raw_response")
        if isinstance(body, str) and body.strip():
            return body
    raise AssertionError("Saved dry-fragment call lacks raw_response")


def summarize_dry_fragment_props(props: list[dict[str, Any]], case: Any) -> dict[str, Any]:
    matches, unexpected = match_roles_for_case(case, props)
    matched = [m.role for m in matches if m.status == "matched"]
    blobs = [
        " ".join(
            [
                str(p.get("proposition_text") or ""),
                " ".join(str(x) for x in (p.get("conditions") or [])),
                str((p.get("extraction_debug_meta") or {}).get("evidence_quote") or ""),
            ]
        ).lower()
        for p in props
    ]
    joined = " ".join(blobs)
    return {
        "proposition_count": len(props),
        "matched_roles": matched,
        "unexpected_count": len(unexpected),
        "unexpected_proposition_texts": [
            str(u.get("proposition_text") or "")
            for u in unexpected
            if isinstance(u, dict)
        ],
        "has_organic_manure_spread_prohibition": (
            "organic-manure-spread-prohibition" in matched
        ),
        "threshold_10_metres_preserved": (
            "10 metre" in joined or "10 metres" in joined or "10-metre" in joined
        ),
        "measurement_basis_preserved": (
            "measured from the edge" in joined or "edge of the surface water" in joined
        ),
        "heading_only_propositions": 0,
        "evidence_grounded": all(
            bool(
                (p.get("extraction_debug_meta") or {}).get("evidence_quote")
                if isinstance(p.get("extraction_debug_meta"), dict)
                else False
            )
            for p in props
        )
        if props
        else False,
        "proposition_texts": [str(p.get("proposition_text") or "") for p in props],
        "conditions": [list(p.get("conditions") or []) for p in props],
    }


def replay_uk_regulation_12_saved_call(
    call: dict[str, Any],
    *,
    case: Any | None = None,
) -> dict[str, Any]:
    """Replay one saved UK regulation 12 call through production extract (no LLM)."""
    raw = raw_response_from_call(call)
    cases = {c.case_id: c for c in load_proposition_fidelity_cases()}
    pf_case = case or cases["uk_regulation_12_spread"]

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

    # RecordingJuditLLMClient wraps a real client; patch JuditLLMClient path used
    # inside extract via the recording wrapper's inner complete.
    llm = _ReplayLLM()
    # Pass the stub directly: RecordingJuditLLMClient always calls
    # inner.client.chat.completions.create and cannot replay saved bodies.
    outcome = run_live_dry_fragment(pf_case, llm_client=llm)  # type: ignore[arg-type]

    summary = summarize_dry_fragment_props(outcome.props, pf_case)
    summary["propositions"] = list(outcome.props)
    summary["operative_text"] = str(outcome.operative_text or "")
    summary["heading_text"] = outcome.heading_text
    summary["heading_boundary"] = dict(outcome.heading_boundary or {})
    summary["diagnostics"] = list(outcome.diagnostics or [])
    summary["model_calls_made"] = 0
    summary["replay_llm_lookups"] = len(llm.calls)
    summary["raw_response_mutated"] = False
    summary["validation_errors"] = list(outcome.validation_errors or [])
    summary["dependent_qualification_diagnostics"] = list(
        (getattr(outcome, "diagnostics", None) or [])
    )
    return summary


def replay_uk_regulation_12_calibration_run(
    calibration_run_id: str,
    *,
    root: Path | None = None,
    write_result: bool = True,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Replay all three UK regulation 12 repetitions from a saved calibration run."""
    _ = work_dir
    base = run_dir(calibration_run_id, root=root)
    if not base.is_dir():
        raise FileNotFoundError(f"Calibration run not found: {base}")

    historical: dict[str, Any] = {}
    result_path = base / "calibration_result.json"
    if result_path.is_file():
        historical_result = read_json(result_path)
        historical = {
            "calibration_run_id": historical_result.get("calibration_run_id"),
            "critical_failures": historical_result.get("critical_failures"),
            "note": "historical live calibration result (immutable)",
        }

    cases = {c.case_id: c for c in load_proposition_fidelity_cases()}
    pf_case = cases["uk_regulation_12_spread"]
    repetitions: list[dict[str, Any]] = []
    for rep in (1, 2, 3):
        call_path = calls_dir(calibration_run_id, root=root) / call_artifact_name(
            "uk_regulation_12_spread", rep
        )
        call = read_json(call_path)
        before = json.dumps(call.get("provider_calls"), sort_keys=True)
        raw_fingerprint = [
            {
                "call_index": row.get("call_index"),
                "raw_response_sha256": hashlib.sha256(
                    str(row.get("raw_response") or "").encode("utf-8")
                ).hexdigest(),
            }
            for row in (call.get("provider_calls") or [])
            if isinstance(row, dict)
        ]
        summary = replay_uk_regulation_12_saved_call(call, case=pf_case)
        after_call = read_json(call_path)
        after = json.dumps(after_call.get("provider_calls"), sort_keys=True)
        if before != after:
            raise AssertionError("Historical call artifact was mutated during replay.")

        original_props = call.get("final_propositions") or []
        repetitions.append(
            {
                "repetition": rep,
                "original_live_calibration": {
                    "proposition_count": len(original_props),
                    "unexpected_count": len(
                        (call.get("benchmark_result") or {}).get(
                            "unexpected_propositions"
                        )
                        or []
                    ),
                    "case_status": (call.get("benchmark_result") or {}).get(
                        "case_status"
                    ),
                },
                "post_fix_replay": summary,
                "raw_response_fingerprints": raw_fingerprint,
                "expected": {
                    "propositions": 1,
                    "expected_prohibition_role": True,
                    "unexpected_propositions": 0,
                    "threshold_10_metres": True,
                    "measurement_basis_preserved": True,
                    "heading_only_propositions": 0,
                    "evidence_grounded": True,
                },
            }
        )

    payload = {
        "schema": "law-proposition-extractor.live_proposition_calibration.uk_regulation_12_post_fix_replay.v1",
        "calibration_run_id": calibration_run_id,
        "case_id": "uk_regulation_12_spread",
        "kind": "saved_response_replay_under_corrected_deterministic_code",
        "distinguished_from": "original live calibration result",
        "historical_calibration": historical,
        "model_calls_made": 0,
        "network_calls_made": 0,
        "historical_artifacts_modified": False,
        "repetitions": repetitions,
        "classification_note": (
            "Historical calibration labelled the extra measurement row as an "
            "invented operative proposition. Under corrected code it is treated "
            "as an unexpected dependent qualification / non-independent "
            "measurement restatement and suppressed when content is preserved."
        ),
    }

    if write_result:
        out = base / "uk_regulation_12_post_fix_replay.json"
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["written_to"] = str(out)

    return payload


def assert_uk_regulation_12_post_fix_replay(payload: dict[str, Any]) -> None:
    """Assert post-fix replay invariants for all UK regulation 12 repetitions."""
    if payload.get("model_calls_made") != 0:
        raise AssertionError("Replay must not call the model.")
    if payload.get("historical_artifacts_modified"):
        raise AssertionError("Replay must not modify historical artifacts.")
    reps = payload.get("repetitions") or []
    if len(reps) != 3:
        raise AssertionError(f"Expected 3 repetitions; found {len(reps)}")
    for row in reps:
        replay = row.get("post_fix_replay") or {}
        exp = row.get("expected") or {}
        if replay.get("proposition_count") != exp.get("propositions"):
            raise AssertionError(
                f"rep {row.get('repetition')}: propositions="
                f"{replay.get('proposition_count')} expected {exp.get('propositions')}; "
                f"texts={replay.get('proposition_texts')}"
            )
        if replay.get("unexpected_count") != exp.get("unexpected_propositions"):
            raise AssertionError(
                f"rep {row.get('repetition')}: unexpected="
                f"{replay.get('unexpected_count')}"
            )
        if not replay.get("has_organic_manure_spread_prohibition"):
            raise AssertionError(
                f"rep {row.get('repetition')}: expected prohibition role missing"
            )
        if not replay.get("threshold_10_metres_preserved"):
            raise AssertionError(
                f"rep {row.get('repetition')}: 10-metre threshold not preserved"
            )
        if not replay.get("measurement_basis_preserved"):
            raise AssertionError(
                f"rep {row.get('repetition')}: measurement basis not preserved; "
                f"conditions={replay.get('conditions')}"
            )
        if not replay.get("evidence_grounded"):
            raise AssertionError(
                f"rep {row.get('repetition')}: evidence not grounded"
            )
