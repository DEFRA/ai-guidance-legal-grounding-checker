"""Registration of discovered SourceFamilyCandidate rows via the normal registry path."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from law_proposition_extractor_pipeline.sources import SourceRegistryService
from law_proposition_extractor_pipeline.sources.family_candidate_registration import (
    candidate_can_auto_register,
    register_family_candidates,
)


def _case_file_reference_eur() -> dict:
    return {
        "authority": "case_file",
        "authority_source_id": "eur/2016/429",
        "id": "src-eur-429",
        "title": "EU Animal Health",
        "jurisdiction": "EU",
        "citation": "EUR 2016/429",
        "kind": "regulation",
        "text": "Article 10 text for fixture.",
        "authoritative_locator": "article:10",
        "version_id": "v1",
    }


def _mock_urlopen_context(xml: str) -> MagicMock:
    cm = MagicMock()
    cm.read.return_value = xml.encode()
    cm.status = 200
    cm.headers.get_content_charset.return_value = "utf-8"
    cm.headers.get.return_value = "application/xml"
    cm.__enter__.return_value = cm
    cm.__exit__.return_value = None
    return cm


def test_candidate_manual_review_when_insufficient_locator(tmp_path: Path) -> None:
    registry = SourceRegistryService(
        registry_path=tmp_path / "sr.json",
        source_cache_dir=tmp_path / "cache",
    )
    target = registry.register_reference(reference=_case_file_reference_eur(), refresh=False)
    out = register_family_candidates(
        registry,
        target_registry_id=target["registry_id"],
        candidate_ids=["sfc-2016-429-consolidated"],
    )
    assert out["registered"] == []
    assert out["already_registered"] == []
    assert len(out["manual_review_needed"]) == 1
    assert out["manual_review_needed"][0]["candidate_id"] == "sfc-2016-429-consolidated"


def test_duplicate_candidate_returns_already_registered(tmp_path: Path) -> None:
    registry = SourceRegistryService(
        registry_path=tmp_path / "sr.json",
        source_cache_dir=tmp_path / "cache",
    )
    registry.register_reference(
        reference={
            "authority": "legislation_gov_uk",
            "authority_source_id": "eur/2016/429",
            "id": "src-eur-2016-429",
            "title": "Pre-existing",
            "jurisdiction": "EU",
            "citation": "EUR 2016/429",
            "kind": "legislation",
            "source_url": "https://www.legislation.gov.uk/eur/2016/429/data.xml",
            "version_id": "latest",
        },
        refresh=False,
    )
    target = registry.register_reference(reference=_case_file_reference_eur(), refresh=False)
    out = register_family_candidates(
        registry,
        target_registry_id=target["registry_id"],
        candidate_ids=["sfc-2016-429-base"],
    )
    assert out["registered"] == []
    assert len(out["already_registered"]) == 1
    assert out["already_registered"][0]["candidate_id"] == "sfc-2016-429-base"
    assert out["manual_review_needed"] == []
    assert out["errors"] == []


def test_registers_candidate_with_url_mocked_fetch(tmp_path: Path) -> None:
    xml = """
    <Legislation>
      <Title>Regulation (EU) 2016/429</Title>
      <Body><P1 id="a">Operators must maintain registers.</P1></Body>
    </Legislation>
    """
    registry = SourceRegistryService(
        registry_path=tmp_path / "sr.json",
        source_cache_dir=tmp_path / "cache",
    )
    target = registry.register_reference(reference=_case_file_reference_eur(), refresh=False)
    with patch("law_proposition_extractor_pipeline.sources.adapters.urlopen", return_value=_mock_urlopen_context(xml)):
        out = register_family_candidates(
            registry,
            target_registry_id=target["registry_id"],
            candidate_ids=["sfc-2016-429-base"],
        )
    assert len(out["registered"]) == 1
    assert out["registered"][0]["candidate_id"] == "sfc-2016-429-base"
    rid = out["registered"][0]["registry_id"]
    listed = registry.list_entries()
    assert any(e["registry_id"] == rid for e in listed)


def test_candidate_can_auto_register_false_for_unknown_role() -> None:
    row = {
        "id": "x",
        "title": "T",
        "url": "https://www.legislation.gov.uk/eur/2016/429",
        "source_role": "unknown",
        "relationship_to_target": "implements",
    }
    ok, reason = candidate_can_auto_register(row)
    assert ok is False
    assert "source_role" in reason

