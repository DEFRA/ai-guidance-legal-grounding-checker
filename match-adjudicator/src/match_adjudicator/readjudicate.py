"""Core transform: re-adjudicate Proposition Matcher's flagged top-matches with page context.

Match Adjudicator reads Proposition Matcher's ``results.json`` (a list of guidance propositions, each with
a best-first ``matches`` list) and re-judges the *top* match — the one Audit Assembler
surfaces — whenever its relationship is CONFLICTS or GUIDANCE_INCOMPLETE. Page
context is the other guidance propositions sharing the same ``url``.

The decision is committed in place: the top match's ``relationship`` (and its
``explanation``) are overwritten with Match Adjudicator's verdict and reason. The output keeps
Proposition Matcher's exact schema, so ``audit-assembler build --proposition-matcher-run <match-adjudicator-run>`` consumes it
unchanged. A separate report records every change for human audit.
"""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from collections.abc import Callable
from typing import Any, TypedDict

from .cost import add_usage, new_usage
from .prompt import ALLOWED_NEW, build_prompt

# Verdicts Match Adjudicator re-examines. Accepts Proposition Matcher's CONFLICT/CONFLICTS spelling.
_FLAGGED = {"CONFLICTS", "CONFLICT", "GUIDANCE_INCOMPLETE"}


def _canonical(relationship: str | None) -> str:
    r = (relationship or "").strip().upper()
    return "CONFLICTS" if r == "CONFLICT" else r


class Finding(TypedDict):
    """One flagged top-match queued for re-adjudication. The judge reads the
    context fields; ``_top`` is the live match dict the verdict commits back into."""
    guidance_text: str
    law_text: str
    law_id: str | None
    old_status: str
    explanation: str | None
    siblings: list[str]
    guidance_source_url: str | None
    _top: dict


# A batch judge takes ALL flagged findings at once and returns one verdict
# ({"new_status", "reason"}) per finding, aligned by index. Batch-shaped because
# Match Adjudicator's production judge submits a single Anthropic Message Batch.
BatchJudge = Callable[[list[Finding]], list[dict[str, str]]]


def page_siblings(matcher_output: list[dict]) -> dict[str, list[str]]:
    """Map each page URL to the guidance proposition texts on it."""
    by_url: dict[str, list[str]] = defaultdict(list)
    for entry in matcher_output:
        url = entry.get("url")
        text = entry.get("proposition_text")
        if url and text:
            by_url[url].append(text)
    return by_url


def collect_flagged(output: list[dict], by_url: dict[str, list[str]]) -> list[Finding]:
    """Gather every top match flagged CONFLICTS/GUIDANCE_INCOMPLETE plus the page
    context the judge needs. The findings hold live references to ``output``'s
    match dicts, so committing a verdict to ``_top`` mutates ``output`` in place."""
    findings: list[Finding] = []
    for entry in output:
        matches = entry.get("matches") or []
        if not matches:
            continue
        top = matches[0]
        old_status = _canonical(top.get("relationship"))
        if old_status not in _FLAGGED:
            continue
        guidance_text = entry.get("proposition_text", "")
        siblings = [s for s in by_url.get(entry.get("url", ""), [])
                    if s != guidance_text]
        law = top.get("law_proposition") or {}
        findings.append(Finding(
            guidance_text=guidance_text,
            law_text=law.get("proposition_text", ""),
            law_id=law.get("id"),
            old_status=old_status,
            explanation=top.get("explanation"),
            siblings=siblings,
            guidance_source_url=entry.get("url"),
            _top=top,
        ))
    return findings


