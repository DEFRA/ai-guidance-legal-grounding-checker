def test_ahl_and_animal_health_law_hint_eur_2016_429() -> None:
    from law_proposition_extractor_pipeline.sources.search_aliases import authority_source_ids_hinted_for_query

    for q in (
        "AHL",
        "animal health law",
        "Animal Health Law",
        "animal health",
        "transmissible animal diseases",
    ):
        hints = authority_source_ids_hinted_for_query(q)
        assert "eur/2016/429" in hints, q


def test_celex_32016r0429() -> None:
    from law_proposition_extractor_pipeline.sources.search_aliases import (
        authority_source_ids_hinted_for_query,
        eu_celex_to_legislation_authority_source_id,
    )

    assert eu_celex_to_legislation_authority_source_id("32016R0429") == "eur/2016/429"
    assert eu_celex_to_legislation_authority_source_id("CELEX: 32016R0429") == "eur/2016/429"

    hinted = authority_source_ids_hinted_for_query("CELEX 32016R0429")
    assert "eur/2016/429" in hinted


def test_eu_plain_year_number() -> None:
    from law_proposition_extractor_pipeline.sources.search_aliases import authority_source_ids_hinted_for_query

    assert "eur/2016/429" in authority_source_ids_hinted_for_query("EU 2016/429")
