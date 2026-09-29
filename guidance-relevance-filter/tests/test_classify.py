"""Guidance Relevance Filter's classifier: word-search routing, bulk labelling, and the
no-silent-fallback contract — exercised offline with FakeCompletions.
"""

import json
from importlib.resources import files

import pytest

from guidance_relevance_filter.classify import (
    ClassificationIncomplete,
    build_prompt,
    classify,
    parse_response,
)

from .fakes import FakeCompletions, llm

SLURRY_CATEGORIES = [{"name": "slurry", "description": "slurry handling and storage"}]
BAKED_IN_CATEGORIES = json.loads((files("guidance_relevance_filter.data") / "categories.json").read_text())
BAKED_IN_LEXICONS = json.loads((files("guidance_relevance_filter.data") / "lexicon.json").read_text())
FISH_CATEGORY = BAKED_IN_CATEGORIES[0]["name"]
FISH_REPLY = (
    f'{{"{FISH_CATEGORY}": true, "{FISH_CATEGORY}_score": 0.9, '
    f'"{FISH_CATEGORY}_reason": "about fishery products"}}'
)


@pytest.mark.parametrize("text, label, score", [
    ('{"slurry": true, "slurry_score": 0.8}', True, 0.8),
    ('```json\n{"slurry": false, "slurry_score": 0.0}\n```', False, 0.0),
    ('{"slurry": true, "slurry_score": 0.7, "slurry_reason": "cut off mid sen', True, 0.7),
    ('{"slurry": true}', True, 1.0),
], ids=["clean", "code-fenced", "truncated", "score defaults to label"])
def test_parses_a_model_reply(text, label, score):
    parsed = parse_response(text, SLURRY_CATEGORIES)
    assert parsed is not None
    labels, scores, _ = parsed
    assert labels["slurry"] is label
    assert scores["slurry"] == score


def test_returns_none_for_an_unparseable_reply():
    assert parse_response("not json at all", SLURRY_CATEGORIES) is None


def test_prompt_omits_the_exclusion_criteria_section():
    prompt = build_prompt("Fishery product exports", "body about fishery products", BAKED_IN_CATEGORIES)
    assert "Exclusion Criteria" not in prompt
    assert "homonym gate" in prompt
    assert "single table cell" in prompt
    assert "Pass 2 drops incidental" in prompt


def test_prompt_marks_excerpts_and_lists_lexicon_hits():
    prompt = build_prompt(
        "CS manual",
        "RP28 roofing for slurry stores",
        SLURRY_CATEGORIES,
        lexicon_hits=["slurry", "slurry stores"],
        excerpts=True,
    )
    assert "windows around lexicon hits" in prompt
    assert "Lexicon hits on this page: slurry, slurry stores" in prompt


def test_routes_when_only_the_title_hits_the_lexicon(build_page):
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="How to apply for an export licence.",
        title="Fish exports",
    )
    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS, completions=llm(FISH_REPLY),
    )
    assert stats["n_routed"] == 1
    assert stats["n_skipped"] == 0
    assert results[0]["meta_data"]["funnel"]["stage"] == "pass1_true"
    assert results[0]["meta_data"]["selection_meta_body"]["hits_per_cat"][FISH_CATEGORY]


