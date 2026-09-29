from guidance_relevance_web.category import (
    DOCUMENT_TYPE_OPTIONS,
    ORGANISATION_OPTIONS,
    document_type_options_for,
    filter_pages,
    is_slug,
    lexicon_warnings,
    normalize_slug,
    organisation_options_for,
    page_matches_document_types,
    page_matches_organisations,
    parse_csv_list,
    parse_lexicon_lines,
    parse_scope_list,
    scope_options,
    title_from_slug,
    unique_scope,
    unmatched_scope_warnings,
    unmatched_scope_warnings_index,
)


def _page(
    *,
    primary: str = "",
    organisations: list[str] | None = None,
    document_type: str = "guide",
) -> dict:
    return {
        "url": "https://www.gov.uk/x",
        "meta_data": {
            "title": "x",
            "document_type": document_type,
            "primary_publishing_organisation": primary,
            "organisations": organisations or [],
        },
    }


def test_slug():
    assert is_slug("slurry")
    assert not is_slug("Slurry")
    assert not is_slug("1nope")


def test_lexicon_parse_dedupes():
    assert parse_lexicon_lines("Slurry\nslurry\n# comment\n\nLagoon") == ["Slurry", "Lagoon"]


def test_warns_on_generic_and_trigram():
    warnings = lexicon_warnings(["farm", "animal by-products extra token", "the"])
    joined = " ".join(warnings)
    assert "generic" in joined
    assert "3+ tokens" in joined or "stems to nothing" in joined


def test_generic_stem_warning_is_unigram_only():
    warnings = lexicon_warnings(
        ["animal manure", "Animal slurry", "Farm slurry", "animal"]
    )
    joined = " ".join(warnings)
    assert "animal manure" not in joined
    assert "Animal slurry" not in joined
    assert "Farm slurry" not in joined
    assert "'animal' is a generic stem ('anim')" in joined


def test_csv_parse_dedupes_and_strips():
    assert parse_csv_list(" Environment Agency , environment-agency, EA, ea, ,RPA ") == [
        "environment-agency",
        "ea",
        "rpa",
    ]
    assert parse_csv_list("") == []
    assert parse_csv_list("  ,  ") == []


def test_scope_list_accepts_csv_or_array():
    assert parse_scope_list("guidance, detailed_guide") == ["guidance", "detailed-guide"]
    assert parse_scope_list(["guidance", "detailed_guide", "guidance"]) == [
        "guidance",
        "detailed-guide",
    ]
    assert parse_scope_list(None) == []
    assert parse_scope_list([]) == []


def test_document_type_overlay_covers_guidance_and_html_publication():
    slugs = {value for value, _label in DOCUMENT_TYPE_OPTIONS}
    assert slugs >= {"guidance", "detailed_guide", "html_publication", "guide"}
    labelled = dict(document_type_options_for(["html_publication", "made_up_type"]))
    assert labelled["html_publication"] == "HTML publication"
    assert labelled["made_up_type"] == title_from_slug("made_up_type")


def test_organisation_overlay_aliases_defra():
    slugs = {value for value, _label, _aliases in ORGANISATION_OPTIONS}
    assert "environment-agency" in slugs
    assert "department-for-environment-food-rural-affairs" in slugs
    assert "defra" not in slugs
    aliases = {
        alias
        for _value, _label, extra in ORGANISATION_OPTIONS
        for alias in extra
    }
    assert "defra" in aliases
    assert "ea" in aliases
    assert "rpa" in aliases
    opts = organisation_options_for(["environment-agency", "some-new-quango"])
    by_slug = {value: (label, aliases) for value, label, aliases in opts}
    assert by_slug["environment-agency"][1] == ("ea",)
    assert "some-new-quango" in by_slug
    assert by_slug["some-new-quango"][1] == ()


def test_unique_scope_unions_orgs_and_skips_empty():
    pages = [
        _page(primary="environment-agency", organisations=["rural-payments-agency"], document_type="guide"),
        _page(primary="environment-agency", document_type="detailed_guide"),
        _page(primary="", organisations=[], document_type=""),
        _page(primary="Department for Transport", document_type="html_publication"),
    ]
    orgs, types = unique_scope(pages)
    assert orgs == [
        "Department for Transport",
        "environment-agency",
        "rural-payments-agency",
    ]
    assert types == ["detailed_guide", "guide", "html_publication"]
    org_opts, type_opts = scope_options(orgs, types)
    assert ("environment-agency", "Environment Agency", ("ea",)) in org_opts
    assert ("html_publication", "HTML publication") in type_opts


