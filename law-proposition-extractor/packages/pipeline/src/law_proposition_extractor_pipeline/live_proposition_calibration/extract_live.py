"""Live production-path extraction for proposition calibration (evaluation-only)."""

from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any
from unittest.mock import patch

from law_proposition_extractor_domain import Cluster, Proposition, SourceRecord, Topic
from law_proposition_extractor_llm.client import JuditLLMClient
from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    fixture_dir,
    identify_article_49a_propositions,
    load_case,
)
from law_proposition_extractor_pipeline.extract import (
    EXTRACTION_PROMPT_VERSION,
    _parse_json,
    _parse_model_propositions_container,
    _v2_model_prompt,
    extract_propositions_from_source,
)
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.litellm_model_resolver import resolve_litellm_aliases
from law_proposition_extractor_pipeline.proposition_fidelity.dimensions import heading_only_candidate_rejected
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import PropositionFidelityCase
from law_proposition_extractor_pipeline.proposition_fidelity.runner import (
    _attach_evidence,
    _heading_contexts_for_locator,
    _load_fragment_text,
)
from law_proposition_extractor_pipeline.proposition_normalisation import normalise_extracted_propositions
from law_proposition_extractor_pipeline.runner import build_bundle_from_case
from law_proposition_extractor_pipeline.sources import LegislationGovUkAuthorityAdapter, SourceIngestionService
from .recording_client import RecordingJuditLLMClient


@dataclass
class LiveExtractOutcome:
    props: list[dict[str, Any]]
    diagnostics: list[str] = field(default_factory=list)
    raw_responses: list[str] = field(default_factory=list)
    raw_rows: list[dict[str, Any]] = field(default_factory=list)
    validated_rows: list[dict[str, Any]] = field(default_factory=list)
    rejected_rows: list[dict[str, Any]] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    parse_status: str = "ok"
    validation_status: str = "ok"
    raw_response_status: str = "ok"
    json_repair_applied: bool = False
    json_repair_method: str | None = None
    latency_seconds: float = 0.0
    provider_calls: list[dict[str, Any]] = field(default_factory=list)
    provider_retry_count: int = 0
    token_usage: dict[str, Any] | None = None
    model_alias: str | None = None
    resolved_model: str | None = None
    prompt_version: str = EXTRACTION_PROMPT_VERSION
    prompt_text: str | None = None
    operative_text: str = ""
    heading_contexts: list[dict[str, Any]] = field(default_factory=list)
    heading_text: str | None = None
    source_snapshot_id: str | None = None
    source_fragment_ids: list[str] = field(default_factory=list)
    required_locators: list[str] = field(default_factory=list)
    focus_terms: list[str] = field(default_factory=list)
    request_parameters: dict[str, Any] = field(default_factory=dict)
    article_49a_bundle: dict[str, Any] | None = None
    article_49a_detail: dict[str, Any] | None = None
    heading_boundary: dict[str, Any] = field(default_factory=dict)


