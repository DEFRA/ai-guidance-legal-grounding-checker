r"""Guidance Relevance Filter's pass 2: precision adjudication of pass-1 positives.

Pass 1 is recall-maximised — its prompt drops the Exclusion Criteria and forces
the label TRUE on any category keyword mention, even an incidental one. That
over-includes homonyms, wrong-domain mentions, and pages that merely name the
topic once in a list. Pass 2 re-reads the body of every page pass 1 labelled
TRUE and, with the team's Exclusion Criteria re-introduced, drops those false
positives.

Because it only ever turns a TRUE into a FALSE, the exclusion criteria cost pass 1
no recall: the ~98% of pages the word-search never routed are untouched. The
prompt is tuned to the recall-priority operating point — it removes only
unambiguous out-of-scope noise and keeps anything with real audit value for the
category.

No silent fallbacks: a page whose verdict cannot be parsed is left exactly as
pass 1 labelled it (kept) and counted in ``n_unadjudicated`` — never quietly
dropped. The full pass-1-vs-pass-2 trail is returned for a side audit file, kept
off the pipeline output.
"""
from __future__ import annotations

import json
import os
import warnings

from ._batch import log
from .checkpoint import Checkpoint
from .completions import CompletionRequest, Completions
from .funnel import PASS2_DROP, PASS2_KEEP, PASS2_UNADJUDICATED, stamp


def _resolve_adjudicator_model() -> str:
    """Canonical env with legacy RADIA_* alias. COMPAT_LEGACY_NAME remove in rename+1."""
    canon = "GUIDANCE_RELEVANCE_FILTER_ADJUDICATOR_MODEL"
    legacy = "RADIA_ADJUDICATOR_MODEL"
    c, l = os.getenv(canon), os.getenv(legacy)
    if c is not None and l is not None and c != l:
        raise RuntimeError(
            f"Conflicting environment values for {canon}={c!r} and {legacy}={l!r}."
        )
    if c is not None:
        return c
    if l is not None:
        warnings.warn(
            f"Legacy env {legacy!r} is deprecated; use {canon!r}. Removed in rename+1.",
            DeprecationWarning,
            stacklevel=2,
        )
        return l
    return "claude-sonnet-4-6"


DEFAULT_ADJUDICATOR_MODEL = _resolve_adjudicator_model()
MAX_TOKENS = 500


def full_spec(category: dict) -> str:
    """The complete category definition — inclusion description + exclusion criteria.

    Pass 1 uses only ``description`` (no exclusion); pass 2 needs both halves so the
    adjudicator can reason about what is out of scope.
    """
    spec = category["description"]
    exclusion = category.get("exclusion_criteria", "").strip()
    return f"{spec}\n\n{exclusion}" if exclusion else spec


def _format_hint_bullets(items: list[str]) -> str:
    if not items:
        return ""
    return "\n".join(f"- {item}" for item in items)


def build_prompt(category: dict, title: str, body: str, pass1_reason: str) -> str:
    """The recall-priority adjudication prompt for the baked-in category."""
    name = category["name"]
    spec = full_spec(category)
    hints = category.get("adjudication_hints") or {}
    keep_hints = _format_hint_bullets(hints.get("keep") or [])
    drop_hints = _format_hint_bullets(hints.get("drop") or [])

    keep_section = ""
    if keep_hints:
        keep_section = (
            f"\nKEEP examples (keep = true) — lean toward keeping when similar "
            f"content appears:\n{keep_hints}\n"
        )
    drop_section = ""
    if drop_hints:
        drop_section = (
            f"\nDROP examples (keep = false) — drop only when clearly similar to:\n"
            f"{drop_hints}\n"
        )

    title_line = f"Page title: {title}\n" if title else ""
    return (
        f"You curate a DEFRA guidance corpus for a {name.upper()} policy/legislation "
        f"audit. A fast first pass flagged this page because a {name} keyword "
        "appears; it forces TRUE on any mention. Remove ONLY pages that are clearly "
        f"not about {name} at all. Missing a genuinely {name}-relevant page is "
        "unacceptable; keeping a borderline one is fine. Default to KEEP.\n\n"
        f"=== {name.upper()} CATEGORY SPEC ===\n{spec}\n"
        "=== END SPEC ===\n\n"
        "Apply the inclusion and exclusion criteria above.\n"
        f"KEEP (keep = true) — keep if the page has any audit-relevant {name} "
        "content per the inclusion spec, even briefly.\n"
        "DROP (keep = false) — drop ONLY when the page is clearly out of scope per "
        "the exclusion criteria (homonyms, incidental-only mentions, wrong domain).\n"
        f"{keep_section}{drop_section}"
        "If you are unsure, KEEP.\n\n"
        f"For context, the first pass wrote this note (it may be wrong): {pass1_reason!r}\n\n"
        f"{title_line}\nPage content:\n{body}\n\n"
        "Return ONLY a JSON object:\n"
        "{\n"
        '  "keep": true|false,\n'
        '  "exclusion_hit": "none"|"incidental"|"homonym"|"wrong_domain",\n'
        '  "verdict_reason": "1-2 sentences citing the specific evidence"\n'
        "}"
    )


