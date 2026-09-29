"""Stage 2 body fetch: extracting body text and expanding HTML-attachment chapters."""

import pytest

from fetch_body import (
    _assemble_output,
    _extract_body_text,
    _fill_organisations,
    _fill_withdrawn,
    _html_publication_children,
    _inherit_organisations,
    _inherit_organisations_from_parents,
    _is_publication_parent,
    _items_to_fetch,
    _record_fetch_failure,
    _should_fetch,
)
from funnel import journal

PARENT = "https://www.gov.uk/government/publications/slurry-infrastructure-grant"
CHAPTER = PARENT + "/about-the-slurry-infrastructure-grant-who-can-apply-and-what-it-can-pay-for"


def _page(url, *, body="text", extra_meta=None, **meta):
    md = {"title": "T", "document_type": "guidance", "body_text": body, **meta}
    if extra_meta:
        md.update(extra_meta)
    return {"url": url, "content_id": "id", "meta_data": md}


@pytest.mark.parametrize("content, expected", [
    ({"details": {"body": "<p>Hello world</p>"}}, "Hello world"),
    ({"details": {"parts": [{"body": "<p>One</p>"}, {"body": "<p>Two</p>"}]}}, "One\n\nTwo"),
    ({"details": {"body": " \n "}}, ""),
    ({"details": {}}, ""),
], ids=["single body", "multipart guide", "whitespace body", "no body"])
def test_extracts_body_text_from_a_page(content, expected):
    assert _extract_body_text(content) == expected


def test_extracts_collection_index_when_body_is_whitespace():
    content = {
        "details": {
            "body": " \n ",
            "collection_groups": [
                {
                    "title": "Check what you owe",
                    "body": " \n ",
                    "documents": ["doc-1"],
                },
                {
                    "title": "Slurry stores",
                    "body": "<p>How to store slurry.</p>",
                    "documents": ["doc-2", "missing"],
                },
            ],
        },
        "links": {
            "documents": [
                {"content_id": "doc-1", "title": "HMRC online services"},
                {"content_id": "doc-2", "title": "Storing silage, slurry and agricultural fuel oil"},
            ]
        },
    }
    assert _extract_body_text(content) == (
        "Check what you owe\n"
        "HMRC online services\n"
        "Slurry stores\n"
        "How to store slurry.\n"
        "Storing silage, slurry and agricultural fuel oil"
    )


def test_appends_collection_index_to_a_real_intro():
    content = {
        "details": {
            "body": "<p>Intro.</p>",
            "collection_groups": [{"title": "Grants", "documents": ["doc-1"]}],
        },
        "links": {"documents": [{"content_id": "doc-1", "title": "Slurry infrastructure grant"}]},
    }
    assert _extract_body_text(content) == "Intro.\n\nGrants\nSlurry infrastructure grant"


def test_falls_back_to_document_titles_when_collection_has_no_groups():
    content = {
        "details": {"body": " \n "},
        "links": {"documents": [{"content_id": "doc-1", "title": "Pay landfill tax"}]},
    }
    assert _extract_body_text(content) == "Pay landfill tax"


def test_extracts_manual_toc_from_child_section_groups():
    content = {
        "details": {
            "body": "\n",
            "child_section_groups": [
                {
                    "title": "Contents",
                    "child_sections": [
                        {
                            "title": "1. When appropriate measures apply",
                            "description": "Who this guidance is for.",
                        },
                        {"title": "2. Waste types", "description": ""},
                    ],
                }
            ],
        }
    }
    assert _extract_body_text(content) == (
        "Contents\n"
        "1. When appropriate measures apply\n"
        "Who this guidance is for.\n"
        "2. Waste types"
    )


