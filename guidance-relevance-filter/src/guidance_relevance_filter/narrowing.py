"""Cheap-gate routing: decide which pages reach the LLM.

Two strategies, same return shape ``(selected_categories, selection_meta)``:

- **wordsearch_binary** (default): a page is selected iff the searchable
  text (title + body) hits the curated inclusion lexicon, Porter-stemmed.
  Unigram and bigram only — a lexicon term that stems to three or more
  tokens cannot match.
- **cosine_body**: batch-embed searchable text against the category query
  (``embedding_query`` if set, else ``description``) with nomic-embed-text.
  Selected iff cosine ≥ threshold. Page vectors are cached under
  ``embed_index/<corpus-sha>__<model>.pkl`` so later runs only encode the query.

There are NO silent fallbacks: the caller records an explicit miss verdict on
the pages this module routes away.
"""
from __future__ import annotations

import array
import hashlib
import os
import pickle
import re
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

import ijson
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

# Self-bootstrap the one NLTK corpus we use (the tokenizer is a plain regex, so
# punkt is not needed). First run downloads it; subsequent runs find it cached.
try:
    nltk.data.find("corpora/stopwords")
except LookupError:
    nltk.download("stopwords", quiet=True)

_STEMMER = PorterStemmer()
_STOPWORDS = set(stopwords.words("english"))
_TOKEN_RE = re.compile(r"[a-z][a-z\-]+")
# Process-local: sha256(text) → (unigrams, bigrams). Survives a request, not a process.
# Tiny in-memory classify / select_categories only — the corpus builder must not use it.
_STEM_INDEX: dict[str, tuple[set[str], set[tuple[str, str]]]] = {}
STEM_INDEX_VERSION = 2
EMBED_CACHE_VERSION = 1
_HASH_CHUNK = 1024 * 1024
_EMBED_BATCH = 64
_SLUG_SEP = re.compile(r"[\s_]+")
_BUILD_FLUSH = 400
_SQLITE_CACHE_KIB = -16000

DEFAULT_EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
DEFAULT_COSINE_THRESHOLD = 0.2
ROUTER_WORDSEARCH = "wordsearch"
ROUTER_COSINE = "cosine"
DOCUMENT_PROMPT = "search_document: "
QUERY_PROMPT = "search_query: "


class CosineRouterUnavailable(RuntimeError):
    """Raised when cosine routing is requested but sentence-transformers is missing."""


def tokenize_and_stem(text: str) -> list[str]:
    """Lowercase, regex-tokenise, drop English stopwords, Porter-stem."""
    raw = _TOKEN_RE.findall(text.lower())
    return [_STEMMER.stem(t) for t in raw if t not in _STOPWORDS]


def searchable_text(title: str, body: str) -> str:
    """Title then body — the cheap gate searches both."""
    title = (title or "").strip()
    return f"{title}\n{body}" if title else body


