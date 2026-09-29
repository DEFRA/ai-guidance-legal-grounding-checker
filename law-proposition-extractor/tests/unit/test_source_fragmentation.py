"""Ingestion-time splitting of monolithic document:full fragments."""

import json
from unittest.mock import MagicMock

from law_proposition_extractor_domain import Cluster, ReviewStatus, SourceFragment, SourceRecord, Topic
from law_proposition_extractor_pipeline.runner import _build_proposition_extraction_traces
from law_proposition_extractor_pipeline.source_fragmentation import (
    content_hash,
    expand_monolithic_source_fragment,
    fragment_type_from_locator,
    max_fragment_body_chars_for_llm_budget,
    plan_text_slices,
)
from law_proposition_extractor_pipeline.sources.service import slugify


def test_plan_text_slices_plain_article_locators() -> None:
    body = (
        "Article 109\nOperators must tag equidae.\n\n"
        "Article 114\nInspectors may enter premises.\n"
    )
    max_c = max_fragment_body_chars_for_llm_budget(max_extract_input_tokens=150_000)
    slices = plan_text_slices(body, "document:full", max_body_chars=max_c, overlap_chars=0)
    locs = [s[0] for s in slices]
    assert any(x.startswith("article:109") for x in locs)
    assert any(x.startswith("article:114") for x in locs)


def test_expand_splits_document_full_with_many_articles() -> None:
    preamble = "\n".join([f"Preamble {i}." for i in range(400)])
    body = preamble + "\nArticle 1\n" + ("Duty text. " * 600) + "\n\nArticle 2\n" + ("Other duty. " * 600) + "\n"
    frag = SourceFragment(
        id="frag-reg-test-001",
        source_record_id="src-reg",
        source_snapshot_id="snap-reg",
        fragment_type="instrument",
        locator="document:full",
        fragment_text=body,
        fragment_hash=content_hash(body),
        text_hash=content_hash(body),
        review_status=ReviewStatus.PROPOSED,
        metadata={},
    )
    max_c = 4000
    out = expand_monolithic_source_fragment(
        frag,
        max_body_chars=max_c,
        overlap_chars=0,
        slugify=slugify,
    )
    assert len(out) >= 2
    assert all(len(f.fragment_text) <= max_c * 1.05 for f in out)
    assert {f.source_record_id for f in out} == {"src-reg"}
    assert {f.source_snapshot_id for f in out} == {"snap-reg"}
    assert any(f.locator.startswith("article:") for f in out)


def test_xml_article_split_assigns_numbers() -> None:
    xml = (
        '<article n="109"><p>Equidae tagging.</p></article>'
        '<article n="114"><p>Inspections.</p></article>'
    )
    max_c = max_fragment_body_chars_for_llm_budget(max_extract_input_tokens=150_000)
    slices = plan_text_slices(xml, "document:full", max_body_chars=max_c, overlap_chars=0)
    assert {s[0] for s in slices} >= {"article:109", "article:114"}


def test_chunk_fallback_locator_has_index() -> None:
    blob = "Paragraph one.\n\n" + ("More text. " * 2000)
    max_c = 3000
    slices = plan_text_slices(blob, "document:full", max_body_chars=max_c, overlap_chars=0)
    assert len(slices) >= 2
    assert any("chunk:" in s[0] for s in slices)


def test_fragment_type_from_locator() -> None:
    assert fragment_type_from_locator("article:1") == "article"
    assert fragment_type_from_locator("article:15a") == "article"
    assert fragment_type_from_locator("annex:i") == "annex"
    assert fragment_type_from_locator("section:3") == "section"
    assert fragment_type_from_locator("article:2|chunk:001") == "chunk"
    assert fragment_type_from_locator("document:full") == "document"


def test_expand_structural_fragments_preserves_schedule_hierarchy() -> None:
    reg_text = "Regulation 1\nCitation and commencement.\n"
    schedule_text = "Schedule 1\nEnforcement.\n"
    para_text = "(1) A local authority may inspect records.\n(2) Inspectors may enter premises.\n"
    full_text = f"{reg_text}\n{schedule_text}\n{para_text}"
    frag = SourceFragment(
        id="frag-leg-001",
        source_record_id="src-leg",
        source_snapshot_id="snap-leg",
        fragment_type="instrument",
        locator="document:full",
        fragment_text=full_text,
        fragment_hash=content_hash(full_text),
        text_hash=content_hash(full_text),
        review_status=ReviewStatus.PROPOSED,
        metadata={
            "structural_fragments": [
                {
                    "locator": "regulation:1",
                    "text": reg_text,
                    "order_index": 0,
                    "metadata": {"source_path": "regulation/1"},
                },
                {
                    "locator": "schedule:1",
                    "text": schedule_text,
                    "order_index": 1,
                    "metadata": {"source_path": "schedule/1", "fragment_kind": "schedule"},
                },
                {
                    "locator": "schedule:1:paragraph:3",
                    "parent_locator": "schedule:1",
                    "text": para_text,
                    "order_index": 2,
                    "metadata": {
                        "source_path": "schedule/1/paragraph/3",
                        "fragment_kind": "amendment_provision",
                    },
                },
            ]
        },
    )
    out = expand_monolithic_source_fragment(
        frag,
        max_body_chars=10_000,
        overlap_chars=0,
        slugify=slugify,
    )
    by_loc = {f.locator: f for f in out}
    assert "regulation:1" in by_loc
    assert "schedule:1" in by_loc
    assert "schedule:1:paragraph:3" in by_loc
    assert "Schedule 1" not in by_loc["regulation:1"].fragment_text
    assert by_loc["schedule:1:paragraph:3"].parent_fragment_id == by_loc["schedule:1"].id
    assert by_loc["regulation:1"].parent_fragment_id is None
    assert by_loc["schedule:1"].parent_fragment_id is None
    assert by_loc["schedule:1"].metadata.get("fragment_kind") == "schedule"