def test_skips_a_page_with_no_lexicon_hit_without_calling_the_llm(build_page, capsys):
    page = build_page(
        url="https://example.gov.uk/passport",
        body_text="How to renew a passport.",
        title="Passports",
    )
    results, stats = classify([page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS)
    assert stats["n_skipped"] == 1
    assert stats["n_empty_body"] == 0
    assert stats["n_pages"] == 1
    assert stats["batch"] is None
    assert results[0]["meta_data"]["labels"][FISH_CATEGORY] is False
    assert results[0]["meta_data"]["funnel"]["stage"] == "lexicon_miss"
    err = capsys.readouterr().err
    assert "1 input" in err
    assert "1 lexicon-miss" in err
    assert "0 lexicon-hit" in err


def test_cosine_gate_embeds_title_and_body(monkeypatch, build_page):
    seen: list[list[str]] = []

    def fake_embed(bodies, queries, **_):
        seen.append(bodies)
        return [[0.05]]

    monkeypatch.setattr("guidance_relevance_filter.narrowing._embed_cosine", fake_embed)
    page = build_page(
        url="https://example.gov.uk/passport",
        body_text="How to renew a passport.",
        title="Passports",
    )
    classify([page], BAKED_IN_CATEGORIES, {}, router="cosine", cosine_threshold=0.2)
    assert seen == [["Passports\nHow to renew a passport."]]


def test_cosine_miss_stamps_cosine_miss_and_keeps_the_row(monkeypatch, build_page, capsys):
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._embed_cosine",
        lambda bodies, queries, **_: [[0.05]],
    )
    page = build_page(
        url="https://example.gov.uk/passport",
        body_text="How to renew a passport.",
        title="Passports",
    )
    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, {}, router="cosine", cosine_threshold=0.2,
    )
    assert stats["n_skipped"] == 1
    assert stats["n_routed"] == 0
    assert stats["batch"] is None
    assert len(results) == 1
    md = results[0]["meta_data"]
    assert md["labels"][FISH_CATEGORY] is False
    assert md["funnel"]["stage"] == "cosine_miss"
    assert md["selection_strategy_body"] == "cosine_body"
    assert md["scores"][FISH_CATEGORY] == 0.05
    assert "excluded by cosine_body" in md["reasons"][FISH_CATEGORY]
    assert "0.05" in md["reasons"][FISH_CATEGORY]
    err = capsys.readouterr().err
    assert "1 cosine-miss" in err


def test_cosine_hit_goes_to_the_llm(monkeypatch, build_page):
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._embed_cosine",
        lambda bodies, queries, **_: [[0.9]],
    )
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, {}, router="cosine", completions=llm(FISH_REPLY),
    )
    assert stats["n_routed"] == 1
    assert stats["n_skipped"] == 0
    md = results[0]["meta_data"]
    assert md["labels"][FISH_CATEGORY] is True
    assert md["funnel"]["stage"] == "pass1_true"
    assert md["selection_strategy_body"] == "cosine_body"
    assert md["selection_meta_body"]["scores"][FISH_CATEGORY] == 0.9


def test_score_only_does_not_need_completions(monkeypatch, build_page):
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._embed_cosine",
        lambda bodies, queries, **_: [[0.9]],
    )
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, {}, router="cosine", score_only=True,
    )
    assert stats["score_only"] is True
    assert stats["n_routed"] == 1
    assert stats["n_pass1_true"] == 0
    assert stats["batch"] is None
    md = results[0]["meta_data"]
    assert md["labels"][FISH_CATEGORY] is False
    assert md["funnel"]["stage"] == "pass1_true"
    assert "score-only" in md["reasons"][FISH_CATEGORY]


def test_max_routed_does_not_call_the_llm(build_page):
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS, max_routed=0,
    )
    assert stats["capped"] is True
    assert stats["n_routed"] == 1
    assert stats["n_pass1_true"] == 0
    assert stats["batch"] is None
    md = results[0]["meta_data"]
    assert md["labels"][FISH_CATEGORY] is False
    assert "max-routed" in md["reasons"][FISH_CATEGORY]


def test_max_routed_under_cap_still_calls_the_llm(build_page):
    constructed: list[bool] = []

    class Boom:
        def complete_many(self, *a, **k):
            constructed.append(True)
            raise AssertionError("stop after call")

        def complete_one(self, *a, **k):
            raise AssertionError("rescue not expected")

    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    with pytest.raises(AssertionError, match="stop after call"):
        classify(
            [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
            max_routed=10, completions=Boom(),
        )
    assert constructed == [True]


def test_score_only_ignores_max_routed(build_page):
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    _results, stats = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS, score_only=True, max_routed=0,
    )
    assert stats["capped"] is False
    assert stats["score_only"] is True
    assert stats["n_routed"] == 1
