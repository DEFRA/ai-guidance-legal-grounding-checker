from law_discovery.models import CandidateSource, CategoryBrief, EvidenceSnippet
from law_discovery.scoring import deduplicate_candidates, score_candidate, score_candidates

_SLURRY_CATEGORY = CategoryBrief(
    category_id="slurry_manure_agricultural_effluent",
    label="Slurry, manure, and agricultural effluent",
    description="Storage, spreading, and disposal of livestock waste.",
    synonyms=[
        "slurry",
        "manure",
        "silage effluent",
        "structural integrity",
        "freeboard",
        "nitrate vulnerable zone",
    ],
)


def test_duplicate_uri_candidates_merge() -> None:
    first = CandidateSource(
        source_id="lex-first",
        title="Horse Passports Regulations 2009",
        citation="SI 2009/1741",
        canonical_uri="https://www.legislation.gov.uk/uksi/2009/1741",
        source_system="lex",
        match_basis=["lex_search"],
        matched_terms=["horse passport"],
        confidence="low",
    )
    second = CandidateSource(
        source_id="lex-second",
        title="",
        citation=None,
        canonical_uri="https://www.legislation.gov.uk/uksi/2009/1741",
        source_system="unknown",
        matched_terms=["equine"],
        confidence="medium",
        notes="Second note",
    )

    merged = deduplicate_candidates([first, second])

    assert len(merged) == 1
    assert merged[0].source_id == "lex-first"
    assert merged[0].title == "Horse Passports Regulations 2009"
    assert merged[0].matched_terms == ["horse passport", "equine"]
    assert merged[0].confidence == "medium"


def test_duplicate_citation_candidates_merge() -> None:
    first = CandidateSource(
        source_id="lex-a",
        title="Equine Identification Regulations",
        citation="SI 2018/123",
        match_basis=["lex_search"],
    )
    second = CandidateSource(
        source_id="lex-b",
        title="Equine Identification Regulations",
        citation="SI 2018/123",
        match_basis=["manual"],
        matched_terms=["equine identification"],
    )

    merged = deduplicate_candidates([first, second])

    assert len(merged) == 1
    assert merged[0].source_id == "lex-a"
    assert merged[0].match_basis == ["lex_search", "manual"]
    assert merged[0].matched_terms == ["equine identification"]


def test_duplicate_evidence_is_not_repeated() -> None:
    snippet = EvidenceSnippet(
        evidence_type="title",
        text="Horse Passports Regulations 2009",
        uri="https://www.legislation.gov.uk/uksi/2009/1741",
    )
    first = CandidateSource(
        source_id="lex-a",
        title="Horse Passports Regulations 2009",
        canonical_uri="https://example.test/a",
        evidence=[snippet],
    )
    second = CandidateSource(
        source_id="lex-b",
        title="Horse Passports Regulations 2009",
        canonical_uri="https://example.test/a",
        evidence=[snippet],
    )

    merged = deduplicate_candidates([first, second])

    assert len(merged) == 1
    assert len(merged[0].evidence) == 1


def test_equine_identification_regulations_scores_high_and_directly_regulates() -> None:
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification and traceability",
        description="Rules about horse identification",
        synonyms=["equine identification", "horse passport", "microchip"],
    )
    candidate = CandidateSource(
        source_id="lex-1",
        title="Equine Identification (England) Regulations 2018",
        citation="SI 2018/123",
        source_type="uksi",
        match_basis=["lex_search"],
    )

    scored = score_candidate(candidate, category)

    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_guidance_with_strong_evidence_scores_operationalises() -> None:
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Horse identification rules",
        synonyms=["horse passport", "keeper duties"],
    )
    candidate = CandidateSource(
        source_id="lex-2",
        title="General animal welfare guidance",
        source_type="guidance",
        evidence=[
            EvidenceSnippet(
                evidence_type="text_snippet",
                text="Guidance on horse passport and keeper duties for equines.",
            )
        ],
    )

    scored = score_candidate(candidate, category)

    assert scored.confidence == "medium"
    assert scored.relationship_to_category == "operationalises"


