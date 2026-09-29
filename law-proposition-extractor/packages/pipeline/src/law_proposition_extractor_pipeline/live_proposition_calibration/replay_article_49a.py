"""Offline replay of saved Article 49a live responses through deterministic stages.

Re-runs the production Article 49a pipeline using preserved raw model responses
from a live calibration run. Does not call the model or mutate historical
calibration artifacts. Writes a separate ``post_fix_replay.json``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from law_proposition_extractor_llm.client import TextCompletionResult

from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    fixture_dir,
    identify_article_49a_propositions,
    load_case,
)
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.runner import build_bundle_from_case
from law_proposition_extractor_pipeline.sources import LegislationGovUkAuthorityAdapter, SourceIngestionService

from .artifacts import read_json
from .paths import call_artifact_name, calls_dir, run_dir


def _responses_from_call(call: dict[str, Any]) -> dict[str, str]:
    """Map fragment-locator hint → raw response body from a saved call artifact."""
    out: dict[str, str] = {}
    for row in call.get("provider_calls") or []:
        if not isinstance(row, dict):
            continue
        locator = str(row.get("fragment_locator_hint") or "").strip()
        body = row.get("raw_response")
        if not locator or not isinstance(body, str) or not body.strip():
            continue
        out[locator] = body
    return out


def _summarize_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    roles = identify_article_49a_propositions(bundle)
    props = [
        p
        for p in (bundle.get("propositions") or [])
        if isinstance(p, dict)
        and str(p.get("fragment_locator") or "").startswith("article:49a")
    ]
    groups = bundle.get("legal_rule_groups") or {}
    group_rows = groups.get("groups") if isinstance(groups, dict) else groups
    if not isinstance(group_rows, list):
        group_rows = []
    rels_raw = bundle.get("legal_rule_relationships") or {}
    rel_rows = rels_raw.get("relationships") if isinstance(rels_raw, dict) else rels_raw
    if not isinstance(rel_rows, list):
        rel_rows = []

    def _members(g: dict[str, Any]) -> set[str]:
        return {str(x) for x in (g.get("member_proposition_ids") or g.get("proposition_ids") or [])}

    p1_size = 0
    p2_size = 0
    if roles:
        p1p2 = {roles.get("P1"), roles.get("P2")} - {None}
        e123 = {roles.get("E1"), roles.get("E2"), roles.get("E3")} - {None}
        for g in group_rows:
            if not isinstance(g, dict):
                continue
            members = _members(g)
            if p1p2 and p1p2 <= members:
                p1_size = len(members)
            if e123 and e123 <= members:
                p2_size = len(members)

    exception_to = sum(
        1
        for r in rel_rows
        if isinstance(r, dict) and str(r.get("relationship_type") or "") == "exception_to"
    )
    triggered_by = [
        r
        for r in rel_rows
        if isinstance(r, dict) and str(r.get("relationship_type") or "") == "triggered_by"
    ]

    p3_id = roles.get("P3")
    trigger_conditions: list[str] = []
    eff = bundle.get("effective_law_statements") or {}
    statements = eff.get("statements") if isinstance(eff, dict) else eff
    if isinstance(statements, list) and p3_id:
        for stmt in statements:
            if not isinstance(stmt, dict):
                continue
            source_ids = [
                str(x)
                for x in (stmt.get("source_proposition_ids") or [])
                if str(x)
            ]
            if p3_id not in source_ids:
                continue
            for entry in stmt.get("required_context") or []:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("kind") or "") != "trigger_condition":
                    continue
                if str(entry.get("relationship_type") or "") not in {"triggered_by", ""}:
                    continue
                for tid in entry.get("proposition_ids") or []:
                    if str(tid):
                        trigger_conditions.append(str(tid))

    p3_prop = next((p for p in props if str(p.get("id")) == p3_id), None)
    operative_parts: list[str] = []
    for frag in bundle.get("source_fragments") or []:
        if isinstance(frag, dict) and str(frag.get("locator") or "").startswith(
            "article:49a"
        ):
            text = str(frag.get("fragment_text") or "")
            if text.strip():
                operative_parts.append(text)
    return {
        "proposition_count": len(props),
        "propositions": props,
        "opaque_roles": roles,
        "operative_text": "\n".join(operative_parts),
        "paragraph_1_group_size": p1_size,
        "paragraph_2_group_size": p2_size,
        "exception_to_count": exception_to,
        "triggered_by_count": len(triggered_by),
        "triggered_by": triggered_by,
        "p3_proposition_text": (p3_prop or {}).get("proposition_text"),
        "p3_trigger_condition_proposition_ids": sorted(set(trigger_conditions)),
    }


def replay_article_49a_saved_call(
    call: dict[str, Any],
    *,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Replay one saved Article 49a call through the production pipeline (no LLM)."""
    responses = _responses_from_call(call)
    if len(responses) < 3:
        raise AssertionError(
            f"Expected ≥3 fragment responses in saved call; found {sorted(responses)}"
        )

    base = fixture_dir()
    case_data = load_case(base)
    xml = (base / "source.xml").read_text(encoding="utf-8")
    tmp = work_dir or Path(tempfile.mkdtemp(prefix="a49a-replay-"))
    tmp.mkdir(parents=True, exist_ok=True)

    def fake_fetch(url: str) -> tuple[str, dict[str, object]]:
        return xml, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml.encode("utf-8")),
            "fetched_url": url,
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
            self.calls: list[dict[str, Any]] = []

        def complete_text(self, *, prompt: str, model: str, **kwargs: object) -> str:
            return self.complete_text_result(prompt=prompt, model=model, **kwargs).content

        def complete_text_result(
            self, *, prompt: str, model: str, **kwargs: object
        ) -> TextCompletionResult:
            _ = (model, kwargs)
            for locator, body in responses.items():
                needle = f"Fragment locator (traceability): {locator}"
                if needle in prompt:
                    self.calls.append({"locator": locator, "network": False})
                    return TextCompletionResult(content=body, finish_reason="stop")
            raise AssertionError(
                "Saved live response not found for prompt fragment locator."
            )

    def make_service(cache_dir: Path | str) -> SourceIngestionService:
        adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
        return SourceIngestionService(
            cache_dir=cache_dir,
            adapters={"legislation_gov_uk": adapter},
        )

    llm = _ReplayLLM()
    with (
        patch("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: llm),
        patch("law_proposition_extractor_pipeline.runner.SourceIngestionService", make_service),
        patch("law_proposition_extractor_pipeline.runner.preflight_llm_extraction", lambda *_a, **_k: None),
    ):
        bundle = build_bundle_from_case(
            case_data=case_data,
            use_llm=True,
            extraction_mode="frontier",
            extraction_fallback="fail_closed",
            divergence_reasoning="none",
            source_cache_dir=str(tmp / "source-cache"),
            derived_cache_dir=str(tmp / "derived-cache"),
        )

    export_dir = tmp / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_bundle(bundle=bundle, output_dir=str(export_dir))
    for name, key in (
        ("legal_rule_groups.json", "legal_rule_groups"),
        ("legal_rule_relationships.json", "legal_rule_relationships"),
        ("effective_law_statements.json", "effective_law_statements"),
        ("source_fragments.json", "source_fragments"),
        ("propositions.json", "propositions"),
        ("decision_explanations.json", "decision_explanations"),
    ):
        path = export_dir / name
        if path.is_file():
            bundle[key] = json.loads(path.read_text(encoding="utf-8"))

    summary = _summarize_bundle(bundle)
    summary["model_calls_made"] = 0
    summary["replay_llm_lookups"] = len(llm.calls)
    summary["saved_response_locators"] = sorted(responses)
    summary["raw_responses_mutated"] = False
    return summary


def replay_article_49a_calibration_run(
    calibration_run_id: str,
    *,
    root: Path | None = None,
    write_result: bool = True,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Replay all three Article 49a repetitions from a saved calibration run."""
    base = run_dir(calibration_run_id, root=root)
    if not base.is_dir():
        raise FileNotFoundError(f"Calibration run not found: {base}")

    # Capture historical triggered_by counts without modifying artifacts.
    historical: dict[str, Any] = {}
    result_path = base / "calibration_result.json"
    if result_path.is_file():
        historical_result = read_json(result_path)
        historical = {
            "calibration_run_id": historical_result.get("calibration_run_id"),
            "critical_failures": historical_result.get("critical_failures"),
            "note": "historical live calibration result (immutable)",
        }

    repetitions: list[dict[str, Any]] = []
    for rep in (1, 2, 3):
        call_path = calls_dir(calibration_run_id, root=root) / call_artifact_name(
            "article_49a", rep
        )
        call = read_json(call_path)
        # Fingerprint raw responses to prove immutability after replay.
        raw_fingerprint = [
            {
                "call_index": row.get("call_index"),
                "fragment_locator_hint": row.get("fragment_locator_hint"),
                "raw_response_sha256": __import__("hashlib")
                .sha256(str(row.get("raw_response") or "").encode("utf-8"))
                .hexdigest(),
            }
            for row in (call.get("provider_calls") or [])
            if isinstance(row, dict)
        ]
        before = json.dumps(call.get("provider_calls"), sort_keys=True)
        summary = replay_article_49a_saved_call(
            call,
            work_dir=(work_dir / f"rep-{rep}") if work_dir else None,
        )
        after_call = read_json(call_path)
        after = json.dumps(after_call.get("provider_calls"), sort_keys=True)
        if before != after:
            raise AssertionError("Historical call artifact was mutated during replay.")

        original_detail = call.get("article_49a_detail") or {}
        repetitions.append(
            {
                "repetition": rep,
                "original_live_calibration": {
                    "triggered_by_count": original_detail.get("triggered_by_count"),
                    "exception_to_count": original_detail.get("exception_to_count"),
                    "final_proposition_count": original_detail.get(
                        "final_proposition_count"
                    ),
                },
                "post_fix_replay": summary,
                "raw_response_fingerprints": raw_fingerprint,
                "expected": {
                    "propositions": 6,
                    "paragraph_1_group_size": 2,
                    "paragraph_2_group_size": 3,
                    "exception_to": 3,
                    "triggered_by": 1,
                    "p3_trigger_conditions": 3,
                },
            }
        )

    payload = {
        "schema": "law-proposition-extractor.live_proposition_calibration.post_fix_replay.v1",
        "calibration_run_id": calibration_run_id,
        "case_id": "article_49a",
        "kind": "saved_response_replay_under_corrected_deterministic_code",
        "distinguished_from": "original live calibration result",
        "historical_calibration": historical,
        "model_calls_made": 0,
        "network_calls_made": 0,
        "historical_artifacts_modified": False,
        "repetitions": repetitions,
    }

    if write_result:
        out = base / "post_fix_replay.json"
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["written_to"] = str(out)

    return payload


def assert_article_49a_post_fix_replay(payload: dict[str, Any]) -> None:
    """Assert post-fix replay invariants for all Article 49a repetitions."""
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
                f"{replay.get('proposition_count')} expected {exp.get('propositions')}"
            )
        if replay.get("paragraph_1_group_size") != exp.get("paragraph_1_group_size"):
            raise AssertionError(
                f"rep {row.get('repetition')}: paragraph_1_group_size="
                f"{replay.get('paragraph_1_group_size')}"
            )
        if replay.get("paragraph_2_group_size") != exp.get("paragraph_2_group_size"):
            raise AssertionError(
                f"rep {row.get('repetition')}: paragraph_2_group_size="
                f"{replay.get('paragraph_2_group_size')}"
            )
        if replay.get("exception_to_count") != exp.get("exception_to"):
            raise AssertionError(
                f"rep {row.get('repetition')}: exception_to="
                f"{replay.get('exception_to_count')}"
            )
        if replay.get("triggered_by_count") != exp.get("triggered_by"):
            raise AssertionError(
                f"rep {row.get('repetition')}: triggered_by="
                f"{replay.get('triggered_by_count')}"
            )
        triggers = replay.get("p3_trigger_condition_proposition_ids") or []
        if len(triggers) != exp.get("p3_trigger_conditions"):
            raise AssertionError(
                f"rep {row.get('repetition')}: P3 trigger conditions="
                f"{len(triggers)} expected {exp.get('p3_trigger_conditions')}"
            )
