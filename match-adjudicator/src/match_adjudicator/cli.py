"""Match Adjudicator CLI — re-adjudicate Proposition Matcher's flagged findings with page context.

    match-adjudicator readjudicate \
        --proposition-matcher-run <proposition-matcher/runs/NAME> \
        --dest         <match-adjudicator/runs/NAME>

Reads Proposition Matcher's ``results.json``, re-judges every top match flagged CONFLICTS or
GUIDANCE_INCOMPLETE against the rest of its page's guidance via the Anthropic
Message Batches API (50% cost), and writes a corrected run in Proposition Matcher's own shape
(``results.json``) so Audit Assembler can consume it
unchanged:

    audit-assembler build --proposition-matcher-run <match-adjudicator/runs/NAME> ...

The decision is committed: a flagged finding either stays flagged or becomes
GROUNDED. ``match_adjudicator_report.json`` records every change for audit.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from .cost import cost_usd
from .readjudicate import (


def _producer_fields() -> dict:
    return {
        "producer_component": "match-adjudicator",
        "source_kind": "pipeline",
        "component_id": "match-adjudicator",
    }

    collect_flagged,
    make_anthropic_batch_judge,
    page_siblings,
    readjudicate,
)

app = typer.Typer(add_completion=False, help=__doc__)


@app.callback()
def _main() -> None:
    """Match Adjudicator — re-adjudicate Proposition Matcher's flagged findings before Audit Assembler renders them."""


def _load(path: Path):
    with path.open() as f:
        return json.load(f)


def _write(path: Path, data) -> None:
    with path.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _write_model_card(dest: Path, m: dict, started_at: str) -> None:
    t = m["tokens"]
    (dest / "MODEL.md").write_text(f"""# match-adjudicator run — {dest.name}

## Description

Match Adjudicator re-adjudicates Proposition Matcher's flagged top-matches (CONFLICTS / GUIDANCE_INCOMPLETE)
against the rest of each page's guidance, via the Anthropic Message Batches API
(50% cost). Output keeps Proposition Matcher's schema so Audit Assembler consumes it unchanged.

## Provenance

- **Proposition Matcher run:** `{m['proposition_matcher_run']}`
- **Model:** Anthropic `{m['model']}` via the Message Batches API (50% cost).

## Started

{started_at}

## Headline

- **Guidance propositions:** {m['n_guidance_propositions']}
- **Flagged findings reviewed (LLM calls):** {m['n_flagged_reviewed']}
- **Findings changed:** {m['n_changed']}

## Cost

- **Tokens:** {t['input']:,} in / {t['output']:,} out
- **Cost:** **${m['cost_usd']}** (batch-discounted)

Full machine-readable breakdown in `metrics.json`; per-change audit in `match_adjudicator_report.json`.
""")


@app.command(name="readjudicate")
def readjudicate_cmd(
    proposition_matcher_run: Annotated[Path, typer.Option(
        "--proposition-matcher-run", help="Proposition Matcher run dir (results.json)")],
    dest: Annotated[Path, typer.Option(
        "--dest", help="Match Adjudicator run dir to write (Proposition Matcher-shaped: results.json)")],
    model: Annotated[str, typer.Option(help="Anthropic model")] = "claude-sonnet-4-6",
    poll_seconds: Annotated[int, typer.Option(help="Batch poll interval (s)")] = 30,
    dry_run: Annotated[bool, typer.Option(
        help="Count flagged findings without submitting the batch")] = False,
) -> None:
    output_path = proposition_matcher_run / "results.json"
    if not output_path.exists():
        sys.exit(f"no results.json in Proposition Matcher run: {output_path}")

    matcher_output = _load(output_path)

    if dry_run:
        # No API spend: count what the batch would judge, then stop.
        flagged = collect_flagged(matcher_output, page_siblings(matcher_output))
        print(f"[dry-run] would submit {len(flagged)} flagged findings to the "
              f"batch API ({model}); stopping before any spend.")
        return

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    judge = make_anthropic_batch_judge(model, poll_seconds=poll_seconds)
    corrected, report = readjudicate(matcher_output, judge)
    report["model"] = model
    report["proposition_matcher_run"] = str(proposition_matcher_run)

    usage = dict(judge.usage)
    cost = round(cost_usd(usage, model, batch=True), 4)
    report["tokens"] = usage
    report["cost_usd"] = cost
    metrics = {
        "model": model,
        "proposition_matcher_run": str(proposition_matcher_run),
        "n_guidance_propositions": report["n_guidance_propositions"],
        "n_flagged_reviewed": report["n_flagged_reviewed"],
        "n_changed": report["n_changed"],
        "tokens": usage,
        "cost_usd": cost,
        "started_at": started_at,
    }

    print(
        f"reviewed {report['n_flagged_reviewed']} flagged findings; "
        f"changed {report['n_changed']} "
        f"({report['n_cleared_to_grounded']} cleared to GROUNDED). "
        f"by old status: {report['by_old_status'] or '{}'} "
        f"| ${cost}"
    )

    dest.mkdir(parents=True, exist_ok=True)
    _write(dest / "results.json", corrected)
    _write(dest / "match_adjudicator_report.json", report)
    _write(dest / "metrics.json", metrics)
    _write_model_card(dest, metrics, started_at)

    print(f"wrote {dest / 'results.json'} and {dest / 'match_adjudicator_report.json'}")


if __name__ == "__main__":
    app()
