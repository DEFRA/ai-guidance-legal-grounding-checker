"""Structured-list terminal duplicate reconciliation (Prompt 14-BR1)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import Cluster, ReviewStatus, SourceRecord, Topic
from law_proposition_extractor_domain.proposition_classification import classify_extracted_proposition
from law_proposition_extractor_pipeline.proposition_matcher_law_candidates import build_proposition_matcher_law_candidates
from law_proposition_extractor_pipeline.effective_law import build_effective_law_statements
from law_proposition_extractor_pipeline.extract import _build_propositions_from_v2_rows
from law_proposition_extractor_pipeline.fragment_anchor_coverage import check_structured_list_terminal_coverage
from law_proposition_extractor_pipeline.legal_rule_groups import build_legal_rule_groups
from law_proposition_extractor_pipeline.legal_rule_relationships import build_legal_rule_relationships
from law_proposition_extractor_pipeline.structured_list_decomposition import (
    COMPOSITION_BASIS,
    DUPLICATE_SUPPRESSED_DIAGNOSTIC,
    MULTIPLE_DISTINCT_DIAGNOSTIC,
    are_clear_structured_list_duplicates,
    draft_structured_list_leaves,
    merge_structured_leaf_rows,
    select_structured_list_duplicate_winner,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "structured_list_dedupe"
DUP_FIXTURE = FIXTURE_DIR / "article_49a_p2_duplicate_2_a_i.json"
DISTINCT_FIXTURE = FIXTURE_DIR / "distinct_propositions_same_path.json"
ARTICLE_49A_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)


def _topic() -> Topic:
    return Topic(id="topic-fish", name="Fish control")


def _cluster() -> Cluster:
    return Cluster(id="cluster-fish", topic_id="topic-fish", name="Catch segregation")


def _source_from_dup_fixture(payload: dict) -> SourceRecord:
    return SourceRecord(
        id=str(payload["source_record_id"]),
        title="Control regulation",
        jurisdiction="UK",
        citation="EUR 2009/1224",
        kind="regulation",
        authoritative_text=str(payload["fragment_text"]),
        authoritative_locator=str(payload["base_locator"]),
        current_snapshot_id=str(payload["source_snapshot_id"]),
        review_status=ReviewStatus.PROPOSED,
        metadata={"extraction_fragment_id": payload["source_fragment_id"]},
    )


def _rows_from_fixture(payload: dict) -> list[dict]:
    out: list[dict] = []
    for row in payload["frontier_rows"]:
        item = {k: v for k, v in row.items() if k != "row_id"}
        out.append(item)
    return out


def _paths(rows: list[dict]) -> list[str]:
    return [
        str((r.get("_structured_list_meta") or {}).get("structured_list_path") or "")
        for r in rows
    ]


def test_acceptance_duplicate_signals_are_documented() -> None:
    """Concrete signals that establish prop:de4afd… / prop:939e14… as duplicates."""
    payload = json.loads(DUP_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    a_i = next(d for d in drafts if d.path_key == "2-a-i")
    rows = _rows_from_fixture(payload)
    det, llm = rows[0], rows[1]
    ok, basis = are_clear_structured_list_duplicates(det, llm, a_i)
    assert ok is True
    assert basis in {
        "high_proposition_text_overlap",
        "same_terminal_leaf_claim",
        "shared_leaf_evidence_and_claim",
        "proposition_text_containment",
        "identical_normalized_proposition_text",
    }
    # Path alone is necessary but not treated as sufficient without claim overlap.
    assert det["source_locator"] != llm["source_locator"]
    assert "list:2-a-i" in det["source_locator"]
    assert "(a)(i)" in llm["source_locator"]


def test_two_clear_duplicates_yield_one_retained_row() -> None:
    from law_proposition_extractor_pipeline.heuristics.structured_list_explanations import (
        bind_structured_list_decision_facts,
        build_structured_list_decision_explanations,
    )
    from law_proposition_extractor_pipeline.structured_list_decomposition import StructuredListIdentityContext

    payload = json.loads(DUP_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    rows = _rows_from_fixture(payload)
    identity = StructuredListIdentityContext(
        source_record_id=str(payload["source_record_id"]),
        source_snapshot_id=str(payload["source_snapshot_id"]),
        source_fragment_id=str(payload["source_fragment_id"]),
    )
    merged, diags, facts = merge_structured_leaf_rows(
        existing_rows=rows,
        drafts=drafts,
        base_locator=payload["base_locator"],
        limit=10,
        identity=identity,
    )
    assert _paths(merged) == payload["expected_paths"]
    assert len(merged) == 3
    assert any(d["code"] == DUPLICATE_SUPPRESSED_DIAGNOSTIC for d in diags)
    assert merged[0]["source_locator"] == payload["expected_winner_source_locator"]
    dedupe = (merged[0].get("_structured_list_meta") or {}).get("structured_list_dedupe") or {}
    assert dedupe.get("dedupe_reason") == "duplicate_structured_list_terminal"
    assert dedupe.get("structured_list_path") == "2-a-i"

    suppress_facts = [f for f in facts if f.get("fact_kind") == "suppress_duplicate_terminal"]
    assert len(suppress_facts) == 1
    source = _source_from_dup_fixture(payload)
    props = _build_propositions_from_v2_rows(
        rows=merged, source=source, topic=_topic(), cluster=_cluster(), limit=10
    )
    # Map provisional prop ids for binding (opaque remap happens in runner).
    bound = bind_structured_list_decision_facts(suppress_facts, propositions=props)
    explanations = build_structured_list_decision_explanations(bound)
    assert len(explanations) == 1
    expl = explanations[0]
    assert expl.rule_id == "structured_list.suppress_duplicate_terminal"
    assert expl.metadata.get("structured_list_path") == "2-a-i"
    assert expl.metadata.get("duplicate_basis")
    assert expl.metadata.get("winner_selection_factors")
    assert expl.metadata.get("retained_candidate_id")
    assert expl.subject_id == suppress_facts[0]["suppressed_candidate_id"]
    assert expl.metadata.get("retained_proposition_id") == props[0].id
    assert all(
        (p.extraction_debug_meta or {}).get("extraction_candidate_id")
        != suppress_facts[0]["suppressed_candidate_id"]
        for p in props
    )


def test_winner_selection_is_order_independent() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    a_i = next(d for d in drafts if d.path_key == "2-a-i")
    rows = _rows_from_fixture(payload)
    det, llm = rows[0], rows[1]
    w1 = select_structured_list_duplicate_winner(
        [det, llm], a_i, base_locator=payload["base_locator"]
    )
    w2 = select_structured_list_duplicate_winner(
        [llm, det], a_i, base_locator=payload["base_locator"]
    )
    assert w1["source_locator"] == w2["source_locator"] == payload["expected_winner_source_locator"]

    forward, _, _ = merge_structured_leaf_rows(
        existing_rows=rows, drafts=drafts, base_locator=payload["base_locator"], limit=10
    )
    reversed_rows = list(reversed(rows))
    backward, _, _ = merge_structured_leaf_rows(
        existing_rows=reversed_rows,
        drafts=drafts,
        base_locator=payload["base_locator"],
        limit=10,
    )
    assert [r["source_locator"] for r in forward] == [r["source_locator"] for r in backward]
    assert [r["proposition_text"] for r in forward] == [r["proposition_text"] for r in backward]


def _typed_ctx(stmt: dict, *, kind: str) -> list[dict]:
    return [c for c in stmt.get("required_context") or [] if c.get("kind") == kind]


def _ctx_prop_ids(entries: list[dict]) -> list[str]:
    ids: list[str] = []
    for entry in entries:
        for pid in entry.get("proposition_ids") or []:
            if pid not in ids:
                ids.append(str(pid))
    return ids


def test_suppressed_candidate_absent_from_propositions_and_downstream() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    article = json.loads(ARTICLE_49A_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    merged, diags, _facts = merge_structured_leaf_rows(
        existing_rows=_rows_from_fixture(payload),
        drafts=drafts,
        base_locator=payload["base_locator"],
        limit=10,
    )
    assert any(d["code"] == DUPLICATE_SUPPRESSED_DIAGNOSTIC for d in diags)
    suppressed_loc = "article:49a:paragraph:2:(a)(i)"
    assert all(r.get("source_locator") != suppressed_loc for r in merged)

    source = _source_from_dup_fixture(payload)
    p2_built = _build_propositions_from_v2_rows(
        rows=merged, source=source, topic=_topic(), cluster=_cluster(), limit=10
    )
    assert len(p2_built) == 3
    assert all(suppressed_loc not in str(p.fragment_locator or "") for p in p2_built)

    source_id = str(article["source_record_id"])
    snapshot_id = str(article["source_snapshot_id"])
    p2_ids = [
        "prop-demo-49a-p2-pelagic",
        "prop-demo-49a-p2-industrial",
        "prop-demo-49a-p2-small-vessels",
    ]
    prop_rows: list[dict] = []
    for row in article["exported_propositions"]:
        if str(row["source_fragment_id"]) == "frag-demo-49a-p2":
            continue
        if not str(row["id"]).startswith("prop-demo-49a-"):
            continue
        prop_rows.append(
            {
                "id": row["id"],
                "source_record_id": source_id,
                "source_snapshot_id": snapshot_id,
                "source_fragment_id": row["source_fragment_id"],
                "fragment_locator": row["fragment_locator"],
                "proposition_text": row["proposition_text"],
                "legal_effect_type": row["legal_effect_type"],
                "proposition_tier": "substantive_rule",
                "is_compliance_relevant": True,
                "topic_id": "topic-demo",
                "jurisdiction": "UK",
                "legal_subject": "operator",
                "action": "comply",
                "explicit_cross_reference_targets": list(
                    row.get("explicit_cross_reference_targets") or []
                ),
                "source_order": row.get("source_order", 0),
                "extraction_debug_meta": dict(row.get("extraction_debug_meta") or {}),
            }
        )
    for i, prop in enumerate(p2_built):
        meta = dict(prop.extraction_debug_meta or {})
        prop_rows.append(
            {
                "id": p2_ids[i],
                "source_record_id": source_id,
                "source_snapshot_id": snapshot_id,
                "source_fragment_id": "frag-demo-49a-p2",
                # Groups key off paragraph locator, not list leaf suffix.
                "fragment_locator": "article:49a:paragraph:2",
                "proposition_text": prop.proposition_text,
                "legal_effect_type": "derogation",
                "proposition_tier": "substantive_rule",
                "is_compliance_relevant": True,
                "topic_id": "topic-demo",
                "jurisdiction": "UK",
                "legal_subject": "operator",
                "action": "comply",
                "explicit_cross_reference_targets": list(drafts[i].cross_reference_targets),
                "source_order": i,
                "extraction_debug_meta": meta,
            }
        )

    frags = [
        {
            "id": f["id"],
            "source_record_id": source_id,
            "source_snapshot_id": snapshot_id,
            "locator": f["locator"],
            "fragment_text": f["fragment_text"],
            "parent_fragment_id": f.get("parent_fragment_id"),
            "order_index": f.get("order_index"),
            "fragment_type": f.get("fragment_type"),
            "fragment_hash": f"hash-{f['id']}",
        }
        for f in article["fragments"]
        if str(f["locator"]).startswith("article:49a")
    ]
    groups = build_legal_rule_groups(prop_rows, run_id="run-dedupe", source_fragments=frags)
    p2 = next(
        g
        for g in groups["groups"]
        if g["canonical_locator"] == "article:49a:paragraph:2"
    )
    assert p2["member_proposition_ids"] == p2_ids

    rels = build_legal_rule_relationships(
        prop_rows, run_id="run-dedupe", source_fragments=frags, legal_rule_groups=groups
    )
    exception_sources = [
        r["source_id"]
        for r in rels["relationships"]
        if r["relationship_type"] == "exception_to" and r["source_id"] in set(p2_ids)
    ]
    assert sorted(exception_sources) == sorted(p2_ids)

    law = build_effective_law_statements(
        prop_rows,
        run_id="run-dedupe",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=rels,
    )
    by_prop = {
        stmt["source_proposition_ids"][0]: stmt
        for stmt in law["statements"]
        if stmt.get("source_proposition_ids")
    }
    for pid in ("prop-demo-49a-p1-separate", "prop-demo-49a-p1-no-mixing"):
        assert _ctx_prop_ids(_typed_ctx(by_prop[pid], kind="applicable_exception")) == p2_ids
    assert _ctx_prop_ids(
        _typed_ctx(by_prop["prop-demo-49a-p3-monitoring"], kind="trigger_condition")
    ) == p2_ids

    proposition_matcher_bundle = build_proposition_matcher_law_candidates(
        effective_law_statements=law, propositions=prop_rows
    )
    p2_cands = [
        c
        for c in proposition_matcher_bundle["candidates"]
        if any(pid in set(p2_ids) for pid in (c.get("source_proposition_ids") or []))
    ]
    assert len(p2_cands) == 3


def test_paragraph_2_paths_order_derogations_and_xrefs() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    merged, _, _ = merge_structured_leaf_rows(
        existing_rows=_rows_from_fixture(payload),
        drafts=drafts,
        base_locator=payload["base_locator"],
        limit=10,
    )
    assert _paths(merged) == ["2-a-i", "2-a-ii", "2-b"]
    assert [r["source_locator"] for r in merged] == [
        "article:49a:paragraph:2:list:2-a-i",
        "article:49a:paragraph:2:list:2-a-ii",
        "article:49a:paragraph:2:list:2-b",
    ]
    source = _source_from_dup_fixture(payload)
    props = _build_propositions_from_v2_rows(
        rows=merged, source=source, topic=_topic(), cluster=_cluster(), limit=10
    )
    for p in props:
        effect = classify_extracted_proposition(
            proposition_text=p.proposition_text,
            extraction_meta=p.extraction_debug_meta,
            provision_type=str((p.extraction_debug_meta or {}).get("provision_type") or ""),
        )
        assert effect.legal_effect_type.value == "derogation"
        assert "paragraph 1" in " ".join(
            str(x).lower() for x in (drafts[props.index(p)].cross_reference_targets)
        )
    assert "article 14" in " ".join(drafts[2].cross_reference_targets).lower()
    assert "article 14" not in " ".join(drafts[0].cross_reference_targets).lower()
    assert "article 14" not in " ".join(drafts[1].cross_reference_targets).lower()
    assert "article 14" in props[2].proposition_text.lower()
    assert "article 14" not in props[0].proposition_text.lower()
    assert "capelin" in props[1].proposition_text.lower()

    coverage = check_structured_list_terminal_coverage(
        fragment_text=payload["fragment_text"],
        fragment_locator=payload["base_locator"],
        proposition_rows=[p.model_dump(mode="json") for p in props],
    )
    assert coverage["all_covered"] is True
    assert set(coverage["expected_terminals"]) == {"2-a-i", "2-a-ii", "2-b"}
    # Winner keeps canonical components / leaf evidence for traceability.
    winner_meta = props[0].extraction_debug_meta or {}
    assert winner_meta.get("composition_basis") == COMPOSITION_BASIS
    assert winner_meta.get("structured_list_path") == "2-a-i"
    assert winner_meta.get("source_component_locators")


def test_distinct_claims_same_path_preserved_and_diagnosed() -> None:
    payload = json.loads(DISTINCT_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    rows = _rows_from_fixture(payload)
    ok, _basis = are_clear_structured_list_duplicates(rows[0], rows[1], drafts[0])
    assert ok is False
    merged, diags, _facts = merge_structured_leaf_rows(
        existing_rows=rows,
        drafts=drafts,
        base_locator=payload["base_locator"],
        limit=10,
    )
    path_i_rows = [
        r
        for r in merged
        if str((r.get("_structured_list_meta") or {}).get("structured_list_path")) == "1-a-i"
    ]
    assert len(path_i_rows) == 2
    assert any(d["code"] == MULTIPLE_DISTINCT_DIAGNOSTIC for d in diags)
    assert not any(d["code"] == DUPLICATE_SUPPRESSED_DIAGNOSTIC for d in diags)


def test_different_fragments_and_snapshots_not_deduped_across_merge_calls() -> None:
    """Eligibility is per merge invocation (one fragment extraction). Cross-fragment
    candidates never share a merge_structured_leaf_rows call."""
    payload = json.loads(DUP_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    rows = _rows_from_fixture(payload)[:2]
    merged_a, diags_a, _ = merge_structured_leaf_rows(
        existing_rows=rows,
        drafts=drafts,
        base_locator=payload["base_locator"],
        limit=10,
    )
    # Same two candidates, different fragment locator context — still reconciled within
    # that fragment only; we do not merge across prior fragment outputs.
    merged_b, diags_b, _ = merge_structured_leaf_rows(
        existing_rows=rows,
        drafts=drafts,
        base_locator="article:49a:paragraph:2",
        limit=10,
    )
    assert len(merged_a) == len(merged_b) == 3  # fills a-ii and b from drafts
    assert any(d["code"] == DUPLICATE_SUPPRESSED_DIAGNOSTIC for d in diags_a)
    assert any(d["code"] == DUPLICATE_SUPPRESSED_DIAGNOSTIC for d in diags_b)
    # Combining already-retained winners from two snapshots must not re-collapse them
    # when they are non-structured ordinary rows without shared path buckets beyond drafts.
    ordinary = [
        {
            "proposition_text": "Operators shall keep records.",
            "provision_type": "core",
            "source_locator": "article:30:paragraph:1",
            "evidence_text": "Operators shall keep records.",
            "conditions": [],
            "exceptions": [],
            "completeness_status": "complete",
            "confidence": "high",
        }
    ]
    merged_ord, diags_ord, _ = merge_structured_leaf_rows(
        existing_rows=ordinary,
        drafts=drafts,
        base_locator=payload["base_locator"],
        limit=10,
    )
    # Ordinary row retained alongside filled terminals; not treated as structured duplicate.
    assert any(
        "Operators shall keep records" in str(r.get("proposition_text") or "")
        for r in merged_ord
    )
    assert not any(
        d["code"] == DUPLICATE_SUPPRESSED_DIAGNOSTIC
        and "Operators" in str(d.get("suppressed_candidate_id") or "")
        for d in diags_ord
    )


def test_ordinary_non_structured_propositions_unaffected_without_drafts() -> None:
    rows = [
        {
            "proposition_text": "Masters shall keep a fishing logbook.",
            "provision_type": "core",
            "source_locator": "article:14:paragraph:1",
            "evidence_text": "Masters shall keep a fishing logbook.",
            "conditions": [],
            "exceptions": [],
        },
        {
            "proposition_text": "Masters shall keep a fishing logbook.",
            "provision_type": "core",
            "source_locator": "article:14:paragraph:1",
            "evidence_text": "Masters shall keep a fishing logbook.",
            "conditions": [],
            "exceptions": [],
        },
    ]
    merged, diags, _facts = merge_structured_leaf_rows(
        existing_rows=rows, drafts=[], base_locator="article:14:paragraph:1", limit=10
    )
    assert len(merged) == 2
    assert diags == []


def test_output_deterministic_for_duplicate_fixture() -> None:
    payload = json.loads(DUP_FIXTURE.read_text())
    drafts = draft_structured_list_leaves(payload["fragment_text"], payload["base_locator"])
    rows = _rows_from_fixture(payload)
    a, da, _ = merge_structured_leaf_rows(
        existing_rows=rows, drafts=drafts, base_locator=payload["base_locator"], limit=10
    )
    b, db, _ = merge_structured_leaf_rows(
        existing_rows=rows, drafts=drafts, base_locator=payload["base_locator"], limit=10
    )
    assert [r["proposition_text"] for r in a] == [r["proposition_text"] for r in b]
    assert [r["source_locator"] for r in a] == [r["source_locator"] for r in b]
    assert [d["code"] for d in da] == [d["code"] for d in db]