def test_expands_html_publication_children_from_links():
    content = {
        "links": {
            "children": [
                {
                    "document_type": "html_publication",
                    "base_path": "/government/publications/slurry-infrastructure-grant/about",
                    "content_id": "child-1",
                    "title": "About the grant",
                    "public_updated_at": "2024-03-12T09:04:44Z",
                },
                {
                    "document_type": "organisation",
                    "base_path": "/government/organisations/defra",
                    "content_id": "org",
                    "title": "Defra",
                },
            ]
        }
    }
    children = _html_publication_children(content)
    assert [c["url"] for c in children] == [
        "https://www.gov.uk/government/publications/slurry-infrastructure-grant/about"
    ]
    assert children[0]["content_id"] == "child-1"
    assert children[0]["meta_data"]["title"] == "About the grant"
    assert children[0]["meta_data"]["document_type"] == "html_publication"
    assert children[0]["meta_data"]["updated_at"] == "2024-03-12T09:04:44Z"
    assert children[0]["meta_data"]["organisations"] == []
    assert children[0]["meta_data"]["primary_publishing_organisation"] == ""
    assert children[0]["meta_data"]["is_withdrawn"] is False


def test_fill_withdrawn_from_content_api_notice():
    md: dict = {}
    _fill_withdrawn(md, {
        "withdrawn_notice": {
            "explanation": "This was withdrawn.",
            "withdrawn_at": "2020-01-01T00:00:00Z",
        }
    })
    assert md["is_withdrawn"] is True


def test_fill_withdrawn_does_not_clear_search_api_true():
    md = {"is_withdrawn": True}
    _fill_withdrawn(md, {})
    assert md["is_withdrawn"] is True


def test_fill_withdrawn_defaults_missing_to_false():
    md: dict = {}
    _fill_withdrawn(md, {})
    assert md["is_withdrawn"] is False


def test_fills_organisations_from_content_api_links():
    md: dict = {}
    _fill_organisations(md, {
        "links": {
            "organisations": [
                {"base_path": "/government/organisations/environment-agency"},
                {"base_path": "/government/organisations/rural-payments-agency"},
            ],
            "primary_publishing_organisation": [
                {"base_path": "/government/organisations/environment-agency"},
            ],
        }
    })
    assert md["organisations"] == ["environment-agency", "rural-payments-agency"]
    assert md["primary_publishing_organisation"] == "environment-agency"


def test_does_not_overwrite_existing_organisations():
    md = {
        "organisations": ["defra"],
        "primary_publishing_organisation": "defra",
    }
    _fill_organisations(md, {
        "links": {
            "organisations": [{"base_path": "/government/organisations/environment-agency"}],
            "primary_publishing_organisation": [
                {"base_path": "/government/organisations/environment-agency"},
            ],
        }
    })
    assert md["organisations"] == ["defra"]
    assert md["primary_publishing_organisation"] == "defra"


def test_chapters_inherit_parent_organisations():
    children = _html_publication_children({
        "links": {
            "children": [{
                "document_type": "html_publication",
                "base_path": "/government/publications/slurry-infrastructure-grant/about",
                "title": "About",
            }]
        }
    })
    _inherit_organisations(
        {
            "organisations": ["department-for-environment-food-rural-affairs"],
            "primary_publishing_organisation": "department-for-environment-food-rural-affairs",
        },
        children,
    )
    assert children[0]["meta_data"]["organisations"] == [
        "department-for-environment-food-rural-affairs"
    ]
    assert children[0]["meta_data"]["primary_publishing_organisation"] == (
        "department-for-environment-food-rural-affairs"
    )


def test_inherit_does_not_overwrite_existing_child_organisations():
    children = _html_publication_children({
        "links": {
            "children": [{
                "document_type": "html_publication",
                "base_path": "/government/publications/slurry-infrastructure-grant/about",
                "title": "About",
            }]
        }
    })
    children[0]["meta_data"]["organisations"] = ["food-standards-agency"]
    children[0]["meta_data"]["primary_publishing_organisation"] = "food-standards-agency"
    _inherit_organisations(
        {
            "organisations": ["department-for-environment-food-rural-affairs"],
            "primary_publishing_organisation": "department-for-environment-food-rural-affairs",
        },
        children,
    )
    assert children[0]["meta_data"]["organisations"] == ["food-standards-agency"]
    assert children[0]["meta_data"]["primary_publishing_organisation"] == (
        "food-standards-agency"
    )