def test_normalize_slug_collapses_spaces_and_underscores():
    assert normalize_slug("Detailed Guide") == "detailed-guide"
    assert normalize_slug("detailed_guide") == "detailed-guide"
    assert normalize_slug("Environment Agency") == "environment-agency"


def test_org_match_primary_or_list():
    primary_only = _page(primary="environment-agency")
    listed_only = _page(organisations=["rural-payments-agency"])
    both = _page(
        primary="government-digital-service",
        organisations=["hm-revenue-customs"],
    )
    assert page_matches_organisations(primary_only, ["Environment Agency"])
    assert page_matches_organisations(listed_only, ["rural-payments-agency"])
    assert page_matches_organisations(both, ["hm-revenue-customs"])
    assert not page_matches_organisations(primary_only, ["rural-payments-agency"])
    assert page_matches_organisations(primary_only, [])


def test_document_type_match():
    page = _page(document_type="detailed_guide")
    assert page_matches_document_types(page, ["Detailed Guide"])
    assert page_matches_document_types(page, ["guidance", "detailed_guide"])
    assert not page_matches_document_types(page, ["guidance"])
    assert not page_matches_document_types(_page(document_type=""), ["guide"])
    assert page_matches_document_types(page, [])


def test_filter_pages_and_empty_needles():
    ea = _page(primary="environment-agency", document_type="guide")
    defra = _page(
        primary="department-for-environment-food-rural-affairs",
        document_type="detailed_guide",
    )
    pages = [ea, defra]
    assert filter_pages(pages) == pages
    assert filter_pages(pages, organisations=["environment-agency"]) == [ea]
    assert filter_pages(pages, document_types=["detailed_guide"]) == [defra]
    assert filter_pages(
        pages,
        organisations=["environment-agency"],
        document_types=["detailed_guide"],
    ) == []
    assert filter_pages(
        pages,
        organisations=["environment-agency"],
        document_types=["guide"],
    ) == [ea]


def test_unmatched_scope_warnings():
    pages = [
        _page(primary="environment-agency", document_type="guide"),
    ]
    assert unmatched_scope_warnings(pages) == []
    assert unmatched_scope_warnings(pages, organisations=["environment-agency"]) == []
    assert unmatched_scope_warnings(pages, organisations=["defra"]) == [
        "organisation 'defra' matched no pages on this index",
    ]
    mixed = unmatched_scope_warnings(
        pages,
        organisations=["environment-agency", "defra"],
        document_types=["guide", "statutory-instrument"],
    )
    assert mixed == [
        "organisation 'defra' matched no pages on this index",
        "document type 'statutory-instrument' matched no pages on this index",
    ]


def test_unmatched_scope_warnings_index(tmp_path):
    import json

    from guidance_relevance_filter.narrowing import load_or_build_stem_index

    items = [{
        "url": "https://www.gov.uk/a",
        "meta_data": {
            "title": "A",
            "body_text": "body",
            "document_type": "guide",
            "organisations": ["environment-agency"],
            "primary_publishing_organisation": "environment-agency",
        },
    }]
    json_path = tmp_path / "pages.json"
    json_path.write_text(json.dumps(items))
    index = load_or_build_stem_index(
        json_path, corpus_sha256="s", path=tmp_path / "index.sqlite",
    )
    assert unmatched_scope_warnings_index(index) == []
    assert unmatched_scope_warnings_index(
        index, organisations=["environment-agency"],
    ) == []
    assert unmatched_scope_warnings_index(index, organisations=["defra"]) == [
        "organisation 'defra' matched no pages on this index",
    ]
    mixed = unmatched_scope_warnings_index(
        index,
        organisations=["environment-agency", "defra"],
        document_types=["guide", "statutory-instrument"],
    )
    assert mixed == [
        "organisation 'defra' matched no pages on this index",
        "document type 'statutory-instrument' matched no pages on this index",
    ]
    index.close()