@pytest.mark.parametrize("body_text", ["", "   "], ids=["empty", "whitespace"])
def test_keeps_empty_body_pages_with_explicit_skip_reason(build_page, body_text):
    page = build_page(
        url="https://example.gov.uk/empty",
        body_text=body_text,
        title="Empty",
    )
    results, stats = classify([page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS)
    assert stats["n_empty_body"] == 1
    assert stats.get("n_missing_body", 0) == 0
    assert stats["n_routed"] == 0
    assert stats["n_skipped"] == 0
    assert len(results) == 1
    md = results[0]["meta_data"]
    assert md["labels"][FISH_CATEGORY] is False
    assert "empty body_text" in md["reasons"][FISH_CATEGORY]
    assert md["selection_meta_body"]["strategy"] == "empty_body"
    assert md["funnel"]["stage"] == "empty_body"


def test_keeps_missing_body_pages_distinct_from_empty(build_page):
    page = build_page(
        url="https://example.gov.uk/missing",
        body_text=None,
        title="Missing",
    )
    page["meta_data"]["fetch_error"] = {"http_status": 503, "error": "max retries"}
    results, stats = classify([page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS)
    assert stats["n_missing_body"] == 1
    assert stats["n_empty_body"] == 0
    assert stats["n_routed"] == 0
    md = results[0]["meta_data"]
    assert md["labels"][FISH_CATEGORY] is False
    assert "missing body_text" in md["reasons"][FISH_CATEGORY]
    assert md["selection_meta_body"]["strategy"] == "missing_body"
    assert md["funnel"]["stage"] == "missing_body"
    assert md["funnel"]["fetch_error"]["http_status"] == 503


def test_returns_no_results_for_an_empty_corpus():
    results, _ = classify([], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS)
    assert results == []


def test_labels_a_page_that_hits_the_lexicon(build_page):
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS, completions=llm(FISH_REPLY),
    )
    assert stats["n_routed"] == 1
    assert stats["n_pages"] == 1
    assert stats["batch"]["id"] == "batch-test"
    assert stats["batch"]["submitted"] == 1
    assert stats["batch"]["collected"] == 1
    assert results[0]["meta_data"]["labels"][FISH_CATEGORY] is True
    assert results[0]["meta_data"]["funnel"]["stage"] == "pass1_true"
    assert results[0]["meta_data"]["funnel"]["pass1_label"] is True
    assert "body_text" not in results[0]["meta_data"]
    assert results[0]["meta_data"]["selection_meta_body"]["pass1_input"] == "hit_windows"


def test_pass1_prompt_sends_hit_windows_not_the_full_body(build_page):
    seen: list[str] = []
    padding = "Passport renewal guidance for overseas travel. " * 80
    page = build_page(
        url="https://example.gov.uk/cs-manual",
        title="Countryside Stewardship manual",
        body_text=(
            padding
            + " Annex: catch certificate rules for fishery product exports. "
            + padding
        ),
    )
    results, _ = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
        completions=llm(
            FISH_REPLY,
            on_create=lambda reqs: seen.append(reqs[0].messages[0]["content"]),
        ),
    )
    assert seen
    prompt = seen[0]
    assert "catch certificate" in prompt.lower()
    assert "windows around lexicon hits" in prompt
    assert prompt.count("Passport renewal") < 40
    meta = results[0]["meta_data"]["selection_meta_body"]
    assert meta["pass1_input"] == "hit_windows"
    assert meta["n_windows"] >= 1
    assert meta["window_words"] < meta["original_words"]


def test_title_only_hit_sends_placeholder_not_the_body(build_page):
    seen: list[str] = []
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        title="Fish exports",
        body_text="How to apply for an export licence. " * 40,
    )
    results, _ = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
        completions=llm(
            FISH_REPLY,
            on_create=lambda reqs: seen.append(reqs[0].messages[0]["content"]),
        ),
    )
    prompt = seen[0]
    assert "No inclusion-lexicon hit in the body" in prompt
    assert "export licence" not in prompt
    assert results[0]["meta_data"]["selection_meta_body"]["title_hit_only"] is True


