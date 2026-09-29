"""Structured list extraction (Article 109-style); heuristic, no LLM."""

import copy

from law_proposition_extractor_domain import Cluster, ReviewStatus, SourceRecord, Topic
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.extract import (
    STRUCTURED_LIST_RULE_ID,
    STRUCTURED_NOTE_PREFIX,
    extract_propositions,
    parse_structured_extraction_notes,
)
from law_proposition_extractor_pipeline.linting import lint_bundle
from law_proposition_extractor_pipeline.runner import _build_proposition_extraction_traces
from law_proposition_extractor_pipeline.scope_linking import build_scope_artifacts_for_run


def _topic() -> Topic:
    return Topic(id="topic-db", name="Database duties")


def _cluster() -> Cluster:
    return Cluster(id="cluster-db", topic_id="topic-db", name="Core duties")


def test_structured_list_locator_label_readable() -> None:
    from law_proposition_extractor_pipeline.runner import _format_structured_list_locator_for_label as fmt

    assert fmt("article:109:list:1-d-i") == "Art 109 §1(d)(i)"
    assert fmt("article:109:list:1-a-ii") == "Art 109 §1(a)(ii)"


def test_round_robin_includes_art109_1d_equine_when_limit_four() -> None:
    """Pilot-style multi-roman lists: without round-robin, limit=4 is only (a)(i)…(a)(iii)."""
    text = """Article 109
1.
The Member States shall establish and maintain a computer database for the recording of at least:
(a)
the following information related to kept animals of the bovine species:
(i)
their individual identification as provided for in point (a) of Article 112;
(ii)
the establishments keeping them;
(iii)
their movements into and from those establishments;
(b)
the following information related to kept animals of the ovine and caprine species:
(i)
information on their identification;
(ii)
the establishments keeping them;
(iii)
their movements into and from those establishments;
(c)
the following information related to kept animals of the porcine species:
(i)
information on their identification as provided for in Article 115;
(ii)
the establishments keeping them;
(iii)
their movements into and from those establishments;
(d)
the following information related to kept animals of the equine species:
(i)
their unique code as provided for in Article 114;
(ii)
other identification details.
"""
    source = SourceRecord(
        id="pilot-eu-2016-429-art109",
        title="EU 2016/429 Art 109",
        jurisdiction="EU",
        citation="CELEX 32016R0429",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator="article:109",
        current_snapshot_id="snap-art109",
        review_status=ReviewStatus.PROPOSED,
        metadata={},
    )
    props = extract_propositions(source=source, topic=_topic(), cluster=_cluster(), limit=4, llm_client=None)
    equine = [
        p
        for p in props
        if "equine" in p.proposition_text.lower()
        and ":list:" in (p.fragment_locator or "")
        and "-d-" in (p.fragment_locator or "").replace("__", "-")
    ]
    assert equine, "expected §1(d) equine sub-item under limit=4 with round-robin"
    assert parse_structured_extraction_notes(equine[0].notes) or (
        equine[0].extraction_debug_meta or {}
    ).get("structured_list_path")


def test_article109_extracts_equine_list_item_separately_and_preserves_parent() -> None:
    text = """Article 109
1.
The Member States shall establish and maintain a computer database for recording of at least:
(a) the following information related to kept animals of the bovine species: bovine-specific details.
(b) the following information related to kept animals of the ovine species: ovine-specific details.
(d) the following information related to kept animals of the equine species:
(i) their unique code as provided for in Article 114.
(ii) other identification details.
"""
    source = SourceRecord(
        id="pilot-eu-2016-429-art109",
        title="Regulation (EU) 2016/429 — Article 109",
        jurisdiction="EU",
        citation="CELEX 32016R0429 Art 109",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator="article:109",
        current_snapshot_id="snap-art109",
        review_status=ReviewStatus.PROPOSED,
        metadata={},
    )

    props = extract_propositions(source=source, topic=_topic(), cluster=_cluster(), limit=24, llm_client=None)
    assert props, "expected structured list propositions"
    equine_props = [p for p in props if "equine" in p.proposition_text.lower()]
    assert equine_props, "expected an equine-specific list item"
    eq = equine_props[0]
    assert "member states" in eq.proposition_text.lower()
    meta = parse_structured_extraction_notes(eq.notes) or dict(eq.extraction_debug_meta or {})
    assert meta.get("parent_context") or meta.get("structured_list_path")
    assert "list" in str(meta.get("evidence_locator", eq.fragment_locator or "")).lower() or ":" in str(
        meta.get("evidence_locator", eq.fragment_locator or "")
    )