def sha256_file(path: Path) -> str:
    """Stream a file's sha256 so we don't hold the whole corpus in a second buffer."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def stem_index_path(input_path: Path, corpus_sha256: str) -> Path:
    """Default on-disk cache: ``<input-dir>/stem_index/<corpus-sha256>.sqlite``."""
    return input_path.parent / "stem_index" / f"{corpus_sha256}.sqlite"


def resolve_stem_index_path(
    input_path: Path, corpus_sha256: str, stem_index: Path | None = None,
) -> Path:
    """Resolve ``--stem-index``: a ``.sqlite`` file, a directory, or the default."""
    if stem_index is None:
        return stem_index_path(input_path, corpus_sha256)
    if stem_index.suffix == ".sqlite":
        return stem_index
    if stem_index.suffix == ".pkl":
        return stem_index.with_suffix(".sqlite")
    return stem_index / f"{corpus_sha256}.sqlite"


def norm_slug(value: str) -> str:
    """Kebab-case a GOV.UK organisation / document-type slug."""
    return _SLUG_SEP.sub("-", (value or "").strip().lower()).strip("-")


def iter_json_items(path: Path) -> Iterable[dict]:
    """Yield each object in a top-level JSON array without loading the file."""
    with path.open("rb") as fh:
        for item in ijson.items(fh, "item"):
            if isinstance(item, dict):
                yield item


def extract_items_by_url(path: Path, urls: set[str]) -> dict[str, dict]:
    """Stream ``path`` and return the full page objects for ``urls``."""
    if not urls:
        return {}
    found: dict[str, dict] = {}
    for item in iter_json_items(path):
        url = str(item.get("url") or "")
        if url in urls:
            found[url] = item
            if len(found) == len(urls):
                break
    return found


def stem_sets(text: str) -> tuple[set[str], set[tuple[str, str]]]:
    """Unigram/bigram stem sets — not cached. Use this in the corpus builder."""
    body_stems = tokenize_and_stem(text)
    return set(body_stems), set(zip(body_stems, body_stems[1:], strict=False))


def embed_model_slug(model: str) -> str:
    """Filesystem-safe model id (``nomic-ai/nomic-embed-text-v1.5`` → dashes)."""
    return model.replace("/", "-")


def embed_index_path(input_path: Path, corpus_sha256: str, embed_model: str) -> Path:
    """Default on-disk cache: ``<input-dir>/embed_index/<sha>__<model-slug>.pkl``."""
    return (
        input_path.parent / "embed_index"
        / f"{corpus_sha256}__{embed_model_slug(embed_model)}.pkl"
    )


def stem_index(text: str) -> tuple[set[str], set[tuple[str, str]]]:
    """Unigram/bigram stem sets for wordsearch, cached by sha256 of ``text``."""
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    cached = _STEM_INDEX.get(digest)
    if cached is not None:
        return cached
    body_stems = tokenize_and_stem(text)
    unigrams = set(body_stems)
    bigrams = set(zip(body_stems, body_stems[1:], strict=False))
    _STEM_INDEX[digest] = (unigrams, bigrams)
    return unigrams, bigrams


def stem_term(term: str) -> str | tuple[str, ...] | None:
    """Return a stemmed unigram, a stemmed n-gram tuple, or None if empty."""
    parts = _TOKEN_RE.findall(term.lower())
    parts = [_STEMMER.stem(p) for p in parts if p not in _STOPWORDS]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return tuple(parts)


CompiledTerm = tuple[str, str | tuple[str, ...]]
CompiledLexicon = list[tuple[dict, list[CompiledTerm]]]


def compile_lexicon(
    categories: list[dict],
    lexicons: dict[str, list[str]],
) -> CompiledLexicon:
    """Stem each lexicon term once — not once per page."""
    compiled: CompiledLexicon = []
    for cat in categories:
        terms: list[CompiledTerm] = []
        for term in lexicons.get(cat["name"], []):
            stemmed = stem_term(term)
            if stemmed is not None:
                terms.append((term, stemmed))
        compiled.append((cat, terms))
    return compiled


def match_compiled(
    unigrams: set[str],
    bigrams: set[tuple[str, str]],
    compiled: CompiledLexicon,
) -> tuple[list[dict], dict]:
    """Lexicon match against pre-stemmed unigram/bigram sets."""
    hits_per_cat: dict[str, list[str]] = {}
    selected: list[dict] = []
    for cat, terms in compiled:
        hits: list[str] = []
        for term, stemmed in terms:
            if isinstance(stemmed, str):
                if stemmed in unigrams:
                    hits.append(term)
            elif len(stemmed) == 2 and stemmed in bigrams:
                # Only bigrams route; 3+ token terms can never match (see module docstring).
                hits.append(term)
        if hits:
            hits_per_cat[cat["name"]] = hits
            selected.append(cat)
    return selected, {"strategy": "wordsearch_binary", "hits_per_cat": hits_per_cat}


HIT_WINDOW_RADIUS_WORDS = 80
HIT_WINDOW_MAX = 12
HIT_WINDOW_JOIN = "\n\n[…]\n\n"
_WS_WORD_RE = re.compile(r"\S+")


def _stemmed_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, stem) for each non-stopword token, same rules as ``stem_index``."""
    spans: list[tuple[int, int, str]] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        raw = m.group(0)
        if raw in _STOPWORDS:
            continue
        spans.append((m.start(), m.end(), _STEMMER.stem(raw)))
    return spans


def _compiled_terms_for_hits(
    compiled: CompiledLexicon,
    hits_per_cat: dict[str, list[str]] | None,
) -> list[CompiledTerm]:
    terms: list[CompiledTerm] = []
    for cat, cat_terms in compiled:
        allowed = None if hits_per_cat is None else set(hits_per_cat.get(cat["name"]) or [])
        for term, stemmed in cat_terms:
            if allowed is not None and term not in allowed:
                continue
            terms.append((term, stemmed))
    return terms


def _lexicon_char_spans(
    spans: list[tuple[int, int, str]],
    terms: list[CompiledTerm],
) -> list[tuple[int, int]]:
    wanted_uni = {stemmed for _term, stemmed in terms if isinstance(stemmed, str)}
    wanted_bi = {
        stemmed for _term, stemmed in terms
        if isinstance(stemmed, tuple) and len(stemmed) == 2
    }
    out: list[tuple[int, int]] = []
    for i, (start, end, stem) in enumerate(spans):
        if stem in wanted_uni:
            out.append((start, end))
        if i + 1 < len(spans) and (stem, spans[i + 1][2]) in wanted_bi:
            out.append((start, spans[i + 1][1]))
    return out


