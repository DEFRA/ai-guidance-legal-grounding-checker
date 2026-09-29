"""Offline proposition-fidelity benchmark runner (no network, no LLM)."""

from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from typing import Any
from xml.etree import ElementTree

from law_proposition_extractor_domain import Cluster, Proposition, SourceRecord, Topic
from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    run_article_49a_acceptance_pipeline,
)
from law_proposition_extractor_pipeline.dependent_qualification import reconcile_dependent_qualification_rows
from law_proposition_extractor_pipeline.extract import (
    EXTRACTION_PROMPT_VERSION,
    _build_propositions_from_v2_rows,
    _parse_json,
    _parse_model_propositions_container,
    _v2_model_prompt,
    _validate_v2_items,
)
from law_proposition_extractor_pipeline.proposition_normalisation import normalise_extracted_propositions
from law_proposition_extractor_pipeline.source_structure_audit import structural_rows_to_fragments
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root
from law_proposition_extractor_pipeline.sources.adapters import _build_legislation_structural_fragments
from law_proposition_extractor_pipeline.structural_headings import resolve_structural_heading_contexts
from law_proposition_extractor_pipeline.structured_list_decomposition import (
    StructuredListIdentityContext,
    draft_structured_list_leaves,
    merge_structured_leaf_rows,
)

from .dimensions import (
    evaluate_case_level_dimensions,
    evaluate_role_dimensions,
    heading_only_candidate_rejected,
)
from .fixtures import (
    BENCHMARK_VERSION,
    PropositionFidelityCase,
    load_proposition_fidelity_cases,
    validate_manifest_inventory,
)
from .matching import match_roles_for_case, prop_by_id
from .results import (
    PropositionFidelityBenchmarkResult,
    PropositionFidelityCaseResult,
    PropositionFidelityRoleResult,
    accumulate_dimension,
    empty_dimension_totals,
)


def _prop_to_dict(prop: Proposition | dict[str, Any]) -> dict[str, Any]:
    if isinstance(prop, Proposition):
        return prop.model_dump(mode="python")
    return dict(prop)


def _load_fragment_text(case: PropositionFidelityCase) -> tuple[str, list[Any]]:
    if case.fragment_text_override is not None:
        return case.fragment_text_override, []
    xml_text = case.source_path.read_text(encoding="utf-8")
    root = ElementTree.fromstring(xml_text)
    rows, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="https://www.legislation.gov.uk/offline/proposition-fidelity/fixture.xml",
    )
    fragments = structural_rows_to_fragments(rows)
    frag = next((f for f in fragments if f.locator == case.source_locator), None)
    if frag is None:
        # Fallback: longest fragment whose locator starts with the case locator
        candidates = [
            f for f in fragments if str(f.locator).startswith(case.source_locator)
        ]
        frag = max(candidates, key=lambda f: len(f.fragment_text or ""), default=None)
    if frag is None:
        raise LookupError(
            f"{case.case_id}: locator {case.source_locator} not found in "
            f"{case.source_fixture_relative}"
        )
    return str(frag.fragment_text or ""), fragments


def _heading_contexts_for_locator(
    fragments: list[Any], locator: str
) -> list[dict[str, Any]]:
    by_id = {f.id: f for f in fragments}
    frag = next((f for f in fragments if f.locator == locator), None)
    if frag is None:
        return []
    contexts = resolve_structural_heading_contexts(frag, by_id)
    return [
        {
            "kind": c.kind.value if hasattr(c.kind, "value") else str(c.kind),
            "number_label": c.number_label,
            "heading_text": c.heading_text,
            "owner_locator": c.owner_locator,
        }
        for c in contexts
    ]


