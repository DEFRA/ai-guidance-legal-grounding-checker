"""Word-search and cosine routing: a page reaches the LLM only when the cheap
gate selects its category; otherwise the category is excluded.
"""

import pytest

from guidance_relevance_filter.narrowing import query_text, select_by_cosine, select_categories

CATEGORIES = [{"name": "slurry", "description": "slurry handling and storage"}]
LEXICON = {"slurry": ["Slurry", "Cattle manure"]}


@pytest.mark.parametrize("body, term", [
    ("Guidance on slurry storage and lagoon freeboard.", "Slurry"),
    ("The stored slurries must be covered.", "Slurry"),
    ("Rules covering cattle manures spread on farmland.", "Cattle manure"),
], ids=["unigram", "inflected unigram", "inflected bigram"])
def test_selects_a_category_when_its_lexicon_term_appears(body, term):
    selected, meta = select_categories(body, CATEGORIES, LEXICON)
    assert [c["name"] for c in selected] == ["slurry"]
    assert term in meta["hits_per_cat"]["slurry"]


def test_selects_nothing_when_no_lexicon_term_appears():
    body = "Guidance on passport applications and overseas travel insurance."
    selected, _ = select_categories(body, CATEGORIES, LEXICON)
    assert selected == []


def test_hit_windows_keeps_the_hit_and_drops_distant_padding():
    from guidance_relevance_filter.narrowing import compile_lexicon, hit_windows

    padding = "passport renewal. " * 50
    body = padding + "Cover slurry stores. " + padding
    compiled = compile_lexicon(CATEGORIES, LEXICON)
    excerpt, meta = hit_windows(body, compiled, radius_words=3, max_windows=4)
    assert "slurry" in excerpt.lower()
    assert excerpt.count("passport") < body.count("passport")
    assert meta["n_hits"] >= 1
    assert meta["n_windows"] == 1
    assert meta["window_words"] < meta["original_words"]


def test_hit_windows_empty_when_the_hit_is_not_in_the_body():
    from guidance_relevance_filter.narrowing import compile_lexicon, hit_windows

    compiled = compile_lexicon(CATEGORIES, LEXICON)
    excerpt, meta = hit_windows("passport renewal guidance only.", compiled)
    assert excerpt == ""
    assert meta["n_hits"] == 0
    assert meta["n_windows"] == 0


def test_hit_windows_keeps_head_and_tail_when_over_max():
    from guidance_relevance_filter.narrowing import compile_lexicon, hit_windows

    parts = [
        f"{'zzzz ' * 80} slurry HIT{i} {'yyyy ' * 80}"
        for i in range(6)
    ]
    compiled = compile_lexicon(CATEGORIES, LEXICON)
    excerpt, meta = hit_windows("".join(parts), compiled, radius_words=2, max_windows=4)
    assert meta["n_windows"] == 4
    assert "HIT0" in excerpt and "HIT1" in excerpt
    assert "HIT4" in excerpt and "HIT5" in excerpt
    assert "HIT2" not in excerpt


def test_stem_index_reuses_cached_sets():
    from guidance_relevance_filter.narrowing import stem_index

    body = "Guidance on slurry storage and lagoon freeboard."
    a = stem_index(body)
    b = stem_index(body)
    assert a is b
    selected, _ = select_categories(body, CATEGORIES, LEXICON)
    assert [c["name"] for c in selected] == ["slurry"]