def _expand_to_words(text: str, start: int, end: int, radius: int) -> tuple[int, int]:
    words = list(_WS_WORD_RE.finditer(text))
    if not words:
        return 0, len(text)
    i = 0
    while i < len(words) and words[i].end() <= start:
        i += 1
    if i >= len(words):
        i = len(words) - 1
    j = i
    while j < len(words) and words[j].start() < end:
        j += 1
    j = max(j - 1, i)
    i = max(i - radius, 0)
    j = min(j + radius, len(words) - 1)
    return words[i].start(), words[j].end()


def _merge_ranges(ranges: list[tuple[int, int]], gap: int = 40) -> list[tuple[int, int]]:
    if not ranges:
        return []
    ranges = sorted(ranges)
    out = [ranges[0]]
    for start, end in ranges[1:]:
        prev_s, prev_e = out[-1]
        if start <= prev_e + gap:
            out[-1] = (prev_s, max(prev_e, end))
        else:
            out.append((start, end))
    return out


def _pick_windows(
    ranges: list[tuple[int, int]], max_windows: int
) -> list[tuple[int, int]]:
    """Keep the first half and last remainder so annex hits at the end survive."""
    if len(ranges) <= max_windows:
        return ranges
    head = max(max_windows // 2, 1)
    tail = max_windows - head
    if tail <= 0:
        return ranges[:max_windows]
    return ranges[:head] + ranges[-tail:]


def hit_windows(
    body: str,
    compiled: CompiledLexicon,
    *,
    hits_per_cat: dict[str, list[str]] | None = None,
    radius_words: int = HIT_WINDOW_RADIUS_WORDS,
    max_windows: int = HIT_WINDOW_MAX,
) -> tuple[str, dict]:
    """Excerpt ``body`` to windows around stemmed lexicon hits.

    Used so pass 1 sees a table-cell hit in a 100-page CS manual instead of
    the surrounding 60k words. Overlapping windows merge. If there are more
    hits than ``max_windows``, the first half and last remainder are kept
    (annexes tend to sit at the end). Returns ``("", meta)`` when the body
    itself has no hit (title-only routing).
    """
    original_words = len(body.split())
    terms = _compiled_terms_for_hits(compiled, hits_per_cat)
    spans = _lexicon_char_spans(_stemmed_spans(body), terms)
    empty_meta = {
        "n_hits": 0,
        "n_windows": 0,
        "original_words": original_words,
        "window_words": 0,
    }
    if not spans:
        return "", empty_meta
    expanded = [_expand_to_words(body, s, e, radius_words) for s, e in spans]
    merged = _merge_ranges(expanded)
    chosen = _pick_windows(merged, max_windows)
    excerpt = HIT_WINDOW_JOIN.join(body[s:e] for s, e in chosen)
    return excerpt, {
        "n_hits": len(spans),
        "n_windows": len(chosen),
        "original_words": original_words,
        "window_words": len(excerpt.split()),
    }


def select_categories(
    body_text: str,
    categories: list[dict],
    lexicons: dict[str, list[str]],
) -> tuple[list[dict], dict]:
    """Return ``(selected_categories, selection_meta)`` for word-search routing.

    A category is selected iff any of its stemmed lexicon terms (unigram or
    bigram) appears in the stemmed body. ``selection_meta`` records, per
    selected category, which original lexicon terms hit — so a run can always be
    explained. Only presence matters, so the body is reduced to a set of its
    unigrams and bigrams.
    """
    unigrams, bigrams = stem_index(body_text)
    return match_compiled(unigrams, bigrams, compile_lexicon(categories, lexicons))


_SCHEMA = """
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE pages (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  content_id TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  document_type TEXT NOT NULL DEFAULT '',
  primary_organisation TEXT NOT NULL DEFAULT '',
  body_state TEXT NOT NULL CHECK (body_state IN ('ok', 'empty', 'missing')),
  fetch_error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE page_orgs (
  page_id INTEGER NOT NULL,
  slug TEXT NOT NULL,
  PRIMARY KEY (page_id, slug)
) WITHOUT ROWID;
CREATE INDEX page_orgs_slug ON page_orgs(slug);
CREATE TABLE stems (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL UNIQUE
);
CREATE TABLE uni (
  stem_id INTEGER NOT NULL,
  page_id INTEGER NOT NULL,
  PRIMARY KEY (stem_id, page_id)
) WITHOUT ROWID;
CREATE TABLE bi (
  a INTEGER NOT NULL,
  b INTEGER NOT NULL,
  page_id INTEGER NOT NULL,
  PRIMARY KEY (a, b, page_id)
) WITHOUT ROWID;
"""


def _sidecar(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def _unlink_sidecars(path: Path) -> None:
    """Drop WAL/SHM/journal leftovers. Replacing the db file does not remove them."""
    for suffix in ("-wal", "-shm", "-journal"):
        _sidecar(path, suffix).unlink(missing_ok=True)


def _connect(path: Path) -> sqlite3.Connection:
    # DELETE, not WAL: Docker Desktop bind mounts (virtiofs/osxfs) do not
    # support the shared-memory locking WAL needs. Stem indexes are write-once
    # then read-only, so DELETE is enough.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA cache_size={_SQLITE_CACHE_KIB}")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _read_meta(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        return {str(k): str(v) for k, v in conn.execute("SELECT key, value FROM meta")}
    except sqlite3.Error:
        return {}


class StemIndex:
    """Disk-backed inverted Porter-stem index + page catalog (SQLite).

    Postings stay on disk. ``match()`` reads only the lexicon's posting lists.
    """

    def __init__(self, path: Path, corpus_sha256: str, conn: sqlite3.Connection) -> None:
        self.path = path
        self.corpus_sha256 = corpus_sha256
        self._conn = conn
        self._url_ids: dict[str, int] | None = None

    def close(self) -> None:
        self._conn.close()

    def __len__(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()
        return int(row[0]) if row else 0

    def url_ids(self) -> dict[str, int]:
        if self._url_ids is None:
            self._url_ids = {
                str(url): int(pid)
                for url, pid in self._conn.execute("SELECT url, id FROM pages")
            }
        return self._url_ids

    def all_page_ids(self) -> list[int]:
        return [int(r[0]) for r in self._conn.execute("SELECT id FROM pages ORDER BY id")]

    def distinct_organisations(self) -> list[str]:
        return [
            str(r[0])
            for r in self._conn.execute(
                "SELECT DISTINCT slug FROM page_orgs ORDER BY slug COLLATE NOCASE"
            )
        ]

    def distinct_document_types(self) -> list[str]:
        return [
            str(r[0])
            for r in self._conn.execute(
                "SELECT DISTINCT document_type FROM pages "
                "WHERE document_type != '' ORDER BY document_type COLLATE NOCASE"
            )
        ]

    def has_organisation(self, slug: str) -> bool:
        key = norm_slug(slug)
        if not key:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM page_orgs WHERE slug = ? LIMIT 1", (key,),
        ).fetchone()
        return row is not None

    def has_document_type(self, slug: str) -> bool:
        key = norm_slug(slug)
        if not key:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM pages WHERE document_type = ? LIMIT 1", (key,),
        ).fetchone()
        return row is not None

    def matching_organisation_ids(self, slugs: Sequence[str]) -> set[int]:
        wanted = [norm_slug(s) for s in slugs if norm_slug(s)]
        if not wanted:
            return set(self.all_page_ids())
        q = (
            "SELECT DISTINCT page_id FROM page_orgs WHERE slug IN ("
            + ",".join("?" * len(wanted))
            + ")"
        )
        return {int(r[0]) for r in self._conn.execute(q, wanted)}

    def matching_document_type_ids(self, slugs: Sequence[str]) -> set[int]:
        wanted = [norm_slug(s) for s in slugs if norm_slug(s)]
        if not wanted:
            return set(self.all_page_ids())
        q = (
            "SELECT id FROM pages WHERE document_type IN ("
            + ",".join("?" * len(wanted))
            + ")"
        )
        return {int(r[0]) for r in self._conn.execute(q, wanted)}

    def ids_by_body_state(self, page_ids: Sequence[int]) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {"ok": [], "empty": [], "missing": []}
        if not page_ids:
            return out
        self._load_idset(page_ids)
        for state, pid in self._conn.execute(
            "SELECT pages.body_state, pages.id FROM pages "
            "JOIN _idset ON pages.id = _idset.id ORDER BY pages.id"
        ):
            out.setdefault(str(state), []).append(int(pid))
        return out

    def sample_pages(self, page_ids: Sequence[int], n: int = 100) -> dict:
        """First ``n`` ``{url, title}`` rows in ``page_ids`` order."""
        total = len(page_ids)
        head = list(page_ids[:n])
        if not head:
            return {"n": 0, "urls": [], "truncated": False}
        self._load_idset(head)
        by_id = {
            int(pid): {"url": str(url), "title": str(title or "")}
            for pid, url, title in self._conn.execute(
                "SELECT id, url, title FROM pages WHERE id IN (SELECT id FROM _idset)"
            )
        }
        urls = [by_id[i] for i in head if i in by_id]
        return {"n": total, "urls": urls, "truncated": total > n}

    def catalog_items(self, page_ids: Sequence[int] | None = None) -> list[dict]:
        """Lightweight page dicts (no bodies). ``ok`` pages omit ``body_text``."""
        if page_ids is not None and not page_ids:
            return []
        if page_ids is not None:
            self._load_idset(page_ids)
            where = " WHERE id IN (SELECT id FROM _idset)"
            org_where = " WHERE page_id IN (SELECT id FROM _idset)"
        else:
            where = ""
            org_where = ""
        orgs_by_id: dict[int, list[str]] = {}
        for pid, slug in self._conn.execute(
            f"SELECT page_id, slug FROM page_orgs{org_where} ORDER BY page_id, slug"
        ):
            orgs_by_id.setdefault(int(pid), []).append(str(slug))
        items: list[dict] = []
        sql = (
            "SELECT id, url, content_id, title, document_type, "
            f"primary_organisation, body_state, fetch_error FROM pages{where} ORDER BY id"
        )
        for row in self._conn.execute(sql):
            pid = int(row[0])
            body_state = str(row[6])
            meta: dict = {
                "title": row[3] or "",
                "document_type": row[4] or "",
                "organisations": orgs_by_id.get(pid, []),
            }
            if row[5]:
                meta["primary_publishing_organisation"] = row[5]
            if row[7]:
                meta["fetch_error"] = row[7]
            if body_state == "missing":
                meta["body_text"] = None
            elif body_state == "empty":
                meta["body_text"] = ""
            item: dict = {"url": row[1], "meta_data": meta}
            if row[2]:
                item["content_id"] = row[2]
            items.append(item)
        return items

    def items_for_urls(self, urls: Sequence[str]) -> list[dict]:
        """Catalog items for ``urls`` in that order; unknown URLs are dropped."""
        id_by_url = self.url_ids()
        ids = [id_by_url[u] for u in urls if u in id_by_url]
        by_url = {it["url"]: it for it in self.catalog_items(ids)}
        return [by_url[u] for u in urls if u in by_url]

    def match(
        self,
        compiled: CompiledLexicon,
        *,
        page_ids: set[int] | None = None,
    ) -> dict[int, dict]:
        """Inverted lexicon match. Returns page_id → selection_meta for hits only."""
        if page_ids is not None and not page_ids:
            return {}
        restrict = page_ids is not None
        if restrict:
            assert page_ids is not None
            self._load_idset(page_ids)
        hits: dict[int, dict[str, list[str]]] = {}
        for cat, terms in compiled:
            cat_name = cat["name"]
            for term, stemmed in terms:
                if isinstance(stemmed, str):
                    pids = self._uni_pages(stemmed, restrict)
                elif isinstance(stemmed, tuple) and len(stemmed) == 2:
                    pids = self._bi_pages(str(stemmed[0]), str(stemmed[1]), restrict)
                else:
                    continue
                for pid in pids:
                    bucket = hits.setdefault(pid, {})
                    seen = bucket.setdefault(cat_name, [])
                    if term not in seen:
                        seen.append(term)
        return {
            pid: {"strategy": "wordsearch_binary", "hits_per_cat": cats}
            for pid, cats in hits.items()
        }

    def _stem_db_id(self, text: str) -> int | None:
        row = self._conn.execute(
            "SELECT id FROM stems WHERE text = ?", (text,),
        ).fetchone()
        return int(row[0]) if row else None

    def _uni_pages(self, stem: str, restrict: bool) -> list[int]:
        sid = self._stem_db_id(stem)
        if sid is None:
            return []
        if restrict:
            sql = (
                "SELECT uni.page_id FROM uni JOIN _idset ON uni.page_id = _idset.id "
                "WHERE uni.stem_id = ?"
            )
        else:
            sql = "SELECT page_id FROM uni WHERE stem_id = ?"
        return [int(r[0]) for r in self._conn.execute(sql, (sid,))]

    def _bi_pages(self, a: str, b: str, restrict: bool) -> list[int]:
        aid, bid = self._stem_db_id(a), self._stem_db_id(b)
        if aid is None or bid is None:
            return []
        if restrict:
            sql = (
                "SELECT bi.page_id FROM bi JOIN _idset ON bi.page_id = _idset.id "
                "WHERE bi.a = ? AND bi.b = ?"
            )
        else:
            sql = "SELECT page_id FROM bi WHERE a = ? AND b = ?"
        return [int(r[0]) for r in self._conn.execute(sql, (aid, bid))]

    def _load_idset(self, page_ids: Sequence[int]) -> None:
        self._conn.execute("DROP TABLE IF EXISTS _idset")
        self._conn.execute("CREATE TEMP TABLE _idset (id INTEGER PRIMARY KEY)")
        self._conn.executemany(
            "INSERT INTO _idset(id) VALUES (?)", ((int(i),) for i in page_ids),
        )

    @classmethod
    def open(cls, path: Path, expected_sha: str | None = None) -> StemIndex | None:
        if not path.is_file():
            return None
        _unlink_sidecars(path)
        try:
            conn = _connect(path)
            meta = _read_meta(conn)
        except sqlite3.Error:
            return None
        if meta.get("version") != str(STEM_INDEX_VERSION):
            conn.close()
            return None
        sha = meta.get("corpus_sha256") or ""
        if expected_sha is not None and sha != expected_sha:
            conn.close()
            return None
        if not sha:
            conn.close()
            return None
        return cls(path, sha, conn)

    @classmethod
    def build(
        cls,
        json_path: Path,
        corpus_sha256: str,
        path: Path,
        *,
        on_progress: Callable[[str, int, int], None] | None = None,
        n_pages: int | None = None,
    ) -> StemIndex:
        """Stream ``json_path``, Porter-stem, write ``path`` atomically."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".building")
        if tmp.exists():
            tmp.unlink()
        _unlink_sidecars(tmp)
        conn = sqlite3.connect(str(tmp))
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.executescript(_SCHEMA)
        total = n_pages or 0
        if on_progress is not None:
            on_progress("stem", 0, total)
        intern: dict[str, int] = {}
        pending_stems: list[tuple[int, str]] = []
        pending_uni: list[tuple[int, int]] = []
        pending_bi: list[tuple[int, int, int]] = []
        pending_pages: list[tuple] = []
        pending_orgs: list[tuple[int, str]] = []

        def intern_stem(text: str) -> int:
            sid = intern.get(text)
            if sid is None:
                sid = len(intern) + 1
                intern[text] = sid
                pending_stems.append((sid, text))
            return sid

        def flush() -> None:
            if pending_stems:
                conn.executemany(
                    "INSERT INTO stems(id, text) VALUES (?, ?)", pending_stems,
                )
                pending_stems.clear()
            if pending_pages:
                conn.executemany(
                    "INSERT INTO pages(id, url, content_id, title, document_type, "
                    "primary_organisation, body_state, fetch_error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    pending_pages,
                )
                pending_pages.clear()
            if pending_orgs:
                conn.executemany(
                    "INSERT OR IGNORE INTO page_orgs(page_id, slug) VALUES (?, ?)",
                    pending_orgs,
                )
                pending_orgs.clear()
            if pending_uni:
                conn.executemany(
                    "INSERT OR IGNORE INTO uni(stem_id, page_id) VALUES (?, ?)",
                    pending_uni,
                )
                pending_uni.clear()
            if pending_bi:
                conn.executemany(
                    "INSERT OR IGNORE INTO bi(a, b, page_id) VALUES (?, ?, ?)",
                    pending_bi,
                )
                pending_bi.clear()

        n = 0
        try:
            for n, item in enumerate(iter_json_items(json_path), start=1):
                meta = item.get("meta_data") or {}
                if not isinstance(meta, dict):
                    meta = {}
                url = str(item.get("url") or "") or f"__page_{n - 1}__"
                title = str(meta.get("title") or "").strip()
                doc_type = norm_slug(str(meta.get("document_type") or ""))
                primary = norm_slug(str(meta.get("primary_publishing_organisation") or ""))
                fetch_error = str(meta.get("fetch_error") or "")
                raw_body = meta.get("body_text")
                if raw_body is None:
                    body_state = "missing"
                elif not str(raw_body).strip():
                    body_state = "empty"
                else:
                    body_state = "ok"
                    unigrams, bigrams = stem_sets(
                        searchable_text(title, str(raw_body)),
                    )
                    for stem in unigrams:
                        pending_uni.append((intern_stem(stem), n - 1))
                    for a, b in bigrams:
                        pending_bi.append((intern_stem(a), intern_stem(b), n - 1))
                pending_pages.append((
                    n - 1,
                    url,
                    str(item.get("content_id") or ""),
                    title,
                    doc_type,
                    primary,
                    body_state,
                    fetch_error,
                ))
                if primary:
                    pending_orgs.append((n - 1, primary))
                for raw in meta.get("organisations") or []:
                    slug = norm_slug(str(raw))
                    if slug:
                        pending_orgs.append((n - 1, slug))
                if n % _BUILD_FLUSH == 0:
                    flush()
                if on_progress is not None and (n == 1 or n % 100 == 0):
                    on_progress("stem", n, total or n)
            flush()
            conn.execute("DELETE FROM meta")
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                [
                    ("version", str(STEM_INDEX_VERSION)),
                    ("corpus_sha256", corpus_sha256),
                    ("n_pages", str(n)),
                ],
            )
            conn.commit()
        except Exception:
            conn.close()
            tmp.unlink(missing_ok=True)
            _unlink_sidecars(tmp)
            raise
        conn.close()
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
        _unlink_sidecars(tmp)
        _unlink_sidecars(path)
        tmp.replace(path)
        if on_progress is not None:
            on_progress("stem", n, n)
        try:
            conn = _connect(path)
            meta = _read_meta(conn)
        except sqlite3.Error as e:
            raise RuntimeError(
                f"built stem index but failed to reopen {path}: {e}"
            ) from e
        if meta.get("version") != str(STEM_INDEX_VERSION):
            conn.close()
            raise RuntimeError(
                f"built stem index but meta version={meta.get('version')!r} "
                f"!= {STEM_INDEX_VERSION} ({path})"
            )
        sha = meta.get("corpus_sha256") or ""
        if sha != corpus_sha256:
            conn.close()
            raise RuntimeError(
                f"built stem index but corpus_sha256 mismatch ({path})"
            )
        return cls(path, sha, conn)


def load_or_build_stem_index(
    json_path: Path,
    *,
    corpus_sha256: str,
    path: Path,
    on_progress: Callable[[str, int, int], None] | None = None,
    log: Callable[[str], None] | None = None,
    n_pages: int | None = None,
) -> StemIndex:
    """Open ``path`` if it matches ``corpus_sha256``, otherwise stream-build it."""
    cached = StemIndex.open(path, corpus_sha256)
    if cached is not None:
        if log is not None:
            log(f"Stem index cache hit ({len(cached)} pages): {path}")
        return cached
    if log is not None:
        log(f"Building stem index (once per corpus sha) → {path}")

    def _progress(phase: str, done: int, total: int) -> None:
        if log is not None and (done % 500 == 0 or done == total):
            log(f"  stem {done}/{total or '?'}…")
        if on_progress is not None:
            on_progress(phase, done, total)

    index = StemIndex.build(
        json_path, corpus_sha256, path, on_progress=_progress, n_pages=n_pages,
    )
    if log is not None:
        log(f"Wrote stem index ({len(index)} pages): {path}")
    return index


def query_text(category: dict) -> str:
    """Text encoded as the cosine search query for a category."""
    return (category.get("embedding_query") or category.get("description") or "").strip()


class EmbedCache:
    """URL → page embedding, keyed on disk by corpus sha + embed model + prompt."""

    def __init__(
        self,
        corpus_sha256: str,
        embed_model: str,
        pages: dict[str, array.array] | None = None,
    ) -> None:
        self.corpus_sha256 = corpus_sha256
        self.embed_model = embed_model
        self._pages: dict[str, array.array] = pages or {}

    def __len__(self) -> int:
        return len(self._pages)

    def get(self, url: str) -> list[float] | None:
        packed = self._pages.get(url)
        if packed is None:
            return None
        return packed.tolist()

    def put(self, url: str, vector: list[float]) -> None:
        self._pages[url] = array.array("f", vector)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": EMBED_CACHE_VERSION,
            "corpus_sha256": self.corpus_sha256,
            "embed_model": self.embed_model,
            "document_prompt": DOCUMENT_PROMPT,
            "pages": self._pages,
        }
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)

    @classmethod
    def try_load(
        cls, path: Path, expected_sha: str, embed_model: str,
    ) -> EmbedCache | None:
        if not path.is_file():
            return None
        try:
            with path.open("rb") as fh:
                payload = pickle.load(fh)
        except (OSError, pickle.UnpicklingError, EOFError, AttributeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("version") != EMBED_CACHE_VERSION:
            return None
        if payload.get("corpus_sha256") != expected_sha:
            return None
        if payload.get("embed_model") != embed_model:
            return None
        if payload.get("document_prompt") != DOCUMENT_PROMPT:
            return None
        raw_pages = payload.get("pages")
        if not isinstance(raw_pages, dict):
            return None
        pages: dict[str, array.array] = {}
        dim: int | None = None
        for url, raw in raw_pages.items():
            try:
                packed = raw if isinstance(raw, array.array) else array.array("f", raw)
            except (TypeError, ValueError):
                return None
            if dim is None:
                dim = len(packed)
            elif len(packed) != dim:
                return None
            pages[str(url)] = packed
        return cls(expected_sha, embed_model, pages)

    @classmethod
    def build(
        cls,
        items: list[dict],
        corpus_sha256: str,
        *,
        embed_model: str,
        device: str | None = None,
        log: Callable[[str], None] | None = None,
    ) -> EmbedCache:
        """Embed every page that has a body. Missing/empty bodies are omitted."""
        urls: list[str] = []
        bodies: list[str] = []
        for item in items:
            meta = item.get("meta_data") or {}
            raw_body = meta.get("body_text")
            if raw_body is None or not str(raw_body).strip():
                continue
            title = (meta.get("title") or "").strip()
            urls.append(item["url"])
            bodies.append(searchable_text(title, str(raw_body)))
        vectors = _encode_documents(
            bodies, model=embed_model, device=device, log=log,
        )
        pages = {
            url: array.array("f", vec) for url, vec in zip(urls, vectors, strict=True)
        }
        return cls(corpus_sha256, embed_model, pages)


def load_or_build_embed_cache(
    items: list[dict],
    *,
    corpus_sha256: str,
    embed_model: str,
    path: Path,
    device: str | None = None,
    log: Callable[[str], None] | None = None,
) -> EmbedCache:
    """Load ``path`` if it matches sha + model + prompt, otherwise embed and write it."""
    cached = EmbedCache.try_load(path, corpus_sha256, embed_model)
    if cached is not None:
        if log is not None:
            log(f"Embed index cache hit ({len(cached)} pages): {path}")
        return cached
    if log is not None:
        log(f"Building embed index (once per corpus sha + model) → {path}")
    cache = EmbedCache.build(
        items, corpus_sha256, embed_model=embed_model, device=device, log=log,
    )
    cache.save(path)
    if log is not None:
        log(f"Wrote embed index ({len(cache)} pages): {path}")
    return cache


def _sentence_transformer(model: str, device: str | None):
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError as e:
        raise CosineRouterUnavailable(
            "cosine routing requires the cosine extra. Run: uv sync --extra cosine"
        ) from e
    return SentenceTransformer(model, device=device, trust_remote_code=True)


def _encode_documents(
    bodies: list[str],
    *,
    model: str,
    device: str | None = None,
    log: Callable[[str], None] | None = None,
) -> list[list[float]]:
    """Encode page title+body with the document prompt. Batched for memory."""
    if not bodies:
        return []
    st = _sentence_transformer(model, device)
    out: list[list[float]] = []
    n = len(bodies)
    for i in range(0, n, _EMBED_BATCH):
        chunk = bodies[i : i + _EMBED_BATCH]
        raw = st.encode(chunk, prompt=DOCUMENT_PROMPT, convert_to_numpy=True)
        out.extend([float(x) for x in row] for row in raw)
        done = min(i + _EMBED_BATCH, n)
        if log is not None and (done % 512 == 0 or done == n):
            log(f"  embed {done}/{n}…")
    return out


def _score_page_embeddings(
    page_embeddings: list[list[float]],
    queries: list[str],
    *,
    model: str,
    device: str | None,
) -> list[list[float]]:
    """Encode queries only; cosine against already-cached page vectors."""
    try:
        import torch
        from sentence_transformers import util  # type: ignore[import-not-found]
    except ImportError as e:
        raise CosineRouterUnavailable(
            "cosine routing requires the cosine extra. Run: uv sync --extra cosine"
        ) from e

    st = _sentence_transformer(model, device)
    cat_embeddings = st.encode(
        queries, prompt=QUERY_PROMPT, convert_to_tensor=True,
    )
    page_tensor = torch.tensor(page_embeddings, dtype=cat_embeddings.dtype)
    scores = util.cos_sim(page_tensor, cat_embeddings)
    n_q = len(queries)
    return [
        [round(float(scores[i][j]), 4) for j in range(n_q)]
        for i in range(len(page_embeddings))
    ]


def _embed_cosine(
    bodies: list[str],
    queries: list[str],
    *,
    model: str,
    device: str | None,
) -> list[list[float]]:
    """Encode bodies vs queries; return an (N, C) cosine matrix as nested lists."""
    try:
        from sentence_transformers import util  # type: ignore[import-not-found]
    except ImportError as e:
        raise CosineRouterUnavailable(
            "cosine routing requires the cosine extra. Run: uv sync --extra cosine"
        ) from e

    st = _sentence_transformer(model, device)
    cat_embeddings = st.encode(
        queries, prompt=QUERY_PROMPT, convert_to_tensor=True,
    )
    page_embeddings = st.encode(
        bodies, prompt=DOCUMENT_PROMPT, convert_to_tensor=True,
    )
    scores = util.cos_sim(page_embeddings, cat_embeddings)
    return [
        [round(float(scores[i][j]), 4) for j in range(len(queries))]
        for i in range(len(bodies))
    ]


def select_by_cosine(
    bodies: list[str],
    categories: list[dict],
    *,
    model: str = DEFAULT_EMBED_MODEL,
    threshold: float = DEFAULT_COSINE_THRESHOLD,
    device: str | None = None,
    page_embeddings: list[list[float]] | None = None,
) -> list[tuple[list[dict], dict]]:
    """Batch-encode bodies against category query text. One result per body.

    A category is selected iff its cosine score is ≥ ``threshold``. Each
    ``selection_meta`` carries the per-category scores so a miss can be
    explained (and a threshold histogram built) without a second encode.
    ``page_embeddings`` skips the document encode (cache hit); queries still
    go through the model.
    """
    if not bodies:
        return []
    if page_embeddings is not None and len(page_embeddings) != len(bodies):
        raise ValueError(
            f"page_embeddings length {len(page_embeddings)} != bodies {len(bodies)}"
        )
    names = [c["name"] for c in categories]
    queries = [query_text(c) for c in categories]
    base_meta = {
        "strategy": "cosine_body",
        "threshold": threshold,
        "embed_model": model,
    }
    if not categories:
        return [([], {**base_meta, "scores": {}}) for _ in bodies]

    if page_embeddings is not None:
        matrix = _score_page_embeddings(
            page_embeddings, queries, model=model, device=device,
        )
    else:
        matrix = _embed_cosine(bodies, queries, model=model, device=device)
    out: list[tuple[list[dict], dict]] = []
    for row in matrix:
        scores = {names[j]: row[j] for j in range(len(names))}
        selected = [c for j, c in enumerate(categories) if row[j] >= threshold]
        out.append((selected, {**base_meta, "scores": scores}))
    return out
