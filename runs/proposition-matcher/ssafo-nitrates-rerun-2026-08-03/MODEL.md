# proposition-matcher run — ssafo-nitrates-rerun-2026-08-03

## Description

Proposition Matcher batch matching run (group-rerank): each Guidance Proposition Extractor guidance proposition is
classified against its surviving Law Proposition Extractor law candidates in a single LLM call, with
a compliance summary per producing proposition. Prompts are shared with the
in-process matcher (`proposition-matcher.matching.prompts`).

## Provenance

- **Guidance (Guidance Proposition Extractor):** `/Users/bram/Code/defra/content-audit-data-assets/steps/susan/runs/ssafo-nvz-3/output.json`
- **Law (Law Proposition Extractor):** `/Users/bram/Code/defra/content-audit-data-assets/steps/judit/runs/ssafo-nitrates-2-export/beatrice_law_candidates.json` (source=`candidates`)
- **Model:** Anthropic `claude-sonnet-4-6` via the Message Batches API (50% cost).
- **Strategy:** group-rerank — local nomic embeddings + cosine retrieval
  (threshold 0.65, gap 0.04, top-15), then one
  grouped LLM call per guidance proposition.
  Candidates mode embeds `matching_text` and shows `statement_text` to the LLM;
  propositions mode embeds/displays `proposition_text`.

## Started

2026-08-03T18:28:47

## Headline

- **Guidance propositions:** 217
- **Law units:** 500 (`candidates`)
- **Guidance props with survivors (LLM calls):** 215
- **Guidance props empty (no candidate, free):** 2

## Cost & runtime

- **Tokens:** 519,019 in / 216,471 out
- **Cost:** **$2.4021** total — group-rerank $1.9321, summarise $0.47 (batch-discounted)
- **Time (wall-clock):**
  - local (embed + retrieve): 0m19s
  - group-rerank batch (submit → ended, incl. queue wait): 9m08s
  - summarise batch (incl. queue wait): 5m05s
  - **total: 14m34s**

Full machine-readable breakdown in `metrics.json`.