def test_stem_index_roundtrip_and_sha_mismatch(tmp_path):
    import json

    from guidance_relevance_filter.narrowing import (
        StemIndex,
        compile_lexicon,
        load_or_build_stem_index,
    )

    items = [{
        "url": "https://example.gov.uk/slurry",
        "meta_data": {
            "title": "Slurry storage",
            "body_text": "Guidance on slurry storage and lagoon freeboard.",
        },
    }]
    json_path = tmp_path / "pages.json"
    json_path.write_text(json.dumps(items))
    path = tmp_path / "stem_index" / "abc.sqlite"
    index = load_or_build_stem_index(json_path, corpus_sha256="abc", path=path)
    assert path.is_file()
    assert not hasattr(index, "_pages")
    loaded = StemIndex.open(path, "abc")
    assert loaded is not None
    assert StemIndex.open(path, "other-sha") is None
    hits = loaded.match(compile_lexicon(CATEGORIES, LEXICON))
    assert len(hits) == 1
    meta = next(iter(hits.values()))
    assert "Slurry" in meta["hits_per_cat"]["slurry"]
    loaded.close()
    index.close()


def test_stem_index_uses_delete_journal_not_wal(tmp_path):
    import json

    from guidance_relevance_filter.narrowing import StemIndex, load_or_build_stem_index

    items = [{
        "url": "https://example.gov.uk/slurry",
        "meta_data": {"title": "Slurry", "body_text": "slurry stores"},
    }]
    json_path = tmp_path / "pages.json"
    json_path.write_text(json.dumps(items))
    path = tmp_path / "idx.sqlite"
    index = load_or_build_stem_index(json_path, corpus_sha256="s", path=path)
    mode = index._conn.execute("PRAGMA journal_mode").fetchone()[0]
    index.close()
    assert str(mode).lower() == "delete"
    assert not path.with_name(path.name + "-wal").exists()
    path.with_name(path.name + "-wal").write_bytes(b"garbage")
    path.with_name(path.name + "-shm").write_bytes(b"garbage")
    reopened = StemIndex.open(path, "s")
    assert reopened is not None
    assert len(reopened) == 1
    reopened.close()


def test_stem_index_match_matches_match_compiled(tmp_path):
    import json

    from guidance_relevance_filter.narrowing import (
        compile_lexicon,
        load_or_build_stem_index,
        match_compiled,
        searchable_text,
        stem_index,
    )

    items = [
        {
            "url": "https://example.gov.uk/slurry",
            "meta_data": {
                "title": "Slurry storage",
                "body_text": "Guidance on slurry storage and lagoon freeboard.",
                "document_type": "guide",
                "organisations": ["environment-agency"],
                "primary_publishing_organisation": "environment-agency",
            },
        },
        {
            "url": "https://example.gov.uk/passports",
            "meta_data": {
                "title": "Passports",
                "body_text": "Guidance on passport applications.",
            },
        },
        {
            "url": "https://example.gov.uk/empty",
            "meta_data": {"title": "Empty", "body_text": ""},
        },
        {
            "url": "https://example.gov.uk/missing",
            "meta_data": {"title": "Missing", "body_text": None},
        },
    ]
    json_path = tmp_path / "pages.json"
    json_path.write_text(json.dumps(items))
    path = tmp_path / "index.sqlite"
    index = load_or_build_stem_index(json_path, corpus_sha256="s", path=path)
    compiled = compile_lexicon(CATEGORIES, LEXICON)
    hits = index.match(compiled)
    id_by_url = index.url_ids()
    for item in items:
        url = item["url"]
        pid = id_by_url[url]
        raw = (item["meta_data"] or {}).get("body_text")
        if raw is None or not str(raw).strip():
            assert pid not in hits
            continue
        uni, bi = stem_index(searchable_text(
            item["meta_data"]["title"], str(raw),
        ))
        selected, meta = match_compiled(uni, bi, compiled)
        if selected:
            assert hits[pid]["hits_per_cat"] == meta["hits_per_cat"]
        else:
            assert pid not in hits
    assert not hasattr(index, "_pages")
    index.close()


