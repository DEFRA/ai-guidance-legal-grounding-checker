"""In-memory Completions double for offline classify/adjudicate tests."""
from __future__ import annotations

from collections.abc import Callable

from guidance_relevance_filter.completions import CompletionRequest


class FakeCompletions:
    """Maps ``custom_id → text``. Missing ids look like a dropped bulk reply."""

    def __init__(
        self,
        replies: dict[str, str] | None = None,
        *,
        rescue: Callable | None = None,
        on_create: Callable | None = None,
        meta_id: str = "batch-test",
    ) -> None:
        self.replies = dict(replies or {})
        self.rescue = rescue
        self.on_create = on_create
        self.meta_id = meta_id

    def complete_many(
        self,
        requests: list[CompletionRequest],
        *,
        label: str,
        resume_id: str | None = None,
        already: dict[str, dict] | None = None,
        on_submitted=None,
        on_result=None,
    ):
        del label
        if resume_id:
            if on_submitted is not None:
                on_submitted(resume_id)
        else:
            if self.on_create is not None:
                self.on_create(requests)
            if on_submitted is not None:
                on_submitted(self.meta_id)
        raw: dict[str, str] = {}
        usage = {"input": 0, "output": 0}
        for cid, rec in (already or {}).items():
            raw[cid] = rec["text"]
            usage["input"] += int(rec.get("input") or 0)
            usage["output"] += int(rec.get("output") or 0)
        for req in requests:
            if req.custom_id in raw:
                continue
            text = self.replies.get(req.custom_id)
            if text is None:
                continue
            raw[req.custom_id] = text
            u = {"input": 10, "output": 5}
            usage["input"] += u["input"]
            usage["output"] += u["output"]
            if on_result is not None:
                on_result(req.custom_id, text, u)
        meta = {
            "id": resume_id or self.meta_id,
            "submitted": len(requests),
            "collected": len(raw),
            "elapsed_seconds": 0,
            "request_counts": {
                "succeeded": len(raw),
                "processing": 0,
                "errored": 0,
                "canceled": 0,
                "expired": 0,
            },
            "resumed": bool(resume_id or already),
            "mode": "batch",
        }
        return raw, usage, meta

    def complete_one(self, request: CompletionRequest):
        if self.rescue is None:
            raise AssertionError("the rescue (Messages API) call was not expected")
        result = self.rescue(request) if _wants_request(self.rescue) else self.rescue()
        if result is None:
            return None
        if isinstance(result, tuple):
            return result
        return result, {"input": 10, "output": 5}


def llm(*texts: str, **kwargs) -> FakeCompletions:
    """``llm(text0, text1)`` → custom_ids ``\"0\"``, ``\"1\"``."""
    return FakeCompletions({str(i): t for i, t in enumerate(texts)}, **kwargs)


def _wants_request(fn: Callable) -> bool:
    try:
        return fn.__code__.co_argcount >= 1 and fn.__code__.co_varnames[0] != "self"
    except AttributeError:
        return False