def parse_verdict(text: str) -> dict | None:
    """Parse an adjudicator reply into ``{keep, exclusion_hit, verdict_reason}``.

    Returns None for an unparseable reply or one missing the verdict — the caller
    keeps such a page rather than guessing.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if "keep" not in parsed:
        return None
    return {
        "keep": bool(parsed["keep"]),
        "exclusion_hit": str(parsed.get("exclusion_hit", "none")),
        "verdict_reason": str(parsed.get("verdict_reason", "")),
    }


def adjudicate(
    items: list[dict],
    results: list[dict],
    categories: list[dict],
    *,
    model: str = DEFAULT_ADJUDICATOR_MODEL,
    max_words: int = 60000,
    checkpoint: Checkpoint | None = None,
    completions: Completions | None = None,
) -> tuple[list[dict], dict, list[dict]]:
    """Re-adjudicate pass-1 positives in place. Returns (results, stats, audit).

    ``results`` is pass 1's labelled output (``body_text`` already dropped); bodies
    are joined back from ``items`` by URL. Each positive's ``labels``/``reasons`` are
    updated to the pass-2 verdict; ``funnel.pass1_reason`` is preserved so the
    pass-1 note survives the overwrite. Everything else is left untouched.
    """
    category = categories[0]
    cat = category["name"]
    bodies = {it["url"]: (it["meta_data"].get("body_text") or "") for it in items}

    positives = [r for r in results if r["meta_data"]["labels"].get(cat) is True]
    stats = {
        "n_positives": len(positives),
        "n_kept": 0,
        "n_dropped": 0,
        "n_unadjudicated": 0,
        "model": model,
        "batch": None,
        "resumed": False,
        "usage": {"model": model, "batch": {"input": 0, "output": 0}},
    }
    audit: list[dict] = []
    if not positives:
        log(f"Pass 2: 0 pass-1 positives of {len(results)} pages; skipping adjudication")
        return results, stats, audit
    if completions is None:
        raise RuntimeError("completions is required when pass-1 positives need adjudication")
    log(
        f"Pass 2: {len(positives)} pass-1 positives of {len(results)} pages → adjudicate"
    )

    requests: list[CompletionRequest] = []
    truncated: dict[str, tuple[int, int]] = {}
    for i, r in enumerate(positives):
        md = r["meta_data"]
        body = bodies.get(r["url"], "")
        words = body.split()
        if len(words) > max_words:
            truncated[r["url"]] = (max_words, len(words))
            body = " ".join(words[:max_words])
        prompt = build_prompt(
            category, md.get("title", ""), body, md.get("reasons", {}).get(cat, "")
        )
        requests.append(
            CompletionRequest(
                custom_id=str(i),
                model=model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        )

    if checkpoint is not None:
        checkpoint.record_pass2_positives([r["url"] for r in positives])
    resume_id = checkpoint.pass2_batch_id if checkpoint is not None else None
    already = checkpoint.pass2_replies if checkpoint is not None else None
    stats["resumed"] = bool(resume_id or already)

    def _remember(batch_id: str) -> None:
        if checkpoint is not None:
            checkpoint.record_pass2_batch(batch_id)

    def _on_result(custom_id: str, text: str, usage: dict) -> None:
        if checkpoint is not None:
            checkpoint.record_pass2_reply(custom_id, text, usage)

    raw, batch_usage, stats["batch"] = completions.complete_many(
        requests, label="adjudicate",
        resume_id=resume_id, already=already,
        on_submitted=_remember, on_result=_on_result,
    )
    stats["usage"] = {"model": model, "batch": batch_usage}

    for i, r in enumerate(positives):
        md = r["meta_data"]
        funnel = md.get("funnel") or {}
        pass1_reason = funnel.get("pass1_reason") or md.get("reasons", {}).get(cat, "")
        rec = {
            "url": r["url"],
            "pass1_score": md.get("scores", {}).get(cat),
            "pass1_reason": pass1_reason,
        }
        verdict = parse_verdict(raw.get(str(i), ""))

        if verdict is None:
            stats["n_unadjudicated"] += 1
            md["reasons"][cat] = (
                "[pass-2 adjudication unavailable — kept as pass-1 labelled it] "
                + pass1_reason
            )
            stamp(
                md, PASS2_UNADJUDICATED,
                pass1_label=True,
                pass1_score=rec["pass1_score"],
                pass1_reason=pass1_reason,
                pass2_keep=True,
                pass2_reason="adjudication unavailable",
                exclusion_hit="unadjudicated",
            )
            audit.append({
                **rec, "stage": PASS2_UNADJUDICATED, "pass2_keep": True,
                "exclusion_hit": "unadjudicated",
                "pass2_reason": "adjudication unavailable",
            })
            continue

        note = verdict["verdict_reason"]
        if r["url"] in truncated:
            mw, orig = truncated[r["url"]]
            note = f"[body truncated to {mw} words from {orig}] " + note
        md["labels"][cat] = verdict["keep"]
        md["reasons"][cat] = note
        stage = PASS2_KEEP if verdict["keep"] else PASS2_DROP
        stamp(
            md, stage,
            pass1_label=True,
            pass1_score=rec["pass1_score"],
            pass1_reason=pass1_reason,
            pass2_keep=verdict["keep"],
            pass2_reason=note,
            exclusion_hit=verdict["exclusion_hit"],
        )
        if verdict["keep"]:
            stats["n_kept"] += 1
        else:
            stats["n_dropped"] += 1
        audit.append({
            **rec, "stage": stage, "pass2_keep": verdict["keep"],
            "exclusion_hit": verdict["exclusion_hit"], "pass2_reason": note,
        })

    log(
        f"Pass 2 done: kept={stats['n_kept']} dropped={stats['n_dropped']} "
        f"unadjudicated={stats['n_unadjudicated']}"
    )
    return results, stats, audit