def _sum_token_usage(calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not calls:
        return None
    prompt = completion = total = 0
    any_usage = False
    for call in calls:
        usage = call.get("token_usage")
        if not isinstance(usage, dict):
            continue
        any_usage = True
        prompt += int(usage.get("prompt_tokens") or 0)
        completion += int(usage.get("completion_tokens") or 0)
        total += int(usage.get("total_tokens") or 0)
    if not any_usage:
        return None
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _inspect_heading_boundary(
    *,
    heading_text: str | None,
    operative_text: str,
    props: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    findings: list[str] = []
    heading_only_prop = False
    heading_only_evidence = False
    heading_expanded = False
    ht = (heading_text or "").strip()
    if not ht:
        return {
            "heading_present": False,
            "heading_only_proposition": False,
            "heading_only_evidence": False,
            "heading_material_expansion": False,
            "findings": ["no heading on case"],
        }
    op_norm = " ".join(operative_text.lower().split())
    ht_norm = " ".join(ht.lower().split())
    for prop in props:
        text = str(prop.get("proposition_text") or "")
        meta = prop.get("extraction_debug_meta") if isinstance(prop.get("extraction_debug_meta"), dict) else {}
        evidence = str(meta.get("evidence_quote") or "")
        blob = f"{text} {evidence}".lower()
        if ht_norm and ht_norm in " ".join(text.lower().split()) and len(text) < len(ht) + 40:
            if ht_norm not in op_norm or text.strip().lower() == ht.lower():
                heading_only_prop = True
                findings.append(f"heading-only proposition candidate: {text[:120]}")
        if evidence and ht_norm and ht_norm in " ".join(evidence.lower().split()):
            if ht_norm not in op_norm or evidence.strip().lower() == ht.lower():
                heading_only_evidence = True
                findings.append(f"heading-only evidence: {evidence[:120]}")
        # Material expansion: claim content that appears only in heading, not operative.
        for token in ht.split():
            tok = token.lower().strip(".,;:")
            if len(tok) < 5:
                continue
            if tok in blob and tok not in op_norm:
                heading_expanded = True
                findings.append(f"heading-only token leaked into proposition: {tok}")
                break
    # Fake heading-only candidate must be rejectable by production helper.
    if not heading_only_candidate_rejected(ht, operative_text):
        findings.append("heading_only_candidate_rejected helper did not reject fake heading candidate")
    for row in raw_rows:
        ev = str(row.get("evidence_text") or "")
        if ht and ev.strip() == ht:
            heading_only_evidence = True
            findings.append("raw row evidence equals heading text")
    return {
        "heading_present": True,
        "heading_text": ht,
        "heading_only_proposition": heading_only_prop,
        "heading_only_evidence": heading_only_evidence,
        "heading_material_expansion": heading_expanded,
        "findings": findings,
    }


def resolve_model_provenance(client: JuditLLMClient | RecordingJuditLLMClient) -> dict[str, Any]:
    settings = client.settings
    alias = settings.frontier_extract_model
    resolved = None
    try:
        resolution = resolve_litellm_aliases(llm_settings=settings, try_proxy=False)
        resolved = resolution.alias_to_provider.get(alias)
    except Exception as exc:  # noqa: BLE001 — provenance best-effort
        resolved = f"unresolved:{exc}"
    return {
        "configured_model_alias": alias,
        "resolved_provider_model": resolved,
        "temperature": 0.0,
        "seed": None,
        "seed_note": "production extraction does not supply a seed",
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "prompt_template_identifier": "_v2_model_prompt / EXTRACTION_PROMPT_VERSION=v3",
        "system_prompt": "You extract legal propositions as strict JSON only.",
        "llm_base_url_redacted": True,
    }


def run_live_dry_fragment(
    case: PropositionFidelityCase,
    *,
    llm_client: RecordingJuditLLMClient,
) -> LiveExtractOutcome:
    diagnostics: list[str] = []
    t0 = perf_counter()
    fragment_text, fragments = _load_fragment_text(case)
    heading_contexts = _heading_contexts_for_locator(fragments, case.source_locator)
    source = SourceRecord(
        id=f"live-pf-{case.case_id}",
        title=case.case_id,
        jurisdiction=case.jurisdiction or "UK",
        citation=case.case_id,
        kind="regulation",
        authoritative_text=fragment_text,
        authoritative_locator=case.source_locator,
        current_snapshot_id=f"snap-live-{case.case_id}",
        metadata={
            "extraction_fragment_id": f"frag-live-{case.case_id}",
            "structural_heading_contexts": heading_contexts,
        },
    )
    topic = Topic(id="live-pf-topic", name="Live proposition calibration")
    cluster = Cluster(id="live-pf-cluster", topic_id="live-pf-topic", name="Calibration")
    prompt = _v2_model_prompt(
        source,
        topic,
        cluster,
        extraction_mode="frontier",
        prompt_source_text=fragment_text,
        fragment_locator_hint=case.source_locator,
        structural_heading_contexts=heading_contexts,
    )
    if heading_contexts:
        if "Structural legislative context" not in prompt:
            diagnostics.append("prompt missing Structural legislative context block")
        if "Operative source text:" not in prompt:
            diagnostics.append("prompt missing Operative source text marker")
    else:
        diagnostics.append("unheaded provision — prompt-v3 heading block absent as expected")

    capture: dict[str, Any] = {}
    outcome = extract_propositions_from_source(
        source,
        topic,
        cluster,
        llm_client=llm_client,  # type: ignore[arg-type]
        limit=max(8, case.expected_proposition_count + 2),
        extraction_mode="frontier",
        extraction_fallback="fail_closed",
        prompt_version=EXTRACTION_PROMPT_VERSION,
        workbench_capture=capture,
    )
    raw_outputs = [str(x) for x in (capture.get("raw_model_outputs") or []) if str(x).strip()]
    if not raw_outputs and llm_client.calls:
        raw_outputs = [c.raw_response for c in llm_client.calls if c.raw_response]

    parse_status = "ok"
    validation_status = "ok"
    raw_response_status = "ok"
    raw_rows: list[dict[str, Any]] = []
    validated = list(capture.get("validated_rows") or [])
    validation_errors = list(outcome.validation_errors or [])
    json_repair_applied = False
    json_repair_method = None

    if not raw_outputs:
        raw_response_status = "empty"
        parse_status = "missing"
    else:
        for raw in raw_outputs:
            parsed = _parse_json(raw)
            if parsed is None:
                parse_status = "failed"
                continue
            try:
                rows = _parse_model_propositions_container(parsed)
                raw_rows.extend(rows)
            except Exception as exc:  # noqa: BLE001
                parse_status = "failed"
                diagnostics.append(f"parse_container_error: {exc}")
        for trace in outcome.extraction_llm_call_traces or []:
            if isinstance(trace, dict) and trace.get("json_repair_applied"):
                json_repair_applied = True
                json_repair_method = str(trace.get("json_repair_method") or "")

    if validation_errors:
        validation_status = "issues"
    if outcome.failed_closed:
        validation_status = "failed_closed"
        diagnostics.append(f"failed_closed: {outcome.failure_reason}")

    normalised = normalise_extracted_propositions(
        [
            Proposition.model_validate(deepcopy(p.model_dump(mode="python")))
            for p in outcome.propositions
        ],
        source_by_id={source.id: source},
    )
    props = _attach_evidence(normalised, validated)

    provider_calls = [c.to_dict() for c in llm_client.calls]
    heading_boundary = _inspect_heading_boundary(
        heading_text=case.heading_text,
        operative_text=fragment_text,
        props=props,
        raw_rows=raw_rows or validated,
    )

    return LiveExtractOutcome(
        props=props,
        diagnostics=diagnostics,
        raw_responses=raw_outputs,
        raw_rows=raw_rows,
        validated_rows=validated,
        rejected_rows=[],
        validation_errors=validation_errors,
        parse_status=parse_status,
        validation_status=validation_status,
        raw_response_status=raw_response_status,
        json_repair_applied=json_repair_applied,
        json_repair_method=json_repair_method,
        latency_seconds=round(perf_counter() - t0, 3),
        provider_calls=provider_calls,
        provider_retry_count=sum(1 for c in llm_client.calls if c.is_retry),
        token_usage=_sum_token_usage(provider_calls),
        model_alias=outcome.model_alias or llm_client.settings.frontier_extract_model,
        resolved_model=next(
            (c.resolved_model for c in llm_client.calls if c.resolved_model), None
        ),
        prompt_version=EXTRACTION_PROMPT_VERSION,
        prompt_text=prompt,
        operative_text=fragment_text,
        heading_contexts=heading_contexts,
        heading_text=case.heading_text,
        source_snapshot_id=source.current_snapshot_id,
        source_fragment_ids=[str(source.metadata.get("extraction_fragment_id"))],
        required_locators=[case.source_locator],
        focus_terms=[],
        request_parameters={
            "temperature": 0.0,
            "seed": None,
            "extraction_mode": "frontier",
            "extraction_fallback": "fail_closed",
            "prompt_version": EXTRACTION_PROMPT_VERSION,
        },
        heading_boundary=heading_boundary,
    )


def run_live_article_49a(
    case: PropositionFidelityCase,
    *,
    llm_client: RecordingJuditLLMClient,
    work_dir: Path | None = None,
) -> LiveExtractOutcome:
    """Run production Article 49a pipeline with a live frontier client (offline XML)."""
    diagnostics: list[str] = ["runner=article_49a_live_pipeline"]
    t0 = perf_counter()
    base = fixture_dir()
    case_data = load_case(base)
    xml = (base / "source.xml").read_text(encoding="utf-8")
    tmp = work_dir or Path(tempfile.mkdtemp(prefix="live-a49a-"))
    tmp.mkdir(parents=True, exist_ok=True)

    def fake_fetch(url: str) -> tuple[str, dict[str, object]]:
        return xml, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml.encode("utf-8")),
            "fetched_url": url,
        }

    def make_service(cache_dir: Path | str) -> SourceIngestionService:
        adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
        return SourceIngestionService(
            cache_dir=cache_dir,
            adapters={"legislation_gov_uk": adapter},
        )

    source_cache = tmp / "source-cache"
    derived_cache = tmp / "derived-cache"
    export_dir = tmp / "export"

    # Clear prior calls for this repetition window.
    prior_call_count = len(llm_client.calls)

    with (
        patch("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: llm_client),
        patch("law_proposition_extractor_pipeline.runner.SourceIngestionService", make_service),
        patch("law_proposition_extractor_pipeline.runner.preflight_llm_extraction", lambda *_a, **_k: None),
    ):
        bundle = build_bundle_from_case(
            case_data=case_data,
            use_llm=True,
            extraction_mode="frontier",
            extraction_fallback="fail_closed",
            divergence_reasoning="none",
            source_cache_dir=str(source_cache),
            derived_cache_dir=str(derived_cache),
        )

    export_dir.mkdir(parents=True, exist_ok=True)
    export_bundle(bundle=bundle, output_dir=str(export_dir))
    for name, key in (
        ("legal_rule_groups.json", "legal_rule_groups"),
        ("legal_rule_relationships.json", "legal_rule_relationships"),
        ("effective_law_statements.json", "effective_law_statements"),
        ("source_fragments.json", "source_fragments"),
        ("propositions.json", "propositions"),
        ("source_snapshots.json", "source_snapshots"),
    ):
        path = export_dir / name
        if path.is_file():
            bundle[key] = json.loads(path.read_text(encoding="utf-8"))

    props = [
        p
        for p in (bundle.get("propositions") or [])
        if isinstance(p, dict)
        and str(p.get("fragment_locator") or "").startswith("article:49a")
    ]
    operative_parts: list[str] = []
    fragment_ids: list[str] = []
    for frag in bundle.get("source_fragments") or []:
        if isinstance(frag, dict) and str(frag.get("locator") or "").startswith("article:49a"):
            operative_parts.append(str(frag.get("fragment_text") or ""))
            if frag.get("id"):
                fragment_ids.append(str(frag["id"]))
    operative_text = "\n".join(operative_parts)

    new_calls = [c.to_dict() for c in llm_client.calls[prior_call_count:]]
    raw_responses = [c["raw_response"] for c in new_calls if c.get("raw_response")]
    raw_rows: list[dict[str, Any]] = []
    parse_status = "ok"
    for raw in raw_responses:
        parsed = _parse_json(raw)
        if parsed is None:
            parse_status = "failed"
            continue
        try:
            raw_rows.extend(_parse_model_propositions_container(parsed))
        except Exception as exc:  # noqa: BLE001
            parse_status = "failed"
            diagnostics.append(f"parse_container_error: {exc}")

    roles: dict[str, str] = {}
    try:
        roles = identify_article_49a_propositions(bundle)
        diagnostics.append(f"opaque_roles={sorted(roles)}")
    except AssertionError as exc:
        diagnostics.append(f"identify_article_49a_propositions_failed: {exc}")

    # Downstream invariants
    groups = bundle.get("legal_rule_groups") or {}
    group_rows = groups.get("groups") if isinstance(groups, dict) else groups
    if not isinstance(group_rows, list):
        group_rows = []
    rels_raw = bundle.get("legal_rule_relationships") or {}
    rel_rows = rels_raw.get("relationships") if isinstance(rels_raw, dict) else rels_raw
    if not isinstance(rel_rows, list):
        rel_rows = []

    def _group_member_ids(g: dict[str, Any]) -> set[str]:
        members = g.get("member_proposition_ids") or g.get("proposition_ids") or []
        return {str(x) for x in members}

    p1_group_ok = False
    p2_group_ok = False
    if roles:
        p1p2 = {roles.get("P1"), roles.get("P2")} - {None}
        e123 = {roles.get("E1"), roles.get("E2"), roles.get("E3")} - {None}
        for g in group_rows:
            if not isinstance(g, dict):
                continue
            members = _group_member_ids(g)
            if p1p2 and p1p2 <= members:
                p1_group_ok = True
            if e123 and e123 <= members:
                p2_group_ok = True

    exception_to = sum(
        1
        for r in rel_rows
        if isinstance(r, dict) and str(r.get("relationship_type") or "") == "exception_to"
    )
    triggered_by = sum(
        1
        for r in rel_rows
        if isinstance(r, dict) and str(r.get("relationship_type") or "") == "triggered_by"
    )

    rows_per_para: dict[str, int] = {}
    structured_path_rows = 0
    for row in raw_rows:
        loc = str(row.get("fragment_locator") or row.get("locator") or "")
        key = loc or "unknown"
        rows_per_para[key] = rows_per_para.get(key, 0) + 1
        path = row.get("structured_list_path")
        if path:
            structured_path_rows += 1
    for prop in props:
        loc = str(prop.get("fragment_locator") or "")
        meta = prop.get("extraction_debug_meta") if isinstance(prop.get("extraction_debug_meta"), dict) else {}
        if meta.get("structured_list_path"):
            structured_path_rows += 0  # already counted from raw when present
        rows_per_para.setdefault(loc, 0)

    article_detail = {
        "model_proposed_row_count": len(raw_rows),
        "rows_per_paragraph": rows_per_para,
        "rows_with_structured_list_paths": structured_path_rows,
        "final_proposition_count": len(props),
        "opaque_roles": roles,
        "paragraph_1_group_ok": p1_group_ok,
        "paragraph_2_group_ok": p2_group_ok,
        "exception_to_count": exception_to,
        "triggered_by_count": triggered_by,
        "expected_final": {
            "propositions": 6,
            "roles": ["P1", "P2", "E1", "E2", "E3", "P3"],
            "exception_to": 3,
            "triggered_by": 1,
        },
    }

    snapshots = bundle.get("source_snapshots") or []
    snapshot_id = None
    if isinstance(snapshots, list) and snapshots:
        snapshot_id = str(snapshots[0].get("id") or "") or None

    heading_boundary = _inspect_heading_boundary(
        heading_text=case.heading_text,
        operative_text=operative_text,
        props=props,
        raw_rows=raw_rows,
    )
    required = list(
        (case_data.get("extraction") or {}).get("required_fragment_locators") or []
    )
    focus = list((case_data.get("extraction") or {}).get("focus_terms") or [])

    raw_response_status = "ok" if raw_responses else "empty"
    validation_status = "ok"
    if any(c.get("error") for c in new_calls):
        validation_status = "provider_error"
        raw_response_status = "error"

    return LiveExtractOutcome(
        props=props,
        diagnostics=diagnostics,
        raw_responses=raw_responses,
        raw_rows=raw_rows,
        validated_rows=raw_rows,
        rejected_rows=[],
        validation_errors=[],
        parse_status=parse_status,
        validation_status=validation_status,
        raw_response_status=raw_response_status,
        latency_seconds=round(perf_counter() - t0, 3),
        provider_calls=new_calls,
        provider_retry_count=sum(1 for c in new_calls if c.get("is_retry")),
        token_usage=_sum_token_usage(new_calls),
        model_alias=llm_client.settings.frontier_extract_model,
        resolved_model=next(
            (c.get("resolved_model") for c in new_calls if c.get("resolved_model")), None
        ),
        prompt_version=EXTRACTION_PROMPT_VERSION,
        prompt_text=None,
        operative_text=operative_text,
        heading_contexts=[],
        heading_text=case.heading_text,
        source_snapshot_id=snapshot_id,
        source_fragment_ids=fragment_ids,
        required_locators=required,
        focus_terms=focus,
        request_parameters={
            "temperature": 0.0,
            "seed": None,
            "extraction_mode": "frontier",
            "extraction_fallback": "fail_closed",
            "prompt_version": EXTRACTION_PROMPT_VERSION,
            "required_fragment_locators": required,
            "focus_terms": focus,
        },
        article_49a_bundle=bundle,
        article_49a_detail=article_detail,
        heading_boundary=heading_boundary,
    )