def _attach_evidence(
    props: list[Proposition], validated_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, prop in enumerate(props):
        data = _prop_to_dict(prop)
        meta = dict(data.get("extraction_debug_meta") or {})
        if idx < len(validated_rows):
            row = validated_rows[idx]
            if row.get("evidence_text") and not meta.get("evidence_quote"):
                meta["evidence_quote"] = str(row.get("evidence_text"))
            if row.get("completeness_status") and not meta.get("completeness_status"):
                meta["completeness_status"] = str(row.get("completeness_status"))
            if row.get("display_label") and not meta.get("display_label"):
                meta["display_label"] = str(row.get("display_label"))
            struct = row.get("_structured_list_meta")
            if isinstance(struct, dict) and struct.get("structured_list_path"):
                meta.setdefault("structured_list_path", struct["structured_list_path"])
            if row.get("structured_list_path"):
                meta.setdefault("structured_list_path", row["structured_list_path"])
        data["extraction_debug_meta"] = meta or None
        out.append(data)
    return out


def run_dry_fragment_case(case: PropositionFidelityCase) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse offline response through production validators + normalisation."""
    diagnostics: list[str] = []
    if case.response is None or case.response_path is None:
        raise ValueError(f"{case.case_id}: missing response fixture")
    raw = case.response_path.read_text(encoding="utf-8")
    # Allow either raw JSON object or {"raw_model_output": "..."} wrapper
    try:
        wrapper = json.loads(raw)
    except json.JSONDecodeError:
        wrapper = None
    if isinstance(wrapper, dict) and "propositions" in wrapper:
        raw_model_output = json.dumps(wrapper, sort_keys=True)
    elif isinstance(wrapper, dict) and "raw_model_output" in wrapper:
        raw_model_output = str(wrapper["raw_model_output"])
    else:
        raw_model_output = raw

    fragment_text, fragments = _load_fragment_text(case)
    heading_contexts = _heading_contexts_for_locator(fragments, case.source_locator)

    # Prompt-v3 structural heading block contract (headed cases).
    if case.heading_present or heading_contexts:
        source = SourceRecord(
            id=f"pf-{case.case_id}",
            title=case.case_id,
            jurisdiction=case.jurisdiction or "UK",
            citation=case.case_id,
            kind="regulation",
            authoritative_text=fragment_text,
            authoritative_locator=case.source_locator,
            metadata={"structural_heading_contexts": heading_contexts},
        )
        prompt = _v2_model_prompt(
            source,
            Topic(id="pf-topic", name="Proposition fidelity"),
            Cluster(id="pf-cluster", topic_id="pf-topic", name="Benchmark"),
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
                op_idx = prompt.index("Operative source text:")
                for ctx in heading_contexts:
                    ht = str(ctx.get("heading_text") or "")
                    if ht and ht in prompt[op_idx:]:
                        diagnostics.append(
                            f"heading leaked into operative prompt block: {ht[:80]}"
                        )
        diagnostics.append(
            f"prompt_version_production={EXTRACTION_PROMPT_VERSION}; "
            f"response_fixture_prompt={case.response.prompt_version}; "
            f"reflects_prompt_v3={case.response.reflects_prompt_v3}"
        )
        if case.heading_text and not heading_only_candidate_rejected(
            case.heading_text, fragment_text
        ):
            diagnostics.append("heading-only fake candidate was NOT rejected")
    else:
        diagnostics.append("unheaded provision — prompt-v3 heading block absent as expected")

    parsed = _parse_json(raw_model_output)
    raw_rows = _parse_model_propositions_container(parsed)
    validated, verrs, issue_records = _validate_v2_items(
        raw_rows, fragment_text, limit=max(8, case.expected_proposition_count + 2)
    )
    if verrs:
        diagnostics.extend(f"validation: {e}" for e in verrs[:8])
    if issue_records:
        diagnostics.append(f"validation_issues={len(issue_records)}")

    # Structured-list merge when drafts exist (production post-processing).
    drafts = draft_structured_list_leaves(fragment_text, case.source_locator)
    if drafts and validated:
        identity = StructuredListIdentityContext(
            source_record_id=f"pf-{case.case_id}",
            source_snapshot_id="snap-pf",
            source_fragment_id=f"frag-{case.case_id}",
        )
        validated, sl_diags, _facts = merge_structured_leaf_rows(
            existing_rows=validated,
            drafts=drafts,
            base_locator=case.source_locator,
            limit=max(8, case.expected_proposition_count + 2),
            identity=identity,
        )
        if sl_diags:
            diagnostics.append(f"structured_list_diags={len(sl_diags)}")

    if validated:
        dq_identity = StructuredListIdentityContext(
            source_record_id=f"pf-{case.case_id}",
            source_snapshot_id="snap-pf",
            source_fragment_id=f"frag-{case.case_id}",
        )
        validated, dq_diags, _dq_facts = reconcile_dependent_qualification_rows(
            validated,
            source_text=fragment_text,
            identity=dq_identity,
        )
        if dq_diags:
            diagnostics.append(f"dependent_qualification_diags={len(dq_diags)}")

    source = SourceRecord(
        id=f"pf-{case.case_id}",
        title=case.case_id,
        jurisdiction=case.jurisdiction or "UK",
        citation=case.case_id,
        kind="regulation",
        authoritative_text=fragment_text,
        authoritative_locator=case.source_locator,
        current_snapshot_id="snap-pf",
        metadata={
            "extraction_fragment_id": f"frag-{case.case_id}",
            "structural_heading_contexts": heading_contexts,
        },
    )
    topic = Topic(id="pf-topic", name="Proposition fidelity")
    cluster = Cluster(id="pf-cluster", topic_id="pf-topic", name="Benchmark")
    props = _build_propositions_from_v2_rows(
        rows=validated,
        source=source,
        topic=topic,
        cluster=cluster,
        limit=max(8, case.expected_proposition_count + 2),
    )
    normalised = normalise_extracted_propositions(
        [Proposition.model_validate(deepcopy(p.model_dump(mode="python"))) for p in props],
        source_by_id={source.id: source},
    )
    return _attach_evidence(normalised, validated), diagnostics


def run_article_49a_case(
    case: PropositionFidelityCase, *, work_dir: Path
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    result = run_article_49a_acceptance_pipeline(work_dir=work_dir, export=True)
    props = [
        p
        for p in (result.bundle.get("propositions") or [])
        if isinstance(p, dict)
        and str(p.get("fragment_locator") or "").startswith("article:49a")
    ]
    diagnostics = [
        "runner=article_49a_pipeline",
        f"opaque_roles={sorted(result.proposition_ids)}",
        "response fixtures: article_49a frontier_responses (prompt v2-shaped; predate prompt v3)",
    ]
    return props, result.bundle, diagnostics


def evaluate_case(
    case: PropositionFidelityCase,
    *,
    work_dir: Path | None = None,
) -> PropositionFidelityCaseResult:
    diagnostics: list[str] = []
    bundle: dict[str, Any] | None = None
    if case.runner == "article_49a_pipeline":
        tmp = work_dir or Path(tempfile.mkdtemp(prefix="pf-article49a-"))
        props, bundle, diag = run_article_49a_case(case, work_dir=tmp)
        diagnostics.extend(diag)
        operative_text = ""
        # Aggregate operative text from article 49a fragments when available
        for frag in bundle.get("source_fragments") or []:
            if isinstance(frag, dict) and str(frag.get("locator") or "").startswith(
                "article:49a"
            ):
                operative_text += "\n" + str(frag.get("fragment_text") or "")
        heading_text = case.heading_text
    else:
        props, diag = run_dry_fragment_case(case)
        diagnostics.extend(diag)
        operative_text, _frags = _load_fragment_text(case)
        heading_text = case.heading_text

    matches, unexpected = match_roles_for_case(
        case, props, article_49a_bundle=bundle
    )
    matched_props = [
        p
        for m in matches
        if m.status == "matched"
        for p in [prop_by_id(props, m.proposition_id)]
        if p is not None
    ]

    role_results: list[PropositionFidelityRoleResult] = []
    for expected in case.gold:
        match = next(m for m in matches if m.role == expected.role)
        prop = prop_by_id(props, match.proposition_id)
        dim_results = evaluate_role_dimensions(
            case=case,
            expected=expected,
            match=match,
            prop=prop,
            operative_text=operative_text,
            heading_text=heading_text,
            all_matched_props=matched_props,
        )
        role_results.append(
            PropositionFidelityRoleResult(
                role=expected.role,
                proposition_id=match.proposition_id,
                status=match.status,  # type: ignore[arg-type]
                dimension_results=dim_results,
                evidence=_debug_evidence(prop),
                notes=match.notes,
                competing_candidates=list(match.competing_candidate_ids),
            )
        )

    case_dims = evaluate_case_level_dimensions(
        case=case,
        matches=matches,
        unexpected=unexpected,
        propositions=props,
        operative_text=operative_text,
        heading_text=heading_text,
    )

    missing_roles = [m.role for m in matches if m.status == "missing"]
    matched_roles = [m.role for m in matches if m.status == "matched"]
    unexpected_payload = [
        {
            "proposition_id": str(p.get("id")),
            "fragment_locator": str(p.get("fragment_locator") or ""),
            "legal_effect_type": str(p.get("legal_effect_type") or ""),
            "proposition_text": str(p.get("proposition_text") or "")[:240],
        }
        for p in unexpected
    ]

    fail_count = sum(
        1
        for r in role_results
        for d in r.dimension_results
        if d.status == "fail"
    ) + sum(1 for d in case_dims if d.status == "fail")
    warn_count = sum(
        1
        for r in role_results
        for d in r.dimension_results
        if d.status == "warning"
    ) + sum(1 for d in case_dims if d.status == "warning")

    if fail_count and case.accepted_limitations:
        case_status: Any = "baseline_limitation"
    elif fail_count:
        case_status = "fail"
    elif warn_count:
        case_status = "warning"
    else:
        case_status = "pass"

    return PropositionFidelityCaseResult(
        case_id=case.case_id,
        structural_pattern=case.structural_pattern,
        expected_roles=[g.role for g in case.gold],
        matched_roles=matched_roles,
        missing_roles=missing_roles,
        unexpected_propositions=unexpected_payload,
        role_results=role_results,
        dimension_results=case_dims,
        diagnostics=diagnostics,
        produced_count=len(props),
        accepted_limitations=list(case.accepted_limitations),
        case_status=case_status,
    )


def _debug_evidence(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""
    meta = prop.get("extraction_debug_meta")
    if isinstance(meta, dict):
        return str(meta.get("evidence_quote") or "")
    return ""


def run_proposition_fidelity_benchmark(
    *,
    root: Path | None = None,
    work_dir: Path | None = None,
) -> PropositionFidelityBenchmarkResult:
    started = perf_counter()
    base = root or judit_root()
    inventory_errors = validate_manifest_inventory(root=base)
    if inventory_errors:
        raise AssertionError(
            "proposition-fidelity manifest invalid:\n- " + "\n- ".join(inventory_errors)
        )

    cases = load_proposition_fidelity_cases(root=base)
    case_results: list[PropositionFidelityCaseResult] = []
    warnings: list[str] = []
    failures: list[str] = []
    dim_totals = empty_dimension_totals()

    tmp_root = work_dir or Path(tempfile.mkdtemp(prefix="pf-bench-"))
    tmp_root.mkdir(parents=True, exist_ok=True)

    for case in cases:
        result = evaluate_case(case, work_dir=tmp_root / case.case_id)
        case_results.append(result)
        for role in result.role_results:
            for dim in role.dimension_results:
                accumulate_dimension(dim_totals, dim)
                if dim.status == "fail":
                    failures.append(
                        f"{result.case_id}/{role.role}/{dim.dimension}: {dim.detail}"
                    )
                elif dim.status == "warning":
                    warnings.append(
                        f"{result.case_id}/{role.role}/{dim.dimension}: {dim.detail}"
                    )
        for dim in result.dimension_results:
            accumulate_dimension(dim_totals, dim)
            if dim.status == "fail":
                failures.append(f"{result.case_id}/case/{dim.dimension}: {dim.detail}")
            elif dim.status == "warning":
                warnings.append(f"{result.case_id}/case/{dim.dimension}: {dim.detail}")

    fully_passing_roles = sum(
        1
        for c in case_results
        for r in c.role_results
        if r.status == "matched"
        and all(d.status in {"pass", "not_applicable"} for d in r.dimension_results)
    )
    warning_roles = sum(
        1
        for c in case_results
        for r in c.role_results
        if any(d.status == "warning" for d in r.dimension_results)
        and not any(d.status == "fail" for d in r.dimension_results)
    )
    failed_roles = sum(
        1
        for c in case_results
        for r in c.role_results
        if r.status == "missing"
        or any(d.status == "fail" for d in r.dimension_results)
    )
    unexpected = sum(len(c.unexpected_propositions) for c in case_results)
    expected_props = sum(len(c.expected_roles) for c in case_results)
    produced_props = sum(c.produced_count for c in case_results)

    totals = {
        "cases": len(case_results),
        "expected_propositions": expected_props,
        "produced_propositions": produced_props,
        "fully_passing_roles": fully_passing_roles,
        "warning_roles": warning_roles,
        "failed_roles": failed_roles,
        "unexpected_propositions": unexpected,
    }
    return PropositionFidelityBenchmarkResult(
        benchmark_version=BENCHMARK_VERSION,
        cases=case_results,
        totals=totals,
        warnings=warnings,
        failures=failures,
        dimension_totals=dim_totals,
        runtime_seconds=round(perf_counter() - started, 3),
    )