def test_weak_lex_only_result_scores_low() -> None:
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Horse identification rules",
        synonyms=["horse passport"],
    )
    candidate = CandidateSource(
        source_id="lex-3",
        title="Unrelated Betting Act 1963",
        source_type="act",
        match_basis=["lex_search"],
        matched_terms=["horse"],
    )

    scored = score_candidate(candidate, category)

    assert scored.confidence == "low"
    assert scored.relationship_to_category == "possibly_relevant"


def test_scoring_does_not_auto_accept_or_reject() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Equine identification",
        description="Desc",
        synonyms=["equine identification"],
    )
    candidate = CandidateSource(
        source_id="lex-4",
        title="Equine Identification (England) Regulations 2018",
        source_type="uksi",
        review_status="unreviewed",
    )

    scored = score_candidate(candidate, category)

    assert scored.review_status == "unreviewed"


def test_sorting_is_deterministic() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test",
        description="Desc",
        synonyms=["alpha", "beta"],
    )
    candidates = [
        CandidateSource(source_id="c", title="Charlie", match_basis=["lex_search"]),
        CandidateSource(
            source_id="a",
            title="Alpha Act",
            match_basis=["lex_search"],
            matched_terms=["alpha"],
        ),
        CandidateSource(
            source_id="b",
            title="Beta Regulations",
            evidence=[EvidenceSnippet(evidence_type="text_snippet", text="mentions beta")],
        ),
    ]

    first = score_candidates(candidates, category)
    second = score_candidates(candidates, category)

    assert [item.source_id for item in first] == [item.source_id for item in second]
    assert first[0].confidence in {"high", "medium", "low"}


def test_source_type_alone_does_not_directly_regulate() -> None:
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Horse identification rules",
        synonyms=["equine identification"],
    )
    candidate = CandidateSource(
        source_id="lex-act",
        title="Unrelated Betting Act 1963",
        source_type="act",
        match_basis=["lex_search"],
    )

    scored = score_candidate(candidate, category)

    assert scored.relationship_to_category != "directly_regulates"


def test_single_weak_matched_term_does_not_score_high() -> None:
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Horse identification rules",
        synonyms=["horse passport", "keeper"],
    )
    candidate = CandidateSource(
        source_id="lex-weak",
        title="Unrelated Betting Act 1963",
        source_type="act",
        matched_terms=["horse"],
        match_basis=["lex_search"],
    )

    scored = score_candidate(candidate, category)

    assert scored.confidence != "high"


def test_multiple_corroborating_matches_can_score_high() -> None:
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification and traceability",
        description="Horse identification rules",
        synonyms=["equine identification", "horse passport", "microchip"],
    )
    candidate = CandidateSource(
        source_id="lex-strong",
        title="Equine Identification and Horse Passport Order 2018",
        source_type="uksi",
        matched_terms=["equine identification", "horse passport"],
        evidence=[
            EvidenceSnippet(
                evidence_type="text_snippet",
                text="Requirements for equine identification and horse passport.",
            )
        ],
    )

    scored = score_candidate(candidate, category)

    assert scored.confidence == "high"


def test_revoked_title_sets_temporal_status() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test category",
        description="Desc",
        synonyms=["alpha"],
    )
    candidate = CandidateSource(
        source_id="lex-revoked",
        title="Alpha Regulations 2000 (Revoked)",
        source_type="uksi",
    )

    scored = score_candidate(candidate, category)

    assert scored.temporal_status == "revoked"


def test_repealed_title_sets_historical_temporal_status() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test category",
        description="Desc",
        synonyms=["alpha"],
    )
    candidate = CandidateSource(
        source_id="lex-repealed",
        title="Alpha Act 1990 (Repealed)",
        source_type="act",
    )

    scored = score_candidate(candidate, category)

    assert scored.temporal_status == "historical"