def test_load_or_build_does_not_restem_on_hit(tmp_path, monkeypatch):
    import json

    from guidance_relevance_filter.narrowing import compile_lexicon, load_or_build_stem_index

    items = [{
        "url": "https://example.gov.uk/slurry",
        "meta_data": {"title": "Slurry", "body_text": "slurry stores and lagoons"},
    }]
    json_path = tmp_path / "pages.json"
    json_path.write_text(json.dumps(items))
    path = tmp_path / "cache.sqlite"
    first = load_or_build_stem_index(json_path, corpus_sha256="s", path=path)

    def boom(_text):
        raise AssertionError("tokenize_and_stem should not run on a disk cache hit")

    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing.tokenize_and_stem", boom,
    )
    second = load_or_build_stem_index(json_path, corpus_sha256="s", path=path)
    assert second.path == first.path
    assert len(second.match(compile_lexicon(CATEGORIES, LEXICON))) == 1
    first.close()
    second.close()


def test_resolve_stem_index_path_sqlite_dir_and_pkl():
    from pathlib import Path

    from guidance_relevance_filter.narrowing import resolve_stem_index_path

    inp = Path("/data/corpus/with_body.json")
    sha = "abc123"
    assert resolve_stem_index_path(inp, sha) == Path(
        "/data/corpus/stem_index/abc123.sqlite"
    )
    assert resolve_stem_index_path(inp, sha, Path("/x/idx.sqlite")) == Path(
        "/x/idx.sqlite"
    )
    assert resolve_stem_index_path(inp, sha, Path("/x/old.pkl")) == Path(
        "/x/old.sqlite"
    )
    assert resolve_stem_index_path(inp, sha, Path("/x")) == Path(
        "/x/abc123.sqlite"
    )


def test_cosine_selects_when_score_meets_threshold(monkeypatch):
    bodies = ["about slurry stores", "about passports"]

    def fake_embed(bodies_in, queries, **_):
        assert bodies_in == bodies
        assert queries == ["slurry handling and storage"]
        return [[0.5], [0.1]]

    monkeypatch.setattr("guidance_relevance_filter.narrowing._embed_cosine", fake_embed)
    decisions = select_by_cosine(bodies, CATEGORIES, threshold=0.2)
    assert [bool(sel) for sel, _meta in decisions] == [True, False]
    hit_sel, hit_meta = decisions[0]
    miss_sel, miss_meta = decisions[1]
    assert [c["name"] for c in hit_sel] == ["slurry"]
    assert miss_sel == []
    assert hit_meta["strategy"] == "cosine_body"
    assert hit_meta["threshold"] == 0.2
    assert hit_meta["scores"]["slurry"] == 0.5
    assert miss_meta["scores"]["slurry"] == 0.1


def test_cosine_keeps_at_exact_threshold(monkeypatch):
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._embed_cosine",
        lambda bodies, queries, **_: [[0.2]],
    )
    selected, meta = select_by_cosine(["body"], CATEGORIES, threshold=0.2)[0]
    assert selected == CATEGORIES
    assert meta["scores"]["slurry"] == 0.2


def test_embedding_query_preferred_over_description(monkeypatch):
    cats = [{
        "name": "slurry",
        "description": "LONG INCLUSION SPEC not for embedding",
        "embedding_query": "slurry manure storage",
    }]
    seen: list[list[str]] = []

    def fake_embed(bodies, queries, **_):
        seen.append(queries)
        return [[0.9]]

    monkeypatch.setattr("guidance_relevance_filter.narrowing._embed_cosine", fake_embed)
    select_by_cosine(["body"], cats, threshold=0.2)
    assert seen == [["slurry manure storage"]]


def test_query_text_falls_back_to_description():
    assert query_text({"name": "fish", "description": "seafood"}) == "seafood"
    assert query_text({
        "name": "fish", "description": "seafood", "embedding_query": "fish trade",
    }) == "fish trade"


def test_select_by_cosine_empty_bodies():
    assert select_by_cosine([], CATEGORIES) == []


