"""Stage 1 discovery: reshaping a GOV.UK Search API hit into Guidance Discovery's page contract."""

from config import SEARCH_DEBUG
from get_defra_guidance_pages import search_request_params, to_pipeline_item
from page import organisation_slug, organisation_slugs, primary_organisation_slug

SEARCH_HIT = {
    "link": "/guidance/store-slurry-safely",
    "content_id": "abc-123",
    "title": "Store slurry safely",
    "description": "How to store slurry.",
    "public_timestamp": "2024-01-01T00:00:00Z",
    "content_store_document_type": "guidance",
    "view_count": 42,
    "organisations": [
        {"slug": "department-for-environment-food-rural-affairs", "title": "Defra"},
        {"slug": "environment-agency", "title": "Environment Agency"},
    ],
    "primary_publishing_organisation": [
        {"slug": "department-for-environment-food-rural-affairs", "title": "Defra"},
    ],
    "is_withdrawn": False,
}


def test_maps_a_search_hit_to_the_page_contract():
    item = to_pipeline_item(SEARCH_HIT)
    assert item["url"] == "https://www.gov.uk/guidance/store-slurry-safely"
    assert item["content_id"] == "abc-123"
    assert item["meta_data"]["updated_at"] == "2024-01-01T00:00:00Z"
    assert item["meta_data"]["document_type"] == "guidance"
    assert item["meta_data"]["organisations"] == [
        "department-for-environment-food-rural-affairs",
        "environment-agency",
    ]
    assert item["meta_data"]["primary_publishing_organisation"] == (
        "department-for-environment-food-rural-affairs"
    )
    assert item["meta_data"]["is_withdrawn"] is False


def test_defaults_fields_missing_from_a_hit():
    item = to_pipeline_item({})
    assert item["url"] == "https://www.gov.uk"
    assert item["meta_data"]["view_count"] == 0
    assert item["meta_data"]["organisations"] == []
    assert item["meta_data"]["primary_publishing_organisation"] == ""
    assert item["meta_data"]["is_withdrawn"] is False


def test_maps_a_withdrawn_search_hit():
    item = to_pipeline_item({**SEARCH_HIT, "is_withdrawn": True})
    assert item["meta_data"]["is_withdrawn"] is True


def test_search_request_includes_withdrawn_pages():
    params = search_request_params()
    assert params["debug"] == SEARCH_DEBUG == "include_withdrawn"
    assert "is_withdrawn" in params["fields"]


def test_organisation_slug_from_search_and_content_shapes():
    assert organisation_slug({"slug": "environment-agency"}) == "environment-agency"
    assert organisation_slug(
        {"base_path": "/government/organisations/rural-payments-agency"}
    ) == "rural-payments-agency"
    assert organisation_slug(
        {"link": "/government/organisations/natural-england"}
    ) == "natural-england"
    assert organisation_slug("department-for-environment-food-rural-affairs") == (
        "department-for-environment-food-rural-affairs"
    )
    assert organisation_slug(None) == ""


def test_organisation_slugs_dedupes_and_skips_empty():
    assert organisation_slugs([
        {"slug": "defra"},
        {"slug": "defra"},
        {"base_path": "/government/organisations/environment-agency"},
        {},
    ]) == ["defra", "environment-agency"]
    assert organisation_slugs({"slug": "defra"}) == ["defra"]
    assert primary_organisation_slug([]) == ""
    assert primary_organisation_slug([{"slug": "defra"}, {"slug": "ea"}]) == "defra"