def test_slurry_vehicle_functional_safety_structural_integrity_scores_low() -> None:
    candidate = CandidateSource(
        source_id="noise-1",
        title="The Road Vehicles (Functional Safety) Regulations 2020",
        source_type="uksi",
        matched_terms=["structural integrity"],
        match_basis=["lex_search"],
    )

    scored = score_candidates([candidate], _SLURRY_CATEGORY)[0]

    assert scored.confidence == "low"
    assert scored.relationship_to_category != "directly_regulates"


def test_slurry_cdm_structural_integrity_scores_low() -> None:
    candidate = CandidateSource(
        source_id="noise-2",
        title="Construction (Design and Management) Regulations 2015",
        source_type="uksi",
        matched_terms=["structural integrity"],
        match_basis=["lex_search"],
    )

    scored = score_candidates([candidate], _SLURRY_CATEGORY)[0]

    assert scored.confidence == "low"
    assert scored.relationship_to_category != "directly_regulates"


def test_slurry_merchant_shipping_freeboard_scores_low() -> None:
    candidate = CandidateSource(
        source_id="noise-3",
        title="Merchant Shipping (Safety of Navigation) Regulations 2020",
        source_type="uksi",
        matched_terms=["freeboard"],
        match_basis=["lex_search"],
    )

    scored = score_candidates([candidate], _SLURRY_CATEGORY)[0]

    assert scored.confidence == "low"
    assert scored.relationship_to_category != "directly_regulates"


def test_slurry_silage_slurry_fuel_oil_scores_high_directly_regulates() -> None:
    candidate = CandidateSource(
        source_id="core-1",
        title=(
            "The Water Resources (Control of Pollution) (Silage, Slurry "
            "and Agricultural Fuel Oil) (England) Regulations 2010"
        ),
        source_type="uksi",
        match_basis=["lex_search"],
        matched_terms=["slurry"],
    )

    scored = score_candidates([candidate], _SLURRY_CATEGORY)[0]

    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_slurry_agricultural_pollution_wales_scores_high_directly_regulates() -> None:
    candidate = CandidateSource(
        source_id="core-2",
        title="The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021",
        source_type="uksi",
        match_basis=["lex_search"],
    )

    scored = score_candidates([candidate], _SLURRY_CATEGORY)[0]

    assert scored.confidence == "high"
    assert scored.relationship_to_category == "directly_regulates"


def test_slurry_nvz_action_programme_scotland_scores_high_or_medium() -> None:
    candidate = CandidateSource(
        source_id="core-3",
        title="The Action Programme for Nitrate Vulnerable Zones (Scotland) Regulations 2008",
        source_type="uksi",
        match_basis=["lex_search"],
    )

    scored = score_candidates([candidate], _SLURRY_CATEGORY)[0]

    assert scored.confidence in {"high", "medium"}


def test_slurry_council_directive_91_676_scores_high_or_medium() -> None:
    candidate = CandidateSource(
        source_id="core-4",
        title=(
            "Council Directive 91/676/EEC concerning the protection of waters "
            "against pollution caused by nitrates from agricultural sources"
        ),
        source_type="assimilated_eu_law",
        match_basis=["lex_search"],
        matched_terms=["agricultural nitrate"],
    )

    scored = score_candidates([candidate], _SLURRY_CATEGORY)[0]

    assert scored.confidence in {"high", "medium"}


def test_slurry_manure_alone_on_local_act_not_high() -> None:
    candidate = CandidateSource(
        source_id="fp-1",
        title="The Exampletown Local Act 1920",
        source_type="act",
        matched_terms=["manure"],
        match_basis=["lex_search"],
    )

    scored = score_candidates([candidate], _SLURRY_CATEGORY)[0]

    assert scored.confidence != "high"
    assert scored.relationship_to_category != "directly_regulates"
