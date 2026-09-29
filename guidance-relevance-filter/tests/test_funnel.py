"""Per-page funnel stamps and the LLM-stage drop journal."""

import json
from importlib.resources import files

from guidance_relevance_filter.adjudicate import adjudicate
from guidance_relevance_filter.classify import classify
from guidance_relevance_filter.funnel import (
    COSINE_MISS,
    EMPTY_BODY,
    LEXICON_MISS,
    MISSING_BODY,
    PASS1_FALSE,
    PASS2_DROP,
    PASS2_KEEP,
    exclusion_hit_counts,
    journal,
    page_ref,
    stage_counts,
)

from .fakes import llm

BAKED_IN_CATEGORIES = json.loads(
    (files("guidance_relevance_filter.data") / "categories.json").read_text()
)
BAKED_IN_LEXICONS = json.loads(
    (files("guidance_relevance_filter.data") / "lexicon.json").read_text()
)
FISH_CATEGORY = BAKED_IN_CATEGORIES[0]["name"]
FISH_TRUE = (
    f'{{"{FISH_CATEGORY}": true, "{FISH_CATEGORY}_score": 0.9, '
    f'"{FISH_CATEGORY}_reason": "about fishery products"}}'
)
FISH_FALSE = (
    f'{{"{FISH_CATEGORY}": false, "{FISH_CATEGORY}_score": 0.1, '
    f'"{FISH_CATEGORY}_reason": "incidental aquarium mention"}}'
)
FISH_KEEP = '{"keep": true, "exclusion_hit": "none", "verdict_reason": "catch certificates"}'
FISH_DROP = (
    '{"keep": false, "exclusion_hit": "wrong_domain", '
    '"verdict_reason": "ornamental aquarium fish"}'
)


def _page(url, body, title="T"):
    return {
        "url": url,
        "content_id": "x",
        "meta_data": {"title": title, "body_text": body},
    }


def test_page_ref_stamps_is_withdrawn():
    live = page_ref(_page("https://example.gov.uk/live", "body"))
    assert live["is_withdrawn"] is False
    withdrawn = _page("https://example.gov.uk/old", "body")
    withdrawn["meta_data"]["is_withdrawn"] = True
    assert page_ref(withdrawn)["is_withdrawn"] is True


def test_stamps_every_drop_stage_across_both_passes():
    missing = _page("https://example.gov.uk/missing", None, "Missing")
    missing["meta_data"]["fetch_error"] = {"http_status": 404}
    empty = _page("https://example.gov.uk/empty", "", "Empty")
    miss = _page("https://example.gov.uk/passport", "How to renew a passport.", "Passports")
    hit = "Guidance on catch certificates for fishery product exports."
    p1_false = _page("https://example.gov.uk/aquarium", hit, "Aquarium")
    p2_drop = _page("https://example.gov.uk/drop", hit, "Drop")
    p2_keep = _page("https://example.gov.uk/keep", hit, "Keep")
    items = [missing, empty, miss, p1_false, p2_drop, p2_keep]

    results, stats = classify(
        items, BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
        completions=llm(FISH_FALSE, FISH_TRUE, FISH_TRUE),
    )
    assert stats["n_missing_body"] == 1
    assert stats["n_empty_body"] == 1
    assert stats["n_skipped"] == 1
    assert stats["n_routed"] == 3
    assert stats["n_pass1_false"] == 1
    assert stats["n_pass1_true"] == 2
    by_url = {r["url"]: r["meta_data"]["funnel"]["stage"] for r in results}
    assert by_url[missing["url"]] == MISSING_BODY
    assert by_url[empty["url"]] == EMPTY_BODY
    assert by_url[miss["url"]] == LEXICON_MISS
    assert by_url[p1_false["url"]] == PASS1_FALSE
    assert results[0]["meta_data"]["funnel"]["fetch_error"] == {"http_status": 404}
    assert results[3]["meta_data"]["funnel"]["pass1_reason"] == "incidental aquarium mention"

    results, adj, audit = adjudicate(
        items, results, BAKED_IN_CATEGORIES,
        completions=llm(FISH_DROP, FISH_KEEP),
    )
    assert adj["n_dropped"] == 1 and adj["n_kept"] == 1
    assert {a["url"]: a["stage"] for a in audit} == {
        p2_drop["url"]: PASS2_DROP,
        p2_keep["url"]: PASS2_KEEP,
    }

    stages = stage_counts(results)
    assert stages == {
        MISSING_BODY: 1,
        EMPTY_BODY: 1,
        LEXICON_MISS: 1,
        PASS1_FALSE: 1,
        PASS2_DROP: 1,
        PASS2_KEEP: 1,
    }
    drop = next(r for r in results if r["url"] == p2_drop["url"])
    assert drop["meta_data"]["labels"][FISH_CATEGORY] is False
    assert drop["meta_data"]["funnel"]["pass1_reason"]
    pass1_note = drop["meta_data"]["funnel"]["pass1_reason"]
    assert drop["meta_data"]["reasons"][FISH_CATEGORY] != pass1_note

    doc = journal(
        results, FISH_CATEGORY,
        n_pages=6, n_routed=3, n_pass1_true=2,
    )
    assert doc["counts"]["missing_body"] == 1
    assert doc["counts"]["empty_body"] == 1
    assert doc["counts"]["lexicon_miss"] == 1
    assert doc["counts"]["cosine_miss"] == 0
    assert doc["counts"]["routing_miss"] == 1
    assert doc["cosine_miss"] == []
    assert doc["counts"]["pass1_false"] == 1
    assert doc["counts"]["pass2_dropped"] == 1
    assert doc["counts"]["final_true"] == 1
    assert doc[MISSING_BODY][0]["url"] == missing["url"]
    assert doc[MISSING_BODY][0]["fetch_error"] == {"http_status": 404}
    assert doc[MISSING_BODY][0]["is_withdrawn"] is False
    assert doc[EMPTY_BODY][0]["url"] == empty["url"]
    assert doc[LEXICON_MISS][0]["url"] == miss["url"]
    assert doc[PASS1_FALSE][0]["url"] == p1_false["url"]
    assert doc[PASS2_DROP][0]["exclusion_hit"] == "wrong_domain"
    assert doc[PASS2_KEEP][0]["url"] == p2_keep["url"]
    assert exclusion_hit_counts(results)["wrong_domain"] == 1


