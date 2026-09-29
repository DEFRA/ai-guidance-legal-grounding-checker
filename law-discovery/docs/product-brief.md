# Law Discovery product brief

## What Law Discovery is

Law Discovery is a **standalone** legal source discovery workbench. It lives in its own repository and has **no dependency on Law Proposition Extractor or Proposition Matcher code**.

Given a **category brief** — label, description, optional synonyms, exclusions, and jurisdiction hints — Law Discovery finds **candidate** UK legal instruments and interpretive materials, explains why they may be relevant, and helps a human curate a **source register** for downstream use.

Law Discovery outputs a reviewable register. It does **not** guarantee complete legal coverage.

## Product boundaries

| Product | Responsibility |
|---------|----------------|
| **Law Discovery** | Find candidate legal sources; score and explain possible relevance; support human curation; export register and Law Proposition Extractor handoff JSON |
| **Law Proposition Extractor** | Turn **accepted** Law Discovery sources into source-backed legal propositions |
| **Proposition Matcher** | Check guidance against Law Proposition Extractor propositions |

```
Category brief → Law Discovery (discovery + curation) → Source register
                                                    ↓
                                    Selected sources (JSON handoff)
                                                    ↓
                                         Law Proposition Extractor (propositions)
                                                    ↓
                                    Proposition Matcher (guidance vs law)
```

## What Law Discovery does

- Accept a category brief as structured input
- Generate a deterministic query plan from synonyms and exclusions
- Search Lex API / Lex Graph as the first candidate discovery substrate
- Normalise candidate sources into a common shape
- Apply simple deterministic scoring; optionally enrich with Pydantic AI
- Record human review status per entry
- Export a JSON source register
- Export selected sources for Law Proposition Extractor via a versioned JSON contract

## What Law Discovery does not do

- Guarantee completeness of legal coverage
- Draw final legal conclusions or provide legal advice
- Extract legal propositions (Law Proposition Extractor)
- Compare guidance against law (Proposition Matcher)
- Persist data in a database (V1)
- Provide a web UI (V1)

## AI usage

When configured, Law Discovery may use **Pydantic AI** for:

- Category expansion (additional synonyms, search terms)
- Candidate relevance assessment (structured rationale)

All AI calls route through a **LiteLLM OpenAI-compatible proxy**. Deterministic commands work without any AI configuration.

## Primary artefacts

| Artefact | Description |
|----------|-------------|
| Category brief | Input definition for a discovery topic |
| Query plan | Deterministic search plan derived from the brief |
| Discovery run | Candidates returned from Lex plus scores |
| Source register | Curated, reviewable list of sources |
| Law Proposition Extractor handoff | JSON export of accepted sources only |

See [v1-process.md](v1-process.md) for the V1 workflow and [source-register-schema.md](source-register-schema.md) for output shapes.

## Users

- Legal researchers scoping sources for a policy category
- Analysts reviewing and accepting/rejecting candidates
- Engineers integrating Law Discovery into discovery workflows ahead of Law Proposition Extractor ingestion
