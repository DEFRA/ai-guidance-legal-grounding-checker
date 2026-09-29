import pytest
from law_proposition_extractor_domain import SourceRecord
from law_proposition_extractor_pipeline.sources import classify_source_categorisation


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
    ("source", "primary_target_citation", "expected_role"),
    [
        (
            _source(
                source_id="src-base-001",
                title="Regulation (EU) 2020/1234",
                citation="EU-BASE-001",
                source_url="https://www.legislation.gov.uk/eur/2020/1234",
            ),
            "EU-BASE-001",
            "base_act",
        ),
        (
            _source(
                source_id="src-amend-001",
                title="Commission Regulation amending Regulation (EU) 2020/1234",
                citation="EU-AMEND-001",
            ),
            "EU-BASE-001",
            "amendment",
        ),
        (
            _source(
                source_id="src-deleg-001",
                title="Commission Delegated Regulation (EU) 2021/555",
                citation="EU-DELEG-001",
                metadata={"target_citation": "EU-BASE-001"},
            ),
            "EU-BASE-001",
            "delegated_act",
        ),
        (
            _source(
                source_id="src-impl-001",
                title="Commission Implementing Regulation (EU) 2021/888",
                citation="EU-IMPL-001",
            ),
            "EU-BASE-001",
            "implementing_act",
        ),
        (
            _source(
                source_id="src-guide-001",
                title="Guidance on movement record requirements",
                citation="EU-GUIDE-001",
            ),
            "EU-BASE-001",
            "guidance",
        ),
        (
            _source(
                source_id="src-expl-001",
                title="Explanatory memorandum to Regulation (EU) 2020/1234",
                citation="EU-EXPL-001",
            ),
            "EU-BASE-001",
            "explanatory_material",
        ),
        (
            _source(
                source_id="src-cert-001",
                title="Model certificate for consignments",
                citation="EU-CERT-001",
            ),
            "EU-BASE-001",
            "certificate_model",
        ),
        (
            _source(
                source_id="src-annex-001",
                title="Annex I - movement documentation format",
                citation="EU-ANNEX-001",
            ),
            "EU-BASE-001",
            "annex",
        ),
        (
            _source(
                source_id="src-corr-001",
                title="Corrigendum to Regulation (EU) 2020/1234",
                citation="EU-CORR-001",
            ),
            "EU-BASE-001",
            "corrigendum",
        ),
        (
            _source(
                source_id="src-case-001",
                title="Case-file input source",
                citation="CASE-001",
                provenance="demo.case_file",
            ),
            "CASE-001",
            "case_file",
        ),
        (
            _source(
                source_id="src-unknown-001",
                title="Background note",
                citation="EU-UNKNOWN-001",
                provenance="manual",
                source_url="https://example.com/background",
            ),
            "EU-BASE-001",
            "unknown",
        ),
    ],
)
def test_classifier_assigns_expected_source_role(
    source: SourceRecord,
    primary_target_citation: str,
    expected_role: str,
) -> None:
    rationale = classify_source_categorisation(
        source=source,
        primary_target_citation=primary_target_citation,
    )
    assert rationale.source_role == expected_role
    assert rationale.relationship_to_analysis
    assert rationale.method in {"deterministic", "fallback"}