def test_journal_lists_cosine_miss_separately_from_lexicon_miss():
    pages = [
        {
            "url": "https://example.gov.uk/lex",
            "meta_data": {"title": "L", "funnel": {"stage": LEXICON_MISS}},
        },
        {
            "url": "https://example.gov.uk/cos",
            "meta_data": {"title": "C", "funnel": {"stage": COSINE_MISS}},
        },
    ]
    doc = journal(pages, "fish", n_pages=2, n_routed=0, n_pass1_true=0)
    assert doc["counts"]["lexicon_miss"] == 1
    assert doc["counts"]["cosine_miss"] == 1
    assert doc["counts"]["routing_miss"] == 2
    assert doc[COSINE_MISS][0]["url"] == "https://example.gov.uk/cos"
    assert doc[LEXICON_MISS][0]["url"] == "https://example.gov.uk/lex"


def test_journal_counts_pass1_false_without_stamps():
    pages = [{"url": "https://example.gov.uk/unstamped", "meta_data": {"labels": {"fish": False}}}]
    doc = journal(
        pages, "fish",
        n_pages=1, n_routed=1, n_pass1_true=0,
    )
    assert doc["counts"]["pass1_false"] == 1
    assert doc[PASS1_FALSE] == []


def test_adjudicate_preserves_stamped_pass1_reason_if_reasons_already_overwritten():
    cat = FISH_CATEGORY
    positive = {
        "url": "https://example.gov.uk/p",
        "content_id": "x",
        "meta_data": {
            "title": "T",
            "labels": {cat: True},
            "scores": {cat: 0.3},
            "reasons": {cat: "already overwritten"},
            "funnel": {
                "stage": "pass1_true",
                "pass1_reason": "original pass-1 note",
                "pass1_label": True,
                "pass1_score": 0.3,
            },
        },
    }
    item = {
        "url": "https://example.gov.uk/p",
        "content_id": "x",
        "meta_data": {"title": "T", "body_text": "fishery product exports"},
    }
    results, _, _ = adjudicate(
        [item], [positive], BAKED_IN_CATEGORIES, completions=llm(FISH_DROP),
    )
    assert results[0]["meta_data"]["funnel"]["pass1_reason"] == "original pass-1 note"
    assert results[0]["meta_data"]["reasons"][cat] != "original pass-1 note"