def readjudicate(
    matcher_output: list[dict],
    judge: BatchJudge,
) -> tuple[list[dict], dict[str, Any]]:
    """Return (corrected_output, report). Does not mutate the input.

    Collects every flagged finding, judges them in a single batch, then commits
    each changed verdict back into its top match in place — keeping Proposition Matcher's
    exact schema so Audit Assembler consumes the result unchanged."""
    output = copy.deepcopy(matcher_output)
    by_url = page_siblings(output)
    findings = collect_flagged(output, by_url)

    verdicts = judge(findings) if findings else []
    if len(verdicts) != len(findings):
        raise ValueError(
            f"judge returned {len(verdicts)} verdicts for {len(findings)} findings")

    changes: list[dict] = []
    for finding, verdict in zip(findings, verdicts, strict=True):
        old_status = finding["old_status"]
        new_status = verdict["new_status"]
        if new_status == old_status:
            continue
        changes.append({
            "guidance_proposition_text": finding["guidance_text"],
            "guidance_source_url": finding["guidance_source_url"],
            "law_id": finding["law_id"],
            "old_status": old_status,
            "new_status": new_status,
            "anna_reason": verdict["reason"],
            "beatrice_reason": finding["explanation"],
        })
        top = finding["_top"]
        top["relationship"] = new_status
        top["explanation"] = verdict["reason"]

    downgrades = [c for c in changes if c["new_status"] == "GROUNDED"]
    report = {
        "n_guidance_propositions": len(output),
        "n_flagged_reviewed": len(findings),
        "n_changed": len(changes),
        "n_cleared_to_grounded": len(downgrades),
        "by_old_status": {
            s: sum(1 for c in changes if c["old_status"] == s)
            for s in sorted({c["old_status"] for c in changes})
        },
        "changes": changes,
    }
    return output, report


# ── LLM judge (Anthropic Message Batches API) ────────────────────────────────


def _parse_json_obj(raw: str) -> dict:
    # Decode the first complete JSON object and ignore any trailing prose the
    # model adds after it (a chatty verdict is still a valid verdict).
    start = raw.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in LLM response: {raw!r}")
    obj, _ = json.JSONDecoder().raw_decode(raw, start)
    return obj


def _parse_verdict(raw: str) -> dict[str, str]:
    data = _parse_json_obj(raw)
    new_status = str(data.get("new_status", "")).strip().upper()
    if new_status not in ALLOWED_NEW:
        # No silent fallback: a malformed verdict must surface, not pass through.
        raise ValueError(f"invalid new_status {new_status!r} (from {data!r})")
    return {"new_status": new_status, "reason": str(data.get("reason", ""))[:400]}


def _message_text(message) -> str:
    return next((b.text for b in message.content if getattr(b, "type", None) == "text"), "")


def make_anthropic_batch_judge(
    model: str, *, max_tokens: int = 1024, poll_seconds: int = 30,
) -> BatchJudge:
    """Build a batch judge backed by the Anthropic Message Batches API (50% cost).

    Submits one request per flagged finding, polls until the batch ends, then
    returns verdicts in finding order. Reads ANTHROPIC_API_KEY.

    The returned judge carries a ``.usage`` dict (token totals across the batch)
    and its ``.model``, so the caller can record the run's cost."""
    import time

    import anthropic
    from anthropic.types.message_create_params import (
        MessageCreateParamsNonStreaming as Params,
    )
    from anthropic.types.messages.batch_create_params import Request

    client = anthropic.Anthropic()
    usage = new_usage()

    def judge(findings: list[Finding]) -> list[dict[str, str]]:
        if not findings:
            return []
        requests = [
            Request(
                custom_id=f"a-{i}",
                params=Params(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": build_prompt(
                        guidance_text=f["guidance_text"], law_text=f["law_text"],
                        old_status=f["old_status"], explanation=f["explanation"],
                        siblings=f["siblings"],
                    )}],
                ),
            )
            for i, f in enumerate(findings)
        ]

        batch = client.messages.batches.create(requests=requests)
        print(f"[match-adjudicator] submitted batch {batch.id} ({len(requests)} findings)", flush=True)
        while True:
            b = client.messages.batches.retrieve(batch.id)
            if b.processing_status == "ended":
                break
            c = b.request_counts
            print(f"[match-adjudicator] {b.processing_status}: proc={c.processing} "
                  f"ok={c.succeeded} err={c.errored}", flush=True)
            time.sleep(poll_seconds)

        raw_by_id: dict[str, str] = {}
        for r in client.messages.batches.results(batch.id):
            if r.result.type != "succeeded":
                # No silent fallback: a failed request must surface.
                raise RuntimeError(f"batch request {r.custom_id} {r.result.type}: {r.result}")
            add_usage(usage, r.result.message)
            raw_by_id[r.custom_id] = _message_text(r.result.message)

        verdicts: list[dict[str, str]] = []
        for i in range(len(findings)):
            raw = raw_by_id.get(f"a-{i}")
            if raw is None:
                raise RuntimeError(f"batch returned no result for finding a-{i}")
            verdicts.append(_parse_verdict(raw))
        return verdicts

    judge.usage = usage
    judge.model = model
    return judge
