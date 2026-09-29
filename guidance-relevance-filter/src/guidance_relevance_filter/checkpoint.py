"""On-disk run checkpoint so a killed process can reattach.

Written to ``<output_dir>/checkpoint.json`` the moment we know anything durable
(fingerprint, routed URL order, batch id / per-reply texts). Deleted when the
run writes its final outputs. Re-invoking ``run`` against the same output dir
with a live checkpoint reattaches; it never silently resubmits the same pages.

custom_id is the index into the routed/positive URL list, so a resume that
would pair the wrong pages with the wrong replies is refused. Batch resume is
an Anthropic batch id; sync resume is the accumulated ``replies`` map.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

CHECKPOINT_VERSION = 1
CHECKPOINT_NAME = "checkpoint.json"


class ResumeIncompatible(RuntimeError):
    """This invocation does not match the checkpoint; attaching would mis-label pages."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def sha256_json(obj: object) -> str:
    return _sha256_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode())


def fingerprint_for(
    *,
    input_path: Path,
    n_pages: int,
    category: str,
    model: str,
    adjudicator_model: str,
    max_words: int,
    shard_name: str | None,
    categories: list[dict],
    lexicons: dict[str, list[str]],
    router: str = "wordsearch",
    cosine_threshold: float = 0.2,
    embed_model: str = "nomic-ai/nomic-embed-text-v1.5",
    llm_mode: str = "batch",
) -> dict:
    """Identity of a run. Resume is only safe when this matches the checkpoint."""
    return {
        "input_sha256": sha256_file(input_path),
        "n_pages": n_pages,
        "category": category,
        "model": model,
        "adjudicator_model": adjudicator_model,
        "max_words": max_words,
        "shard_name": shard_name,
        "categories_sha256": sha256_json(categories),
        "lexicon_sha256": sha256_json(lexicons),
        "router": router,
        "cosine_threshold": cosine_threshold,
        "embed_model": embed_model,
        "llm_mode": llm_mode,
    }


def _normalise_fingerprint(fp: dict) -> dict:
    """Old checkpoints predate ``llm_mode``; treat a missing value as batch."""
    out = dict(fp)
    out.setdefault("llm_mode", "batch")
    return out


def _empty_passes() -> dict:
    return {
        "pass1": {
            "batch_id": None, "routed_urls": None, "submitted": None, "replies": {},
        },
        "pass2": {
            "batch_id": None, "positive_urls": None, "submitted": None, "replies": {},
        },
    }


class Checkpoint:
    """File-backed pass-1/pass-2 identity. ``save`` is atomic (tmp + replace)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict = json.loads(path.read_text()) if path.exists() else {}
        self._lock = threading.Lock()

    @property
    def exists(self) -> bool:
        return bool(self.data)

    @property
    def started_at(self) -> str:
        return self.data["started_at"]

    @property
    def pass1_batch_id(self) -> str | None:
        return (self.data.get("pass1") or {}).get("batch_id")

    @property
    def pass2_batch_id(self) -> str | None:
        return (self.data.get("pass2") or {}).get("batch_id")

    @property
    def pass1_replies(self) -> dict:
        return dict((self.data.get("pass1") or {}).get("replies") or {})

    @property
    def pass2_replies(self) -> dict:
        return dict((self.data.get("pass2") or {}).get("replies") or {})

    @property
    def pass1_routed_urls(self) -> list[str] | None:
        return (self.data.get("pass1") or {}).get("routed_urls")

    @property
    def pass2_positive_urls(self) -> list[str] | None:
        return (self.data.get("pass2") or {}).get("positive_urls")

    def init(self, fingerprint: dict, started_at: str) -> None:
        self.data = {
            "version": CHECKPOINT_VERSION,
            "started_at": started_at,
            "fingerprint": fingerprint,
            **_empty_passes(),
        }
        self._save()

    def assert_fingerprint(self, fingerprint: dict) -> None:
        old = _normalise_fingerprint(self.data.get("fingerprint") or {})
        new = _normalise_fingerprint(fingerprint)
        if old == new:
            return
        diffs = [
            f"  {k}: checkpoint={old.get(k)!r} now={new.get(k)!r}"
            for k in sorted(set(old) | set(new))
            if old.get(k) != new.get(k)
        ]
        raise ResumeIncompatible(
            f"checkpoint {self.path} does not match this invocation:\n"
            + "\n".join(diffs)
            + "\nRe-run with --fresh to abandon the old batch "
            "(it is NOT cancelled on Anthropic), or use a new output dir."
        )

    def record_pass1_routing(self, urls: list[str]) -> None:
        self._record_urls("pass1", "routed_urls", urls)

    def record_pass1_batch(self, batch_id: str) -> None:
        self.data["pass1"]["batch_id"] = batch_id
        self._save()

    def record_pass2_positives(self, urls: list[str]) -> None:
        self._record_urls("pass2", "positive_urls", urls)

    def record_pass2_batch(self, batch_id: str) -> None:
        self.data["pass2"]["batch_id"] = batch_id
        self._save()

    def record_pass1_reply(self, custom_id: str, text: str, usage: dict) -> None:
        self._record_reply("pass1", custom_id, text, usage)

    def record_pass2_reply(self, custom_id: str, text: str, usage: dict) -> None:
        self._record_reply("pass2", custom_id, text, usage)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self.data = {}

    def _record_urls(self, pass_key: str, url_key: str, urls: list[str]) -> None:
        existing = self.data[pass_key].get(url_key)
        if existing is not None and existing != urls:
            raise ResumeIncompatible(
                f"{pass_key} {url_key} changed ({len(existing)} stored vs {len(urls)} now). "
                "Refusing to attach custom_ids to the wrong pages. Use --fresh."
            )
        self.data[pass_key][url_key] = urls
        self.data[pass_key]["submitted"] = len(urls)
        self._save()

    def _record_reply(self, pass_key: str, custom_id: str, text: str, usage: dict) -> None:
        with self._lock:
            replies = self.data[pass_key].setdefault("replies", {})
            replies[custom_id] = {
                "text": text,
                "input": int(usage.get("input") or 0),
                "output": int(usage.get("output") or 0),
            }
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2) + "\n")
        tmp.replace(self.path)