def test_cosine_pass1_sends_the_full_body(monkeypatch, build_page):
    seen: list[str] = []
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._embed_cosine",
        lambda bodies, queries, **_: [[0.9]],
    )
    padding = "Passport renewal guidance for overseas travel. " * 40
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        title="Fishery exports",
        body_text=padding,
    )
    results, _ = classify(
        [page], BAKED_IN_CATEGORIES, {}, router="cosine",
        completions=llm(
            FISH_REPLY,
            on_create=lambda reqs: seen.append(reqs[0].messages[0]["content"]),
        ),
    )
    prompt = seen[0]
    assert padding[:40] in prompt
    assert "windows around lexicon hits" not in prompt
    assert results[0]["meta_data"]["selection_meta_body"]["pass1_input"] == "full_body"


def test_rescue_uses_hit_windows_not_the_document_head(build_page):
    prompts: list[str] = []

    def capture(req):
        prompts.append(req.messages[0]["content"])
        return FISH_REPLY

    padding = "Passport renewal guidance for overseas travel. " * 80
    page = build_page(
        url="https://example.gov.uk/cs-manual",
        title="Countryside Stewardship manual",
        body_text=padding + " Annex: catch certificate rules for fishery product exports.",
    )
    classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
        completions=FakeCompletions({}, rescue=capture),
    )
    assert prompts
    assert "catch certificate" in prompts[0].lower()
    assert prompts[0].count("Passport renewal") < 40


def test_rescues_a_page_the_batch_dropped(build_page):
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
        completions=FakeCompletions({}, rescue=lambda: FISH_REPLY),
    )
    assert stats["n_rescued"] == 1
    assert stats["n_batch_missing"] == 1
    assert stats["batch"]["submitted"] == 1
    assert stats["batch"]["collected"] == 0
    assert results[0]["meta_data"]["labels"][FISH_CATEGORY] is True


def test_notes_the_truncation_when_rescuing_an_oversized_body(build_page):
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="fishery products " * 100,
        title="Fishery exports",
    )
    results, _ = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS, max_words=5,
        completions=FakeCompletions({}, rescue=lambda: FISH_REPLY),
    )
    reason = results[0]["meta_data"]["reasons"][FISH_CATEGORY]
    assert reason.startswith("[body truncated to 5 words from 200]")


@pytest.mark.parametrize("rescue", [
    lambda: "not json at all",
    lambda: None,
], ids=["unparseable reply", "api error"])
def test_raises_rather_than_labelling_a_page_it_cannot_classify(build_page, rescue):
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    with pytest.raises(ClassificationIncomplete):
        classify(
            [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
            completions=FakeCompletions({}, rescue=rescue),
        )


def test_reattaches_to_a_checkpointed_batch_instead_of_creating(tmp_path, build_page):
    from guidance_relevance_filter.checkpoint import Checkpoint

    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    cp = Checkpoint(tmp_path / "checkpoint.json")
    cp.init({"tag": "test"}, "2026-01-01T00:00:00")
    cp.record_pass1_routing([page["url"]])
    cp.record_pass1_batch("batch-test")

    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS, checkpoint=cp,
        completions=llm(
            FISH_REPLY,
            on_create=lambda _reqs: (_ for _ in ()).throw(AssertionError("must not create")),
        ),
    )
    assert stats["resumed"] is True
    assert stats["batch"]["id"] == "batch-test"
    assert results[0]["meta_data"]["labels"][FISH_CATEGORY] is True


