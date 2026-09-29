"""Provider-neutral LLM completions for GRF's two passes.

``classify`` / ``adjudicate`` build ``CompletionRequest``s and never import
Anthropic. Two adapters ship the same prompts: Message Batches (default, 0.5×)
or a concurrent ``messages.create`` fan-out (full price, faster). A later
DeepSeek adapter would take the same request shape; it is not this module's job.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Protocol

import anthropic
from anthropic import Anthropic

from ._batch import _fmt_elapsed, _retry, log, submit_and_collect, text_of

LLM_MODE_BATCH = "batch"
LLM_MODE_SYNC = "sync"
LLM_MODES = (LLM_MODE_BATCH, LLM_MODE_SYNC)
DEFAULT_SYNC_CONCURRENCY = 10

OnSubmitted = Callable[[str], None]
OnResult = Callable[[str, str, dict[str, int]], None]


@dataclass(frozen=True)
class CompletionRequest:
    custom_id: str
    model: str
    max_tokens: int
    messages: list[dict]


class Completions(Protocol):
    """Ship a list of prompts; return ``custom_id → text`` plus token usage."""

    def complete_many(
        self,
        requests: list[CompletionRequest],
        *,
        label: str,
        resume_id: str | None = None,
        already: dict[str, dict] | None = None,
        on_submitted: OnSubmitted | None = None,
        on_result: OnResult | None = None,
    ) -> tuple[dict[str, str], dict[str, int], dict]:
        """Run every request. Missing custom_ids are the caller's to rescue.

        ``already`` is the checkpoint's stored replies (sync resume). ``resume_id``
        is an Anthropic batch id (batch resume). ``on_result`` fires per succeeded
        reply so sync can persist as it goes.
        """

    def complete_one(
        self, request: CompletionRequest,
    ) -> tuple[str, dict[str, int]] | None:
        """One Messages-API call (oversized-page rescue).

        ``None`` on a recoverable miss (prompt too long). Auth, billing, and
        other account-level errors propagate so the run does not look like
        30 independent page failures.
        """


def anthropic_completions(
    mode: str = LLM_MODE_BATCH,
    *,
    concurrency: int = DEFAULT_SYNC_CONCURRENCY,
    client: Anthropic | None = None,
) -> Completions:
    """Wire the Anthropic batch or sync adapter. ``client`` is a test seam."""
    if mode not in LLM_MODES:
        raise ValueError(f"llm mode must be one of {LLM_MODES}, not {mode!r}")
    c = client
    if mode == LLM_MODE_SYNC:
        return AnthropicSyncCompletions(c, concurrency=concurrency)
    return AnthropicBatchCompletions(c)


def _to_batch_request(req: CompletionRequest) -> dict:
    return {
        "custom_id": req.custom_id,
        "params": {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "messages": req.messages,
        },
    }


def _create_message(client: Anthropic, request: CompletionRequest):
    return client.messages.create(
        model=request.model,
        max_tokens=request.max_tokens,
        messages=request.messages,
    )


def _is_fatal_api_error(exc: anthropic.APIError) -> bool:
    """Account/config failures that will hit every page the same way.

    Prompt-too-long is the recoverable 400 (oversized-page rescue). Credit
    balance, auth, and unknown model are not.
    """
    if isinstance(exc, (
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        anthropic.NotFoundError,
    )):
        return True
    if isinstance(exc, anthropic.BadRequestError):
        return "too long" not in str(exc).lower()
    return False


def _log_api_error(what: str, exc: anthropic.APIError) -> None:
    log(f"  {what}: {type(exc).__name__}: {exc}")


def _complete_one(client: Anthropic, request: CompletionRequest) -> tuple[str, dict[str, int]] | None:
    try:
        resp = _create_message(client, request)
    except anthropic.APIError as e:
        _log_api_error(f"messages.create {request.custom_id}", e)
        if _is_fatal_api_error(e):
            raise
        return None
    return text_of(resp), {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens}


class AnthropicBatchCompletions:
    """Anthropic Message Batches API (0.5×). Resume is an Anthropic batch id."""

    def __init__(self, client: Anthropic | None = None) -> None:
        self._client = client

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic()
        return self._client

    def complete_one(
        self, request: CompletionRequest,
    ) -> tuple[str, dict[str, int]] | None:
        return _complete_one(self._get_client(), request)

    def complete_many(
        self,
        requests: list[CompletionRequest],
        *,
        label: str,
        resume_id: str | None = None,
        already: dict[str, dict] | None = None,
        on_submitted: OnSubmitted | None = None,
        on_result: OnResult | None = None,
    ) -> tuple[dict[str, str], dict[str, int], dict]:
        del already, on_result  # batch identity is the server-side job, not per-reply
        raw, usage, meta = submit_and_collect(
            self._get_client(),
            [_to_batch_request(r) for r in requests],
            label=label,
            resume_id=resume_id,
            on_submitted=on_submitted,
        )
        return raw, usage, {**meta, "mode": LLM_MODE_BATCH}


class AnthropicSyncCompletions:
    """Concurrent ``messages.create`` (full price). Resume skips stored replies."""

    def __init__(
        self, client: Anthropic | None = None, *, concurrency: int = DEFAULT_SYNC_CONCURRENCY,
    ) -> None:
        if concurrency < 1:
            raise ValueError(f"concurrency must be >= 1, not {concurrency}")
        self._client = client
        self.concurrency = concurrency

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic()
        return self._client

    def complete_one(
        self, request: CompletionRequest,
    ) -> tuple[str, dict[str, int]] | None:
        return _complete_one(self._get_client(), request)

    def complete_many(
        self,
        requests: list[CompletionRequest],
        *,
        label: str,
        resume_id: str | None = None,
        already: dict[str, dict] | None = None,
        on_submitted: OnSubmitted | None = None,
        on_result: OnResult | None = None,
    ) -> tuple[dict[str, str], dict[str, int], dict]:
        del resume_id, on_submitted  # no server-side job to reattach to
        n = len(requests)
        started = time.monotonic()
        raw: dict[str, str] = {}
        usage = {"input": 0, "output": 0}
        for cid, rec in (already or {}).items():
            raw[cid] = rec["text"]
            usage["input"] += int(rec.get("input") or 0)
            usage["output"] += int(rec.get("output") or 0)
        pending = [r for r in requests if r.custom_id not in raw]
        n_done = n - len(pending)
        log(
            f"  {label}: sync Messages API — {len(pending)} to call"
            + (f", {n_done} already checkpointed" if n_done else "")
            + f", concurrency {self.concurrency}"
        )
        client = self._get_client()

        def _one(req: CompletionRequest) -> tuple[str, tuple[str, dict[str, int]] | None]:
            def op():
                return _create_message(client, req)

            try:
                resp = _retry(op, what=f"{label} {req.custom_id}")
            except anthropic.APIError as e:
                _log_api_error(f"{label} {req.custom_id}", e)
                if _is_fatal_api_error(e):
                    raise
                return req.custom_id, None
            u = {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens}
            return req.custom_id, (text_of(resp), u)

        workers = min(self.concurrency, len(pending)) or 1
        if pending:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_one, req) for req in pending]
                for i, fut in enumerate(as_completed(futures), start=1):
                    cid, got = fut.result()
                    if got is not None:
                        text, u = got
                        raw[cid] = text
                        usage["input"] += u["input"]
                        usage["output"] += u["output"]
                        if on_result is not None:
                            on_result(cid, text, u)
                    if i == 1 or i % 25 == 0 or i == len(pending):
                        log(
                            f"  {label}: {n_done + i}/{n} done "
                            f"({len(raw)} ok, sync)  "
                            f"elapsed {_fmt_elapsed(time.monotonic() - started)}"
                        )

        errored = n - len(raw)
        meta = {
            "id": None,
            "submitted": n,
            "collected": len(raw),
            "elapsed_seconds": int(time.monotonic() - started),
            "request_counts": {
                "succeeded": len(raw),
                "processing": 0,
                "errored": errored,
                "canceled": 0,
                "expired": 0,
            },
            "resumed": n_done > 0,
            "mode": LLM_MODE_SYNC,
            "concurrency": self.concurrency,
        }
        log(f"  {label}: collected {len(raw)}/{n} succeeded replies (sync)")
        return raw, usage, meta
