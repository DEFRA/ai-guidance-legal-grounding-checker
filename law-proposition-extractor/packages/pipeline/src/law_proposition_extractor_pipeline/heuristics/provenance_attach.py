"""Attach provenance and source-effect DecisionExplanation records to a bundle.

Captures/projects facts from stored snapshots and source_legal_effects, then
merges DecisionExplanation rows into the shared decision_explanations artifact.
Does not re-parse manifestation XML or re-run effect parsers.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from law_proposition_extractor_domain import DecisionExplanation

from law_proposition_extractor_pipeline.heuristics.provenance_explanations import (
    build_provenance_decision_explanations,
    collect_manifestation_decision_facts,
)
from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
    build_decision_explanations_artifact,
)
from law_proposition_extractor_pipeline.heuristics.source_effect_explanations import (
    build_source_effect_decision_explanations,
    collect_consumption_decision_facts,
    collect_parse_and_outstanding_facts,
)
from law_proposition_extractor_pipeline.heuristics.structured_list_explanations import (
    merge_decision_explanation_lists,
)
from law_proposition_extractor_pipeline.source_effect_relevance import capture_source_effect_relevance_facts


def _statements_list(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("effective_law_statements")
    if isinstance(raw, dict):
        rows = raw.get("statements") or []
        return [r for r in rows if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


def _propositions_list(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("propositions")
    if isinstance(raw, dict):
        rows = raw.get("propositions") or raw.get("items") or []
        return [r for r in rows if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


def _fragments_list(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("source_fragments")
    if isinstance(raw, dict):
        rows = raw.get("fragments") or raw.get("items") or []
        return [r for r in rows if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


def _snapshots_list(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("source_snapshots")
    if isinstance(raw, dict):
        rows = raw.get("source_snapshots") or raw.get("items") or []
        return [r for r in rows if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


def collect_provenance_and_source_effect_facts(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Collect all provenance/source-effect facts from stored bundle artifacts."""
    snapshots = _snapshots_list(bundle)
    effects_art = bundle.get("source_legal_effects")
    effects_art = effects_art if isinstance(effects_art, Mapping) else None

    facts: list[dict[str, Any]] = []
    facts.extend(collect_manifestation_decision_facts(snapshots))
    facts.extend(
        collect_parse_and_outstanding_facts(
            effects_artifact=effects_art,
            snapshots=snapshots,
        )
    )
    facts.extend(collect_consumption_decision_facts(effects_art))

    if effects_art is not None:
        facts.extend(
            capture_source_effect_relevance_facts(
                statements=_statements_list(bundle),
                propositions=_propositions_list(bundle),
                fragments=_fragments_list(bundle),
                effects=[
                    e for e in (effects_art.get("effects") or []) if isinstance(e, Mapping)
                ],
                effect_links=[
                    lnk
                    for lnk in (effects_art.get("effect_links") or [])
                    if isinstance(lnk, Mapping)
                ],
            )
        )
    return facts


def build_provenance_and_source_effect_explanations(
    facts: Sequence[Mapping[str, Any]],
) -> list[DecisionExplanation]:
    provenance = build_provenance_decision_explanations(facts)
    source_effect = build_source_effect_decision_explanations(facts)
    return merge_decision_explanation_lists(provenance, source_effect)


def attach_provenance_and_source_effect_explanations(bundle: dict[str, Any]) -> None:
    """Append provenance + source-effect explanations to decision_explanations."""
    facts = collect_provenance_and_source_effect_facts(bundle)
    if not facts:
        return
    new_explanations = build_provenance_and_source_effect_explanations(facts)
    if not new_explanations:
        return

    run = bundle.get("run")
    run_id = str(run.get("id") if isinstance(run, dict) else "") or ""

    existing = bundle.get("decision_explanations")
    existing_rows: list[DecisionExplanation] = []
    if isinstance(existing, dict):
        for row in existing.get("decisions") or []:
            if isinstance(row, DecisionExplanation):
                existing_rows.append(row)
            elif isinstance(row, dict):
                try:
                    existing_rows.append(DecisionExplanation.model_validate(row))
                except Exception:
                    continue

    merged = merge_decision_explanation_lists(existing_rows, new_explanations)
    bundle["decision_explanations"] = build_decision_explanations_artifact(
        run_id=run_id or str((existing or {}).get("run_id") if isinstance(existing, dict) else ""),
        decisions=merged,
    )
