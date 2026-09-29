# Dependencies

Per-step external dependencies for the content-audit pipeline. Use this to answer “what do I need to stand up?” before an end-to-end run.

Operator commands and install notes: [RUNBOOK.md](../../RUNBOOK.md#prerequisites). Python libraries that transform content: [python-data-libraries.md](python-data-libraries.md).

## Dependency matrix

| Component | LLM path | External HTTP | State |
| --- | --- | --- | --- |
| **Scope Planner** | — (manual) | — | Category brief / GRF category data (manual or baked-in) |
| **Guidance Discovery** | — | GOV.UK Search API, GOV.UK Content API | Filesystem JSON |
| **Guidance Relevance Filter** | Anthropic **direct** (Message Batches) | — | Filesystem JSON |
| **Guidance Proposition Extractor** | Anthropic **direct** (Message Batches) | GOV.UK Content API (re-fetch bodies) | Filesystem JSON |
| **Law Discovery** | LiteLLM **optional** (`law-discovery-fast` → Anthropic) | Lex API | Filesystem JSON |
| **Law Proposition Extractor** | LiteLLM → Anthropic `frontier_*` and/or Ollama `local_*` (heuristic mode = no LLM) | legislation.gov.uk (source fetch) | Filesystem ops/artifacts; optional SQLite URL is non-handoff plumbing |
| **Proposition Matcher** | Anthropic **direct** + Ollama **embeddings** | — | Filesystem JSON |
| **Match Adjudicator** | Anthropic **direct** | — | Filesystem JSON |
| **Audit Assembler** | — | GOV.UK Content API (reading-age / SMOG) | Filesystem cache + seeds → frontend export |

There is **no** shared Redis, S3/blob store, or Postgres for pipeline handoff.

## Shared vs component-local

**Shared across steps**

- `ANTHROPIC_API_KEY` — direct Anthropic clients; also LiteLLM Anthropic backends
- LiteLLM proxy — owned/configured under `law-proposition-extractor/` (`just litellm`), consumed by Law Discovery AI and LPE
- Ollama — LPE `local_*` via LiteLLM; Proposition Matcher embeddings
- GOV.UK Content API — Guidance Discovery, Guidance Proposition Extractor, Audit Assembler reading-age
- Filesystem artifact convention / external `content-audit-data-assets` repo

**Component-local**

- GOV.UK Search API — Guidance Discovery only
- Lex API — Law Discovery only
- legislation.gov.uk live fetch — Law Proposition Extractor (Law Discovery uses Lex for search)
- LPE FastAPI + Next.js UI — optional local surfaces, not required for merge-path handoff

## Stand-up checklist

| Need | Used by |
| --- | --- |
| [uv](https://docs.astral.sh/uv/) + Python 3.13+ | All coded steps |
| `ANTHROPIC_API_KEY` | Guidance Relevance Filter, Guidance Proposition Extractor, Proposition Matcher, Match Adjudicator; LiteLLM frontier aliases |
| [Ollama](https://ollama.com/) + `nomic-embed-text:v1.5` | Proposition Matcher embeddings |
| LiteLLM (`just litellm` in `law-proposition-extractor/`) | Law Discovery AI features, Law Proposition Extractor LLM extraction |
| `LAW_DISCOVERY_LEX_BASE_URL` (+ optional key) | Law Discovery live discovery |
| `LAW_DISCOVERY_LITELLM_BASE_URL` / API key | Law Discovery optional AI |
| `LAW_PROPOSITION_EXTRACTOR_LLM_BASE_URL` / API key / `LITELLM_MASTER_KEY` | Law Proposition Extractor via LiteLLM |
| Writable `DATA=…/content-audit-data-assets/steps` (or equivalent) | All steps |
| `just`, Node.js | Optional — LPE web UI only |

LiteLLM model aliases: [`law-proposition-extractor/config/litellm.yaml`](../../law-proposition-extractor/config/litellm.yaml).

## Footguns (not pipeline infra)

- **LiteLLM `DATABASE_URL`:** if set in the shell, the proxy may expect a Postgres admin DB. Start via `just litellm` (unsets it) or `unset DATABASE_URL`. This is not a pipeline dependency.
- **`LAW_PROPOSITION_EXTRACTOR_DATABASE_URL` (SQLite):** present in LPE `.env.example`; operational handoff and ops store are filesystem-based. Do not treat SQLite as the cross-step store.

## External repos (not vendored)

- **`content-audit-data-assets`** — run artifacts between steps
- **`ai-sdlc-content-audit`** — Audit Assembler output destination (frontend)

## Related views

- [c1-system-context.md](c1-system-context.md)
- [c2-containers.md](c2-containers.md)
- [python-data-libraries.md](python-data-libraries.md)
- [RUNBOOK.md](../../RUNBOOK.md)
