"""
Guidance Discovery — static search filters: the TWO dials that decide the entire corpus.

This is the whole of Guidance Discovery's "smart filtering" — and it is deliberately not very
smart. There is NO query string, NO relevance ranking, NO date or popularity
gate. The GOV.UK Search API is simply asked for every page that:

    belongs to one of these ORGANISATIONS   AND   is one of these DOCUMENT_TYPES

Withdrawn pages are included too (``debug=include_withdrawn`` in config.py):
the Search API hides them from public search by default.

…and then every matching page is fetched in full (stage 2). The intelligent,
topic-aware narrowing happens downstream in Guidance Relevance Filter, not here.

So these two lists are the only levers on what exists at all:

    widen  -> bigger corpus, longer body fetch, higher recall ceiling
    narrow -> smaller corpus, faster, lower recall ceiling

They are imported by ``get_defra_guidance_pages.py`` (stage 1).
"""

# ============================================================================
# DIAL 1 — ORGANISATIONS   (Search API: filter_organisations[])
#
# Every gov.uk publishing body whose pages we pull. 44 DEFRA-family and
# adjacent organisations. A page is in scope if its publishing org is in here.
# Sorted alphabetically; deduplicated (the source script listed five orgs twice).
# ============================================================================
ORGANISATIONS = [
    "advisory-committee-on-business-appointments",
    "animal-and-plant-health-agency",
    "animal-health-and-veterinary-laboratories-agency",
    "british-cattle-movement-service",
    "central-digital-and-data-office",
    "centre-for-environment-fisheries-and-aquaculture-science",
    "civil-service-government-veterinary-services",
    "commission-for-rural-communities",
    "consumer-council-for-water",
    "department-for-business-energy-and-industrial-strategy",
    "department-for-energy-security-and-net-zero",
    "department-for-environment-food-rural-affairs",
    "department-for-levelling-up-housing-and-communities",
    "department-for-transport",
    "department-of-energy-climate-change",
    "environment-agency",
    "flood-and-coastal-erosion-risk-management-research-and-development-programme",
    "food-standards-agency",
    "forest-enterprise-england",
    "forest-research",
    "forest-service",
    "forestry-commission",
    "government-chemist",
    "government-office-for-science",
    "high-speed-two-limited",
    "hm-revenue-customs",
    "joint-nature-conservation-committee",
    "marine-fisheries-agency",
    "marine-management-organisation",
    "maritime-and-coastguard-agency",
    "ministry-of-housing-communities-and-local-government",
    "national-forest-company",
    "natural-england",
    "office-for-environmental-protection",
    "plant-varieties-and-seeds-tribunal",
    "rural-development-programme-for-england-network",
    "rural-payments-agency",
    "sellafield-ltd",
    "state-veterinary-service",
    "the-food-and-environment-research-agency",
    "valuation-office-agency",
    "veterinary-laboratories-agency",
    "veterinary-medicines-directorate",
    "veterinary-products-committee",
]

# ============================================================================
# DIAL 2 — DOCUMENT TYPES   (Search API: filter_content_store_document_type[])
#
# Which content-store document types count as "guidance" for our purposes.
# A page is in scope only if its document type is one of these.
#
# html_publication is deliberately absent: the Search API does not index that
# type (zero hits globally). Stage 2 expands HTML-attachment chapters from
# each parent publication's Content API `links.children` instead.
# ============================================================================
DOCUMENT_TYPES = [
    "data_ethics_guidance_document",
    "detailed_guide",
    "guidance",
    "statutory_guidance",
    "guide",
    "manual",
    "service_manual_topic",
    "document_collection",
    "manual_section",
    "countryside_stewardship_grant",
    "service_standard_report",
    "farming_grant",
]