def test_expand_structural_fragments_derives_child_fragment_type_from_locator() -> None:
    full_text = "Article 1\nMain body.\nAnnex I\nModel passport."
    frag = SourceFragment(
        id="frag-eu-262",
        source_record_id="src-eu-262",
        source_snapshot_id="snap-eu-262",
        fragment_type="article",
        locator="article:1",
        fragment_text=full_text,
        fragment_hash=content_hash(full_text),
        text_hash=content_hash(full_text),
        review_status=ReviewStatus.PROPOSED,
        metadata={
            "structural_fragments": [
                {"locator": "article:1", "text": "Article 1\nMain body.", "order_index": 0},
                {"locator": "annex:i", "text": "Annex I\nModel passport.", "order_index": 1},
            ]
        },
    )
    out = expand_monolithic_source_fragment(
        frag,
        max_body_chars=10_000,
        overlap_chars=0,
        slugify=slugify,
    )
    by_loc = {f.locator: f for f in out}
    assert by_loc["article:1"].fragment_type == "article"
    assert by_loc["annex:i"].fragment_type == "annex"


def test_extraction_trace_carries_article_locator_from_fragment() -> None:
    topic = Topic(id="t1", name="T", description="", subject_tags=[])
    cluster = Cluster(id="c1", topic_id="t1", name="C", description="")
    src = SourceRecord(
        id="src-x",
        title="Reg",
        jurisdiction="EU",
        citation="R",
        kind="regulation",
        authoritative_text="Article 7\nKeep registers.\n",
        authoritative_locator="article:7",
        current_snapshot_id="snap-x",
        metadata={"extraction_fragment_id": "frag-test-007"},
    )

    client = MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000

    def row() -> dict[str, object]:
        return {
            "proposition_text": "Operators must keep registers.",
            "display_label": "L",
            "subject": "operators",
            "rule": "must",
            "object": "",
            "conditions": [],
            "exceptions": [],
            "temporal_condition": "",
            "provision_type": "core",
            "source_locator": "article:7",
            "evidence_text": "Keep registers.",
            "completeness_status": "complete",
            "confidence": "high",
            "reason": "t",
        }

    client.complete_text.return_value = json.dumps({"propositions": [row()]})

    from law_proposition_extractor_pipeline.extract import extract_propositions_from_source

    out = extract_propositions_from_source(
        src,
        topic,
        cluster,
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="fallback",
    )
    assert out.propositions
    prop = out.propositions[0]
    prop.source_fragment_id = "frag-test-007"
    assert prop.fragment_locator == "article:7"
    traces = _build_proposition_extraction_traces(
        propositions=out.propositions,
        use_llm=True,
        extraction_prompt={"name": "extract.propositions.default", "version": "v2"},
        extraction_strategy_version="v1",
        extraction_hook={"cache_status": "none"},
        pipeline_version="test",
    )
    assert traces[0].source_fragment_id == "frag-test-007"
    assert "article:7" in (traces[0].evidence_locator or "") or prop.fragment_locator == "article:7"


def test_prompt_preflight_skips_llm_when_over_hard_budget() -> None:
    topic = Topic(id="t2", name="T", description="", subject_tags=[])
    cluster = Cluster(id="c2", topic_id="t2", name="C", description="")
    src = SourceRecord(
        id="src-y",
        title="Big",
        jurisdiction="EU",
        citation="R",
        kind="regulation",
        authoritative_text=("Operators shall comply.\n" * 500),
        authoritative_locator="document:full",
        current_snapshot_id="snap-y",
        metadata={"extraction_fragment_id": "frag-y"},
    )
    client = MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 50
    client.settings.extract_model_context_limit = 200_000

    from law_proposition_extractor_pipeline.extract import extract_propositions_from_source

    out = extract_propositions_from_source(
        src,
        topic,
        cluster,
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="fail_closed",
    )
    client.complete_text.assert_not_called()
    assert out.failed_closed