def test_select_by_cosine_uses_cached_page_embeddings(monkeypatch):
    seen: list[str] = []

    def boom(*_a, **_k):
        raise AssertionError("document encode should not run when vectors are cached")

    def fake_score(page_embeddings, queries, **_):
        seen.append("scored")
        assert page_embeddings == [[1.0, 0.0]]
        assert queries == ["slurry handling and storage"]
        return [[0.4]]

    monkeypatch.setattr("guidance_relevance_filter.narrowing._embed_cosine", boom)
    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._score_page_embeddings", fake_score,
    )
    selected, meta = select_by_cosine(
        ["body"], CATEGORIES, threshold=0.2, page_embeddings=[[1.0, 0.0]],
    )[0]
    assert selected == CATEGORIES
    assert meta["scores"]["slurry"] == 0.4
    assert seen == ["scored"]


def test_embed_cache_roundtrip_and_mismatch(tmp_path, monkeypatch):
    from guidance_relevance_filter.narrowing import (
        DEFAULT_EMBED_MODEL,
        EmbedCache,
        load_or_build_embed_cache,
    )

    items = [{
        "url": "https://example.gov.uk/slurry",
        "meta_data": {
            "title": "Slurry storage",
            "body_text": "Guidance on slurry storage and lagoon freeboard.",
        },
    }]

    def fake_encode(bodies, **_):
        assert bodies == ["Slurry storage\nGuidance on slurry storage and lagoon freeboard."]
        return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._encode_documents", fake_encode,
    )
    path = tmp_path / "embed_index" / "abc__nomic-ai-nomic-embed-text-v1.5.pkl"
    cache = load_or_build_embed_cache(
        items, corpus_sha256="abc", embed_model=DEFAULT_EMBED_MODEL, path=path,
    )
    assert path.is_file()
    assert cache.get(items[0]["url"]) == pytest.approx([0.1, 0.2, 0.3], abs=1e-6)
    loaded = EmbedCache.try_load(path, "abc", DEFAULT_EMBED_MODEL)
    assert loaded is not None
    assert loaded.get(items[0]["url"]) == pytest.approx([0.1, 0.2, 0.3], abs=1e-6)
    assert EmbedCache.try_load(path, "other-sha", DEFAULT_EMBED_MODEL) is None
    assert EmbedCache.try_load(path, "abc", "other/model") is None


def test_load_or_build_does_not_reembed_on_hit(tmp_path, monkeypatch):
    from guidance_relevance_filter.narrowing import (
        DEFAULT_EMBED_MODEL,
        load_or_build_embed_cache,
    )

    items = [{
        "url": "https://example.gov.uk/slurry",
        "meta_data": {"title": "Slurry", "body_text": "slurry stores and lagoons"},
    }]
    path = tmp_path / "cache.pkl"
    calls = {"n": 0}

    def fake_encode(bodies, **_):
        calls["n"] += 1
        return [[0.5, 0.25]]

    monkeypatch.setattr(
        "guidance_relevance_filter.narrowing._encode_documents", fake_encode,
    )
    first = load_or_build_embed_cache(
        items, corpus_sha256="s", embed_model=DEFAULT_EMBED_MODEL, path=path,
    )
    assert calls["n"] == 1

    def boom(*_a, **_k):
        raise AssertionError("document encode should not run on a disk cache hit")

    monkeypatch.setattr("guidance_relevance_filter.narrowing._encode_documents", boom)
    second = load_or_build_embed_cache(
        items, corpus_sha256="s", embed_model=DEFAULT_EMBED_MODEL, path=path,
    )
    assert second.get(items[0]["url"]) == pytest.approx(
        first.get(items[0]["url"]) or [], abs=1e-6,
    )


def test_embed_index_path_uses_sha_and_model_slug():
    from pathlib import Path

    from guidance_relevance_filter.narrowing import embed_index_path

    path = embed_index_path(
        Path("/data/corpus/with_body.json"),
        "abc123",
        "nomic-ai/nomic-embed-text-v1.5",
    )
    assert path == Path(
        "/data/corpus/embed_index/abc123__nomic-ai-nomic-embed-text-v1.5.pkl"
    )