def test_inherit_fills_only_the_empty_org_field():
    child = _page(CHAPTER, extra_meta={"document_type": "html_publication"})
    child["meta_data"]["organisations"] = ["food-standards-agency"]
    child["meta_data"]["primary_publishing_organisation"] = ""
    _inherit_organisations(
        {
            "organisations": ["department-for-environment-food-rural-affairs"],
            "primary_publishing_organisation": "rural-payments-agency",
        },
        [child],
    )
    assert child["meta_data"]["organisations"] == ["food-standards-agency"]
    assert child["meta_data"]["primary_publishing_organisation"] == "rural-payments-agency"


def test_assemble_output_inherits_empty_chapter_orgs_from_parent():
    parent = _page(
        PARENT,
        organisations=["department-for-transport"],
        primary_publishing_organisation="department-for-transport",
        extra_meta={"html_publication_urls": [CHAPTER]},
    )
    chapter = _page(
        CHAPTER,
        extra_meta={"document_type": "html_publication"},
        organisations=[],
        primary_publishing_organisation="",
    )
    output = _assemble_output([parent], {PARENT: parent, CHAPTER: chapter})
    assert output[1]["meta_data"]["organisations"] == ["department-for-transport"]
    assert output[1]["meta_data"]["primary_publishing_organisation"] == (
        "department-for-transport"
    )


def test_assemble_output_keeps_chapter_orgs_when_already_present():
    parent = _page(
        PARENT,
        organisations=["department-for-transport"],
        primary_publishing_organisation="department-for-transport",
        extra_meta={"html_publication_urls": [CHAPTER]},
    )
    chapter = _page(
        CHAPTER,
        extra_meta={"document_type": "html_publication"},
        organisations=["food-standards-agency"],
        primary_publishing_organisation="food-standards-agency",
    )
    output = _assemble_output([parent], {PARENT: parent, CHAPTER: chapter})
    assert output[1]["meta_data"]["organisations"] == ["food-standards-agency"]
    assert output[1]["meta_data"]["primary_publishing_organisation"] == (
        "food-standards-agency"
    )


def test_inherit_from_parents_is_a_no_op_without_chapters():
    item = _page(PARENT, organisations=["defra"])
    _inherit_organisations_from_parents([item])
    assert item["meta_data"]["organisations"] == ["defra"]


def test_falls_back_to_html_attachments_when_links_children_empty():
    content = {
        "links": {"children": []},
        "details": {
            "attachments": [
                {
                    "attachment_type": "html",
                    "title": "About",
                    "url": "/government/publications/slurry-infrastructure-grant/about",
                },
                {
                    "attachment_type": "file",
                    "title": "PDF",
                    "url": "/government/uploads/system/x.pdf",
                },
            ]
        },
    }
    children = _html_publication_children(content)
    assert [c["url"] for c in children] == [
        "https://www.gov.uk/government/publications/slurry-infrastructure-grant/about"
    ]
    assert children[0]["meta_data"]["title"] == "About"


def test_prefers_links_children_over_attachments():
    content = {
        "links": {
            "children": [
                {
                    "document_type": "html_publication",
                    "base_path": "/government/publications/x/from-links",
                    "content_id": "from-links",
                    "title": "From links",
                }
            ]
        },
        "details": {
            "attachments": [
                {
                    "attachment_type": "html",
                    "title": "From att",
                    "url": "/government/publications/x/from-att",
                }
            ]
        },
    }
    children = _html_publication_children(content)
    assert [c["url"] for c in children] == [
        "https://www.gov.uk/government/publications/x/from-links"
    ]


@pytest.mark.parametrize("url, expected", [
    (PARENT, True),
    (CHAPTER, False),
    ("https://www.gov.uk/guidance/storing-silage-slurry-and-agricultural-fuel-oil", False),
    ("https://www.gov.uk/government/collections/farming-investment-fund-fif", False),
])
def test_publication_parent_heuristic(url, expected):
    assert _is_publication_parent(url) is expected


