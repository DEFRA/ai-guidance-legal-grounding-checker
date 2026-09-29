import pytest
from law_proposition_extractor_domain import SourceRecord
from law_proposition_extractor_pipeline.sources import build_source_target_link


def _source(
    *,
    source_id: str,
    title: str,
    citation: str,
    kind: str = "regulation",
    source_url: str | None = None,
    provenance: str = "authority.legislation_gov_uk",
    metadata: dict[str, object] | None = None,
) -> SourceRecord:
    return SourceRecord(
        id=source_id,
        title=title,
        jurisdiction="EU",
        citation=citation,
        kind=kind,
        authoritative_text="Article 10. Operators must maintain records.",
        provenance=provenance,
        source_url=source_url,
        metadata=metadata or {},
    )


@pytest.mark.parametrize(
    ("source", "expected_link_type"),
    [
        (
            _source(
                source_id="src-target-001",
                title="Regulation (EU) 2020/1234",
                citation="EU-BASE-001",
                source_url="https://www.legislation.gov.uk/eur/2020/1234",
                metadata={"is_target_source": True},
            ),
            "is_target",
        ),
        (
            _source(
                source_id="src-amend-001",
                title="Regulation amending EU-BASE-001",
                citation="EU-AMEND-001",
            ),
            "amends",
        ),
        (
            _source(
                source_id="src-corr-001",
                title="Corrigendum to EU-BASE-001",
                citation="EU-CORR-001",
            ),
            "corrects",
        ),
        (
            _source(
                source_id="src-deleg-001",
                title="Commission Delegated Regulation supplementing EU-BASE-001",
                citation="EU-DELEG-001",
            ),
            "supplements",
        ),
        (
            _source(
                source_id="src-impl-001",
                title="Commission Implementing Regulation for EU-BASE-001",
                citation="EU-IMPL-001",
            ),
            "implements",
        ),
        (
            _source(
                source_id="src-expl-001",
                title="Explanatory memorandum for EU-BASE-001",
                citation="EU-EXPL-001",
            ),
            "explains",
        ),
        (
            _source(
                source_id="src-guidance-001",
                title="Guidance on EU-BASE-001 compliance",
                citation="EU-GUIDE-001",
            ),
            "explains",
        ),
        (
            _source(
                source_id="src-cert-001",
                title="Model certificate for EU-BASE-001",
                citation="EU-CERT-001",
            ),
            "implements",
        ),
        (
            _source(
                source_id="src-annex-001",
                title="Annex I to EU-BASE-001",
                citation="EU-ANNEX-001",
            ),
            "contains_annex_to",
        ),
        (
            _source(
                source_id="src-context-001",
                title="Unrelated context note",
                citation="OTHER-001",
                provenance="manual",
                source_url="https://example.com/context",
            ),
            "contextual",
        ),
    ],
)
def test_build_source_target_link_assigns_expected_link_type(
    source: SourceRecord,
    expected_link_type: str,
) -> None:
    link = build_source_target_link(
        source=source,
        primary_target_source_id="src-target-001",
        primary_target_citation="EU-BASE-001",
        primary_target_instrument_id="EU-BASE-001",
        primary_target_title="Regulation (EU) 2020/1234",
    )
    assert link.link_type == expected_link_type
    assert link.method in {"deterministic", "fallback"}
    assert link.reason
