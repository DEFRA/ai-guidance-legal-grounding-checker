"""Re-evaluate saved Article 49a calibration outputs for action fidelity (evaluation-only).

Does not modify historical ``calibration_result.json`` / ``calibration_report.md`` /
raw call artifacts. Writes a separate recheck artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import load_proposition_fidelity_cases
from law_proposition_extractor_pipeline.proposition_fidelity.matching import match_roles_for_case, prop_by_id
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

from .artifacts import read_json
from .evaluate import evaluate_live_propositions
from .paths import call_artifact_name, calls_dir, run_dir


def recheck_article_49a_action_fidelity(
    calibration_run_id: str,
    *,
    root: Path | None = None,
    write_result: bool = True,
    output_name: str = "article_49a_action_fidelity_recheck.json",
) -> dict[str, Any]:
    """Re-score Article 49a P2 action fidelity with the corrected evaluator."""
    base = run_dir(calibration_run_id, root=root)
    if not base.is_dir():
        raise FileNotFoundError(f"Calibration run not found: {base}")

    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    historical_paths = [
        base / "calibration_result.json",
        base / "calibration_report.md",
        base / "calibration_manifest.json",
        *[
            calls_dir(calibration_run_id, root=root) / call_artifact_name("article_49a", rep)
            for rep in (1, 2, 3)
        ],
    ]
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in historical_paths
        if p.is_file()
    }

    repetitions: list[dict[str, Any]] = []
    for rep in (1, 2, 3):
        call_path = calls_dir(calibration_run_id, root=root) / call_artifact_name(
            "article_49a", rep
        )
        call = read_json(call_path)
        props = [
            p for p in (call.get("final_propositions") or []) if isinstance(p, dict)
        ]
        operative = str(call.get("operative_source_excerpt") or "")
        heading = call.get("legislative_heading")
        heading_text = str(heading) if heading else case.heading_text
        opaque = (call.get("article_49a_detail") or {}).get("opaque_roles")
        if not isinstance(opaque, dict) or not opaque:
            raise AssertionError(
                f"rep {rep}: saved article_49a_detail.opaque_roles missing; "
                "cannot recheck action fidelity without role map"
            )
        a49_bundle = {"propositions": props, "opaque_roles": opaque}
        pf = evaluate_live_propositions(
            case,
            props,
            operative_text=operative
            or (
                "Those catches shall not be mixed with any other fishery products."
            ),
            heading_text=heading_text,
            diagnostics=[],
            article_49a_bundle=a49_bundle,
        )
        matches, _ = match_roles_for_case(
            case, props, article_49a_bundle=a49_bundle
        )
        p2_match = next(m for m in matches if m.role == "prohibited-mixing-rule")
        p2_prop = prop_by_id(props, p2_match.proposition_id)
        p2_role = next(r for r in pf.role_results if r.role == "prohibited-mixing-rule")
        action_dim = next(
            d for d in p2_role.dimension_results if d.dimension == "action_fidelity"
        )
        historical_action = None
        for finding in call.get("failure_origins") or []:
            if (
                isinstance(finding, dict)
                and finding.get("dimension") == "action_fidelity"
                and finding.get("role") == "prohibited-mixing-rule"
            ):
                historical_action = {
                    "status": "fail",
                    "likely_origin": finding.get("likely_origin"),
                    "detail": finding.get("detail"),
                }
                break
        if historical_action is None:
            br = call.get("benchmark_result") or {}
            for role in br.get("role_results") or []:
                if role.get("role") != "prohibited-mixing-rule":
                    continue
                for dim in role.get("dimension_results") or []:
                    if dim.get("dimension") == "action_fidelity":
                        historical_action = {
                            "status": dim.get("status"),
                            "detail": dim.get("detail"),
                            "expected": dim.get("expected"),
                            "actual": dim.get("actual"),
                        }
        repetitions.append(
            {
                "repetition": rep,
                "matched_roles": pf.matched_roles,
                "matched_role_count": len(pf.matched_roles),
                "produced_count": len(props),
                "p2": {
                    "proposition_id": p2_match.proposition_id,
                    "proposition_text": (p2_prop or {}).get("proposition_text"),
                    "action": (p2_prop or {}).get("action"),
                    "legal_effect_type": (p2_prop or {}).get("legal_effect_type"),
                    "historical_action_fidelity": historical_action,
                    "recheck_action_fidelity": action_dim.to_dict(),
                },
            }
        )

    after = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in historical_paths
        if p.is_file()
    }
    if before != after:
        raise AssertionError("Historical calibration artifacts were mutated during recheck.")

    payload: dict[str, Any] = {
        "schema": "law-proposition-extractor.live_proposition_calibration.article_49a_action_fidelity_recheck.v1",
        "calibration_run_id": calibration_run_id,
        "case_id": "article_49a",
        "kind": "saved_output_reevaluation_under_corrected_action_fidelity_evaluator",
        "distinguished_from": "original live calibration result",
        "model_calls_made": 0,
        "historical_artifacts_modified": False,
        "expected": {
            "action_fidelity_p2": "pass",
            "predicate": "mix",
            "polarity": "negative",
            "legal_effect": "prohibition",
        },
        "repetitions": repetitions,
    }
    if write_result:
        out = base / output_name
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["written_to"] = str(out)
    return payload