def test_structured_equine_links_direct_equine_scope_and_trace_signals() -> None:
    text = """Article 109
1.
The Member States shall establish and maintain a computer database for recording of at least:
(a) bovine information here.
(d) the following information related to kept animals of the equine species.
"""
    demo = build_demo_bundle(use_llm=False)
    bundle = copy.deepcopy(demo)
    bundle["has_proposition_extraction_traces"] = False
    bundle["proposition_extraction_traces"] = []
    if "proposition_extraction_trace_count" in bundle:
        bundle["proposition_extraction_trace_count"] = 0

    p0 = bundle["propositions"][0]
    src_dict = next(s for s in bundle["source_records"] if s["id"] == p0["source_record_id"])
    source = SourceRecord.model_validate({**src_dict, "authoritative_text": text, "authoritative_locator": "article:109"})

    topic = Topic.model_validate(demo["topic"])
    cluster = Cluster.model_validate(demo["clusters"][0])

    prop_in = extract_propositions(source=source, topic=topic, cluster=cluster, limit=10, llm_client=None)
    equine_only = next(p for p in prop_in if "equine" in p.proposition_text.lower())
    equine_row = equine_only.model_copy(
        update={
            "id": p0["id"],
            "topic_id": p0["topic_id"],
            "cluster_id": p0["cluster_id"],
            "source_record_id": p0["source_record_id"],
            "source_snapshot_id": p0["source_snapshot_id"],
            "source_fragment_id": p0["source_fragment_id"],
        }
    )

    traces = _build_proposition_extraction_traces(
        propositions=[equine_row],
        use_llm=False,
        extraction_prompt={"name": "extract.propositions.default", "version": "v1"},
        extraction_strategy_version="vstructured-test",
        extraction_hook={"cache_status": None},
        pipeline_version="pipeline-test",
    )
    assert traces[0].rule_id == STRUCTURED_LIST_RULE_ID
    assert traces[0].signals.get("parent_context")

    sources = []
    for row in bundle["source_records"]:
        rec = SourceRecord.model_validate(row)
        if rec.id == p0["source_record_id"]:
            rec = rec.model_copy(update={"authoritative_text": text, "authoritative_locator": "article:109"})
        sources.append(rec)

    payload = build_scope_artifacts_for_run(run_id=str(bundle["run"]["id"]), propositions=[equine_row], sources=sources)

    equine_links = [
        ln for ln in payload.proposition_scope_links if ln.scope_id == "equine" and ln.inheritance == "explicit"
    ]
    assert equine_links
    assert equine_links[0].relevance == "direct"
    assert equine_links[0].confidence == "high"

    bundle["propositions"][0] = equine_row.model_dump(mode="json")
    other_links = [ln for ln in bundle["proposition_scope_links"] if ln["proposition_id"] != p0["id"]]
    bundle["proposition_scope_links"] = other_links + [
        ln.model_dump(mode="json") for ln in payload.proposition_scope_links
    ]
    bundle["legal_scopes"] = [s.model_dump(mode="json") for s in payload.legal_scopes]
    others_cand = [
        c for c in bundle["scope_review_candidates"] if c.get("signals", {}).get("proposition_id") != p0["id"]
    ]
    bundle["scope_review_candidates"] = others_cand + [
        c.model_dump(mode="json") for c in payload.scope_review_candidates
    ]

    report = lint_bundle(bundle)
    assert not report["errors"]