def test_refuses_to_reattach_when_routed_urls_changed(tmp_path, build_page):
    from guidance_relevance_filter.checkpoint import Checkpoint, ResumeIncompatible

    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    cp = Checkpoint(tmp_path / "checkpoint.json")
    cp.init({"tag": "test"}, "2026-01-01T00:00:00")
    cp.record_pass1_routing(["https://example.gov.uk/SOME-OTHER-PAGE"])
    cp.record_pass1_batch("batch-test")

    with pytest.raises(ResumeIncompatible, match="routed_urls changed"):
        classify(
            [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS, checkpoint=cp,
            completions=llm(FISH_REPLY),
        )


def test_on_progress_ticks_scan_then_wordsearch(build_page):
    ticks = []
    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    classify(
        [page], BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
        score_only=True,
        on_progress=lambda phase, done, total: ticks.append((phase, done, total)),
    )
    assert ticks[0] == ("scan", 0, 1)
    assert ("scan", 1, 1) in ticks
    assert ("wordsearch", 0, 1) in ticks
    assert ticks[-1] == ("wordsearch", 1, 1)


def test_classify_cosine_uses_embed_cache(build_page, monkeypatch):
    from guidance_relevance_filter.narrowing import DEFAULT_EMBED_MODEL, EmbedCache

    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    cache = EmbedCache("deadbeef", DEFAULT_EMBED_MODEL)
    cache.put(page["url"], [1.0, 0.0])

    def boom(*_a, **_k):
        raise AssertionError("document encode should not run when the URL is cached")

    monkeypatch.setattr("guidance_relevance_filter.narrowing._embed_cosine", boom)
    monkeypatch.setattr("guidance_relevance_filter.classify._encode_documents", boom)
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._score_page_embeddings",
        lambda page_embeddings, queries, **_: [[0.9]],
    )
    results, stats = classify(
        [page], BAKED_IN_CATEGORIES, {},
        router="cosine", score_only=True, embed_cache=cache,
    )
    assert stats["n_routed"] == 1
    assert results[0]["meta_data"]["funnel"]["stage"] == "pass1_true"
    assert results[0]["meta_data"]["scores"][FISH_CATEGORY] == 0.9


def test_classify_cosine_encodes_cache_miss_only(monkeypatch):
    from guidance_relevance_filter.narrowing import DEFAULT_EMBED_MODEL, EmbedCache

    hit = {
        "url": "https://example.gov.uk/cached",
        "content_id": "a",
        "meta_data": {"title": "Cached", "body_text": "already embedded"},
    }
    miss = {
        "url": "https://example.gov.uk/fresh",
        "content_id": "b",
        "meta_data": {"title": "Fresh", "body_text": "needs an encode"},
    }
    cache = EmbedCache("deadbeef", DEFAULT_EMBED_MODEL)
    cache.put(hit["url"], [1.0, 0.0])
    encoded: list[list[str]] = []

    def fake_encode(bodies, **_):
        encoded.append(bodies)
        return [[0.0, 1.0] for _ in bodies]

    monkeypatch.setattr("guidance_relevance_filter.classify._encode_documents", fake_encode)
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._score_page_embeddings",
        lambda page_embeddings, queries, **_: [[0.1], [0.9]],
    )
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._embed_cosine",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("full encode should not run when a cache is present")
        ),
    )
    results, stats = classify(
        [hit, miss], BAKED_IN_CATEGORIES, {},
        router="cosine", score_only=True, embed_cache=cache,
    )
    assert encoded == [["Fresh\nneeds an encode"]]
    assert cache.get(miss["url"]) == [0.0, 1.0]
    assert stats["n_routed"] == 1
    assert results[1]["meta_data"]["funnel"]["stage"] == "pass1_true"


def test_classify_wordsearch_uses_stem_index(build_page, tmp_path, monkeypatch):
    import json

    from guidance_relevance_filter.narrowing import load_or_build_stem_index

    page = build_page(
        url="https://example.gov.uk/fishery-exports",
        body_text="Guidance on catch certificates for fishery product exports.",
        title="Fishery exports",
    )
    json_path = tmp_path / "pages.json"
    json_path.write_text(json.dumps([page]))
    index = load_or_build_stem_index(
        json_path, corpus_sha256="deadbeef", path=tmp_path / "index.sqlite",
    )

    def boom(_text):
        raise AssertionError("stem_index should not run when the inverted index is used")

    monkeypatch.setattr("guidance_relevance_filter.classify.stem_index", boom)
    results, stats = classify(
        index.catalog_items(), BAKED_IN_CATEGORIES, BAKED_IN_LEXICONS,
        score_only=True, stem_index_db=index,
    )
    assert stats["n_routed"] == 1
    assert results[0]["meta_data"]["funnel"]["stage"] == "pass1_true"
    index.close()