def test_refetches_old_cached_publication_parent_without_expansion_marker():
    cached = _page(PARENT)
    assert _should_fetch(PARENT, cached) is True
    cached["meta_data"]["html_publication_urls"] = []
    assert _should_fetch(PARENT, cached) is False


def test_skips_cached_non_publication_even_without_expansion_marker():
    url = "https://www.gov.uk/guidance/storing-silage-slurry-and-agricultural-fuel-oil"
    assert _should_fetch(url, _page(url)) is False


def test_fetches_uncached_or_failed():
    assert _should_fetch(PARENT, None) is True
    failed = _page(PARENT, body=None)
    assert _should_fetch(PARENT, failed) is True


def test_refetches_cached_empty_body():
    url = "https://www.gov.uk/government/collections/paying-hmrc-detailed-information"
    assert _should_fetch(url, _page(url, body="")) is True
    assert _should_fetch(url, _page(url, body=" \n ")) is True
    assert _should_fetch(url, _page(url, body="intro")) is False


def test_items_to_fetch_refetches_old_publication_parent():
    parent = _page(PARENT)  # cached body, no html_publication_urls
    work = _items_to_fetch([parent], {PARENT: parent})
    assert [i["url"] for i in work] == [PARENT]


def test_items_to_fetch_walks_cached_parent_chapters():
    parent = _page(PARENT, extra_meta={"html_publication_urls": [CHAPTER]})
    existing = {PARENT: parent}
    work = _items_to_fetch([parent], existing)
    assert [i["url"] for i in work] == [CHAPTER]


def test_assemble_output_appends_chapters_after_input_order():
    other = "https://www.gov.uk/guidance/other"
    parent = _page(PARENT, extra_meta={"html_publication_urls": [CHAPTER]})
    chapter = _page(CHAPTER, extra_meta={"document_type": "html_publication"})
    other_item = _page(other)
    existing = {PARENT: parent, CHAPTER: chapter, other: other_item}
    output = _assemble_output([other_item, parent], existing)
    assert [i["url"] for i in output] == [other, PARENT, CHAPTER]


def test_record_fetch_failure_stamps_body_and_error():
    item = _page(PARENT)
    counters = {"errors": 0}
    _record_fetch_failure(item, counters, http_status=404)
    assert item["meta_data"]["body_text"] is None
    assert item["meta_data"]["fetch_error"] == {"http_status": 404}
    assert counters["errors"] == 1
    _record_fetch_failure(item, counters, error="connection reset")
    assert item["meta_data"]["fetch_error"] == {"error": "connection reset"}
    assert counters["errors"] == 2


def test_funnel_lists_failed_empty_and_expanded_urls():
    search_hit = _page("https://www.gov.uk/guidance/ok")
    failed = _page("https://www.gov.uk/guidance/gone", body=None, extra_meta={
        "fetch_error": {"http_status": 410},
    })
    empty = _page("https://www.gov.uk/guidance/blank", body="")
    parent = _page(PARENT, extra_meta={"html_publication_urls": [CHAPTER]})
    chapter = _page(CHAPTER, extra_meta={"document_type": "html_publication"})
    vanished = _page("https://www.gov.uk/guidance/vanished")

    output = [search_hit, failed, empty, parent, chapter]
    doc = journal([search_hit, failed, empty, parent, vanished], output)

    assert doc["counts"]["search_hits"] == 5
    assert doc["counts"]["chapters_expanded"] == 1
    assert doc["counts"]["fetch_failed"] == 1
    assert doc["counts"]["body_empty"] == 1
    assert doc["counts"]["body_present"] == 3
    assert doc["counts"]["search_hits_missing_from_output"] == 1
    assert doc["fetch_failed"][0]["url"] == failed["url"]
    assert doc["fetch_failed"][0]["fetch_error"] == {"http_status": 410}
    assert doc["body_empty"][0]["url"] == empty["url"]
    assert doc["chapters_expanded"][0]["url"] == CHAPTER
    assert doc["chapters_expanded"][0]["parent_url"] == PARENT
    assert doc["search_hits_missing_from_output"][0]["url"] == vanished["url"]

