from __future__ import annotations

from pathlib import Path

from law_discovery.models import CandidateSource, EvidenceSnippet, load_category_brief
from law_discovery.scoring import score_candidate, score_candidates


def _equine_passports_category(examples_dir: Path):
    return load_category_brief(examples_dir / "categories" / "equine_passports.category.json")


def _score(candidate: CandidateSource, examples_dir: Path) -> CandidateSource:
    return score_candidates([candidate], _equine_passports_category(examples_dir))[0]


def test_coal_mines_act_not_high_confidence(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="fp-coal-mines",
        title="Coal Mines Act 1911",
        source_type="act",
        matched_terms=["horse"],
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence != "high"
    assert scored.relationship_to_category != "directly_regulates"


def test_race_horse_duty_act_not_high_confidence(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="fp-race-horse-duty",
        title="Race-horse Duty Act 1928",
        source_type="act",
        matched_terms=["horse"],
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence != "high"
    assert scored.relationship_to_category != "directly_regulates"


def test_electronic_identification_trust_services_not_high_confidence(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="fp-trust-services",
        title="The Electronic Identification and Trust Services for Electronic Transactions Regulations 2016",
        source_type="uksi",
        matched_terms=["electronic identification"],
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence != "high"
    assert scored.relationship_to_category != "directly_regulates"


def test_malvern_improvement_act_not_high_confidence(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="fp-malvern",
        title="Malvern Improvement Act 1929",
        source_type="act",
        matched_terms=["horse"],
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence != "high"
    assert scored.relationship_to_category != "directly_regulates"


def test_equine_disease_without_identification_is_contextual_not_directly_regulates(
    examples_dir: Path,
) -> None:
    candidate = CandidateSource(
        source_id="ctx-disease",
        title="The Equine Infectious Anaemia (England) Order 2012",
        source_type="uksi",
        matched_terms=["equine"],
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence != "high"
    assert scored.relationship_to_category != "directly_regulates"


def test_broad_species_only_match_capped_at_low(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="weak-horse",
        title="Unrelated Betting Act 1963",
        source_type="act",
        matched_terms=["horse"],
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence == "low"


def test_eu_2015_262_identification_of_equidae_high_directly_regulates(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="core-eu-2015-262",
        title="Commission Implementing Regulation (EU) 2015/262 laying down rules pursuant to Council Directive 90/427/EEC as regards the methods for the identification of equidae",
        source_type="assimilated_eu_law",
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_equine_identification_england_2018_high_directly_regulates(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="core-eng-2018",
        title="The Equine Identification (England) Regulations 2018",
        source_type="uksi",
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_equine_identification_wales_2019_high_directly_regulates(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="core-wales-2019",
        title="The Equine Identification (Wales) Regulations 2019",
        source_type="uksi",
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_equine_animal_identification_scotland_2019_high_directly_regulates(
    examples_dir: Path,
) -> None:
    candidate = CandidateSource(
        source_id="core-scot-2019",
        title="The Equine Animal (Identification) (Scotland) Regulations 2019",
        source_type="uksi",
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_equine_identification_northern_ireland_2019_high_directly_regulates(
    examples_dir: Path,
) -> None:
    candidate = CandidateSource(
        source_id="core-ni-2019",
        title="The Equine Identification Regulations (Northern Ireland) 2019",
        source_type="uksi",
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_horse_passports_regulations_2009_high_directly_regulates(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="core-hp-2009",
        title="The Horse Passports Regulations 2009",
        source_type="uksi",
        match_basis=["lex_search"],
        matched_terms=["horse passport"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_amendment_to_equine_identification_can_score_high(examples_dir: Path) -> None:
    candidate = CandidateSource(
        source_id="amend-eng",
        title="The Equine Identification (England) (Amendment) Regulations 2020",
        source_type="uksi",
        match_basis=["lex_search"],
    )
    scored = _score(candidate, examples_dir)
    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_anchor_passes_with_evidence_linkage(examples_dir: Path) -> None:
    category = _equine_passports_category(examples_dir)
    candidate = CandidateSource(
        source_id="evidence-link",
        title="Animal Health (Miscellaneous) Order 2012",
        source_type="uksi",
        matched_terms=["equine"],
        evidence=[
            EvidenceSnippet(
                evidence_type="text_snippet",
                text="Requirements for equine identification and horse passport records.",
            )
        ],
    )
    scored = score_candidate(candidate, category)
    assert scored.confidence in {"high", "medium"}
    if scored.confidence == "high":
        assert scored.relationship_to_category == "directly_regulates"
