from law_proposition_extractor_domain import Cluster, SourceRecord, Topic
from law_proposition_extractor_pipeline.extract import extract_propositions


def _topic() -> Topic:
    return Topic(id="topic-traceability", name="Traceability duties")


def _cluster() -> Cluster:
    return Cluster(id="cluster-traceability", topic_id="topic-traceability", name="Core duties")


def test_heuristic_extraction_prefers_normative_lines_and_keeps_fragment_locator() -> None:
    source = SourceRecord(
        id="src-uk-001",
        title="Example UK instrument",
        jurisdiction="UK",
        citation="UK-EXAMPLE-001",
        kind="regulation",
        authoritative_text=(
            "Section 1. Citation and commencement.\n"
            "Section 2. Operators must maintain movement records before dispatch.\n"
            "Section 3. The competent authority may inspect records on request."
        ),
        authoritative_locator="document:full",
        current_snapshot_id="snap-src-uk-001-v1",
        metadata={"fragment_locators": ["section:1", "section:2", "section:3"]},
    )

    propositions = extract_propositions(source=source, topic=_topic(), cluster=_cluster(), limit=3)

    assert len(propositions) == 2
    assert propositions[0].fragment_locator == "section:2"
    assert propositions[1].fragment_locator == "section:3"
    assert propositions[0].source_snapshot_id == "snap-src-uk-001-v1"
    assert propositions[0].article_reference == "section 2"
    assert "must maintain movement records" in propositions[0].proposition_text.lower()


def test_heuristic_extraction_can_infer_reference_from_fragment_locator() -> None:
    source = SourceRecord(
        id="src-eu-001",
        title="Example EU instrument",
        jurisdiction="EU",
        citation="EU-EXAMPLE-001",
        kind="regulation",
        authoritative_text="Operators must maintain movement records.",
        authoritative_locator="document:full",
        current_snapshot_id="snap-src-eu-001-v1",
        metadata={"fragment_locators": ["xml:article-10"]},
    )

    propositions = extract_propositions(source=source, topic=_topic(), cluster=_cluster(), limit=1)

    assert len(propositions) == 1
    assert propositions[0].fragment_locator == "xml:article-10"
    assert propositions[0].article_reference == "article 10"
