"""Frozen Guidance Discovery corpus (with_body.json + MANIFEST.json)."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from guidance_relevance_filter.narrowing import (
    StemIndex,
    load_or_build_stem_index,
    sha256_file,
)

from .category import scope_options


class CorpusError(RuntimeError):
    """Corpus directory is missing, stale, or malformed."""


class UnknownCorpus(CorpusError):
    """Requested snapshot sha is not in the library."""


def _optional_slug_list(raw: dict[str, Any], key: str) -> list[str] | None:
    if key not in raw:
        return None
    value = raw[key]
    if not isinstance(value, list):
        return None
    return [str(item).strip() for item in value if str(item).strip()]


@dataclass(frozen=True)
class Manifest:
    built_on: str
    n_pages: int
    with_body_sha256: str
    discovery_git_sha: str | None = None
    organisations: list[str] | None = None
    document_types: list[str] | None = None


def format_built_on(built_on: str) -> str:
    raw = (built_on or "").strip() or "unknown"
    try:
        dt = datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError:
        return raw
    return f"{dt.day} {dt.strftime('%B %Y')}"


def snapshot_label(built_on: str, n_pages: int) -> str:
    pages = f"{n_pages:,}" if n_pages >= 0 else "?"
    return f"{format_built_on(built_on)} · {pages} pages"


@dataclass(frozen=True)
class Snapshot:
    id: str
    built_on: str
    n_pages: int
    root: Path
    organisations: list[str] | None = None
    document_types: list[str] | None = None

    @property
    def label(self) -> str:
        return snapshot_label(self.built_on, self.n_pages)

    @property
    def sha8(self) -> str:
        return self.id[:8]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "built_on": self.built_on,
            "n_pages": self.n_pages,
            "label": self.label,
            "sha8": self.sha8,
            "organisations": self.organisations,
            "document_types": self.document_types,
        }


def _snapshot(root: Path, manifest: Manifest) -> Snapshot:
    return Snapshot(
        id=manifest.with_body_sha256,
        built_on=manifest.built_on,
        n_pages=manifest.n_pages,
        root=root,
        organisations=manifest.organisations,
        document_types=manifest.document_types,
    )


def _manifest_from_raw(raw: dict[str, Any], digest: str) -> Manifest:
    n_pages = int(raw["n_pages"]) if "n_pages" in raw else -1
    return Manifest(
        built_on=str(raw.get("built_on") or "unknown"),
        n_pages=n_pages,
        with_body_sha256=digest,
        discovery_git_sha=raw.get("discovery_git_sha") or None,
        organisations=_optional_slug_list(raw, "organisations"),
        document_types=_optional_slug_list(raw, "document_types"),
    )


class Corpus:
    """Load ``with_body.json`` once per process after checking MANIFEST.json."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self._stem_lock = threading.Lock()
        self._stem_index: StemIndex | None = None

    @property
    def pages_path(self) -> Path:
        return self.root / "with_body.json"

    @property
    def manifest_path(self) -> Path:
        return self.root / "MANIFEST.json"

    def require(self) -> Manifest:
        cached = getattr(self, "_manifest", None)
        if cached is not None:
            return cached
        if not self.root.is_dir():
            raise CorpusError(
                f"Corpus directory {self.root} does not exist. "
                "See docs/updating-the-corpus.md."
            )
        if not self.pages_path.is_file():
            raise CorpusError(
                f"{self.pages_path} is missing. Copy Guidance Discovery "
                "output/with_body.json here (docs/updating-the-corpus.md)."
            )
        if not self.manifest_path.is_file():
            raise CorpusError(f"{self.manifest_path} is missing.")
        try:
            raw = json.loads(self.manifest_path.read_text())
        except json.JSONDecodeError as e:
            raise CorpusError(f"{self.manifest_path} is not valid JSON") from e
        digest = sha256_file(self.pages_path)
        expected = str(raw.get("with_body_sha256") or "")
        if expected and expected != digest:
            raise CorpusError(
                f"{self.pages_path.name} sha256 {digest[:12]}… does not match "
                f"MANIFEST.json ({expected[:12]}…). Re-copy the corpus and bump the manifest."
            )
        manifest = _manifest_from_raw(raw, digest)
        self._manifest = manifest
        return manifest

    def stem_index_path(self) -> Path:
        manifest = self.require()
        return self.root / "stem_index" / f"{manifest.with_body_sha256}.sqlite"

    def ensure_stem_index(
        self,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> StemIndex:
        """Open or stream-build the inverted Porter-stem index for this snapshot."""
        with self._stem_lock:
            if self._stem_index is not None:
                return self._stem_index
            manifest = self.require()
            n_pages = manifest.n_pages if manifest.n_pages >= 0 else None
            self._stem_index = load_or_build_stem_index(
                self.pages_path,
                corpus_sha256=manifest.with_body_sha256,
                path=self.stem_index_path(),
                on_progress=on_progress,
                n_pages=n_pages,
            )
            return self._stem_index

    def scope_slugs(self) -> tuple[list[str], list[str]]:
        """Publisher / document-type slugs: MANIFEST lists, else the stem index."""
        cached = getattr(self, "_scope_slugs", None)
        if cached is not None:
            return cached
        manifest = self.require()
        orgs = manifest.organisations
        types = manifest.document_types
        if orgs is None or types is None:
            index = self.ensure_stem_index()
            if orgs is None:
                orgs = index.distinct_organisations()
            if types is None:
                types = index.distinct_document_types()
        self._scope_slugs = (orgs, types)
        return self._scope_slugs


def _peek_manifest(root: Path) -> Manifest | None:
    """Read MANIFEST.json without hashing with_body.json."""
    pages = root / "with_body.json"
    manifest = root / "MANIFEST.json"
    if not pages.is_file() or not manifest.is_file():
        return None
    try:
        raw = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    digest = str(raw.get("with_body_sha256") or "").strip()
    if not digest:
        return None
    return _manifest_from_raw(raw, digest)


class CorpusCatalog:
    """Library of frozen snapshots under ``GRF_CORPUS``.

    Lists the root itself (legacy flat layout) and each immediate child
    directory that has ``with_body.json`` + ``MANIFEST.json``. Skips
    ``stem_index`` and ``embed_index``. Identity is ``with_body_sha256``; a
    child with the same sha wins over the root.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self._lock = threading.Lock()
        self._loaded: dict[str, Corpus] = {}

    def list(self) -> list[Snapshot]:
        found: dict[str, Snapshot] = {}
        root_manifest = _peek_manifest(self.root)
        if root_manifest is not None:
            found[root_manifest.with_body_sha256] = _snapshot(self.root, root_manifest)
        if self.root.is_dir():
            for child in sorted(self.root.iterdir()):
                if not child.is_dir() or child.name in {"stem_index", "embed_index"}:
                    continue
                peeked = _peek_manifest(child)
                if peeked is None:
                    continue
                found[peeked.with_body_sha256] = _snapshot(child, peeked)
        return sorted(
            found.values(),
            key=lambda s: (s.built_on, s.id),
            reverse=True,
        )

    def views(self) -> list[dict[str, Any]]:
        """Snapshot dicts. Org/type checkboxes come from MANIFEST lists only.

        Missing lists → empty pickers. Do not Porter-stem the corpus on GET /.
        """
        out: list[dict[str, Any]] = []
        for snap in self.list():
            orgs = snap.organisations or []
            types = snap.document_types or []
            org_opts, type_opts = scope_options(orgs, types)
            view = snap.as_dict()
            view["organisations"] = orgs
            view["document_types"] = types
            view["organisation_options"] = [
                [slug, label, list(aliases)] for slug, label, aliases in org_opts
            ]
            view["document_type_options"] = [list(item) for item in type_opts]
            out.append(view)
        return out

    def get(self, sha: str | None) -> Corpus:
        snapshots = self.list()
        if not snapshots:
            raise CorpusError(
                f"No snapshots in {self.root}. "
                "See docs/updating-the-corpus.md."
            )
        key = (sha or "").strip() or None
        if key is None:
            chosen = snapshots[0]
        else:
            match = next((s for s in snapshots if s.id == key), None)
            if match is None:
                raise UnknownCorpus(
                    f"Unknown corpus {key[:12]}… — it is not in {self.root}."
                )
            chosen = match
        with self._lock:
            cached = self._loaded.get(chosen.id)
            if cached is not None:
                return cached
            corpus = Corpus(chosen.root)
            self._loaded[chosen.id] = corpus
            return corpus
