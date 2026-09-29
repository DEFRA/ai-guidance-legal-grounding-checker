import pytest

from conftest import _page, write_snapshot
from guidance_relevance_web.corpus import CorpusCatalog, CorpusError, UnknownCorpus, format_built_on


def test_format_built_on():
    assert format_built_on("2026-09-08") == "8 September 2026"
    assert format_built_on("2026-09-10") == "10 September 2026"
    assert format_built_on("unknown") == "unknown"
    assert format_built_on("") == "unknown"


def test_catalog_lists_flat_root(corpus_dir):
    catalog = CorpusCatalog(corpus_dir)
    snaps = catalog.list()
    assert len(snaps) == 1
    assert snaps[0].built_on == "2026-09-08"
    assert snaps[0].n_pages == 4
    assert snaps[0].root == corpus_dir.resolve()
    newest = catalog.get(None)
    assert newest.pages_path == corpus_dir.resolve() / "with_body.json"
    assert newest.require().n_pages == 4


def test_catalog_lists_root_and_child_newest_first(library_dir):
    catalog = CorpusCatalog(library_dir["root"])
    snaps = catalog.list()
    assert [s.built_on for s in snaps] == ["2026-09-10", "2026-09-08"]
    assert snaps[0].id == library_dir["new_sha"]
    assert snaps[1].id == library_dir["old_sha"]
    assert catalog.get(None).pages_path == library_dir["new_root"].resolve() / "with_body.json"
    old = catalog.get(library_dir["old_sha"])
    assert old.pages_path == library_dir["root"].resolve() / "with_body.json"
    assert old.require().n_pages == 4
    assert catalog.get(library_dir["old_sha"]) is old


def test_catalog_skips_stem_index_and_invalid_children(tmp_path):
    root = tmp_path / "lib"
    write_snapshot(root, [_page("https://www.gov.uk/a", "A", "body")], "2026-09-01")
    (root / "stem_index").mkdir()
    (root / "stem_index" / "MANIFEST.json").write_text("{}")
    (root / "stem_index" / "with_body.json").write_text("[]")
    (root / "embed_index").mkdir()
    (root / "embed_index" / "MANIFEST.json").write_text("{}")
    (root / "embed_index" / "with_body.json").write_text("[]")
    empty = root / "empty-dir"
    empty.mkdir()
    broken = root / "broken"
    broken.mkdir()
    (broken / "with_body.json").write_text("[]")
    (broken / "MANIFEST.json").write_text("{")
    catalog = CorpusCatalog(root)
    assert [s.built_on for s in catalog.list()] == ["2026-09-01"]


def test_catalog_unknown_and_empty(tmp_path, library_dir):
    catalog = CorpusCatalog(library_dir["root"])
    with pytest.raises(UnknownCorpus):
        catalog.get("0" * 64)
    empty = CorpusCatalog(tmp_path / "missing")
    assert empty.list() == []
    with pytest.raises(CorpusError, match="No snapshots"):
        empty.get(None)


def test_catalog_peeks_manifest_scope_lists(corpus_dir):
    catalog = CorpusCatalog(corpus_dir)
    snap = catalog.list()[0]
    assert snap.organisations == [
        "department-for-environment-food-rural-affairs",
        "environment-agency",
    ]
    assert snap.document_types == ["detailed_guide", "guide"]
    views = catalog.views()
    assert views[0]["organisations"] == snap.organisations
    assert views[0]["document_types"] == snap.document_types
    org_slugs = {opt[0] for opt in views[0]["organisation_options"]}
    assert org_slugs == set(snap.organisations)


def test_catalog_scope_fallback_from_pages(tmp_path):
    pages = [
        _page(
            "https://www.gov.uk/a",
            "A",
            "body",
            primary="environment-agency",
            organisations=["environment-agency"],
            document_type="guide",
        ),
    ]
    root = tmp_path / "c"
    write_snapshot(root, pages, "2026-09-01", stamp_scope=False)
    catalog = CorpusCatalog(root)
    snap = catalog.list()[0]
    assert snap.organisations is None
    assert snap.document_types is None
    views = catalog.views()
    assert views[0]["organisations"] == []
    assert views[0]["document_types"] == []
    assert catalog.get(None).scope_slugs() == (["environment-agency"], ["guide"])


def test_catalog_views_does_not_build_stem_index(tmp_path, monkeypatch):
    pages = [
        _page(
            "https://www.gov.uk/a",
            "A",
            "body",
            primary="environment-agency",
            organisations=["environment-agency"],
            document_type="guide",
        ),
    ]
    root = tmp_path / "c"
    write_snapshot(root, pages, "2026-09-01", stamp_scope=False)

    def boom(*_a, **_k):
        raise AssertionError("GET / must not stem-build just to fill checkboxes")

    monkeypatch.setattr(
        "guidance_relevance_web.corpus.load_or_build_stem_index", boom,
    )
    views = CorpusCatalog(root).views()
    assert views[0]["organisations"] == []
    assert views[0]["document_types"] == []


def test_catalog_child_wins_on_duplicate_sha(tmp_path):
    pages = [_page("https://www.gov.uk/a", "A", "slurry lagoon")]
    root = tmp_path / "lib"
    sha = write_snapshot(root, pages, "2026-09-01")
    child = root / "2026-09-01-copy"
    write_snapshot(child, pages, "2026-09-01")
    catalog = CorpusCatalog(root)
    snaps = catalog.list()
    assert len(snaps) == 1
    assert snaps[0].id == sha
    assert snaps[0].root == child.resolve()


def test_require_hashes_without_loading_with_body_json(corpus_dir, monkeypatch):
    from pathlib import Path

    from guidance_relevance_web.corpus import Corpus

    orig_read_bytes = Path.read_bytes
    orig_read_text = Path.read_text

    def no_body_bytes(self, *a, **k):
        if self.name == "with_body.json":
            raise AssertionError("must not read_bytes with_body.json")
        return orig_read_bytes(self, *a, **k)

    def no_body_text(self, *a, **k):
        if self.name == "with_body.json":
            raise AssertionError("must not read_text with_body.json")
        return orig_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", no_body_bytes)
    monkeypatch.setattr(Path, "read_text", no_body_text)
    snap = Corpus(corpus_dir)
    assert snap.require().n_pages == 4
