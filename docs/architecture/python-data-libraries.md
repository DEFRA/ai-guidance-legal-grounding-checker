# Python data libraries

What each pipeline app uses to **work on content**, not to run Python or a CLI.

Use this to answer “which libraries actually transform the data, and what do they do?” Stand-up (keys, proxies, HTTP APIs): [dependencies.md](dependencies.md). Declared packages: each app’s `pyproject.toml`.

Out of scope here: Typer, Rich, python-dotenv, Pydantic-as-schema, FastAPI/Uvicorn, SQLAlchemy, Streamlit, httpx used only as an HTTP client, and notebook-only pandas.

## Per-app

| App | Library | What it does |
| --- | --- | --- |
| **Guidance Relevance Filter** | `nltk` | Turns page text and the topic word-list into stemmed tokens, then drops any page that doesn’t share a word with that list — so most of the corpus never costs an LLM call |
| | `anthropic` | Reads the remaining pages twice: a cheap model keeps anything that might be on-topic, then a stronger model throws out false positives |
| **Guidance Proposition Extractor** | `anthropic` | Splits each on-topic guidance page into short, atomic claims (the guidance propositions the rest of the pipeline compares) |
| **Law Discovery** | `pydantic-ai` | Runs structured LLM jobs over LiteLLM: expand the search, score whether a found instrument is relevant, and suggest which related sources to keep |
| | `httpx` | Talks to the Lex legislation API to search and pull candidate instruments |
| **Law Proposition Extractor** | `openai` | Sends legislation fragments to LiteLLM (cloud Anthropic or local Ollama) so they can be turned into atomic legal propositions. The actual XML parsing of legislation.gov.uk is stdlib, not a third-party lib |
| **Proposition Matcher** | `openai` | Asks a local Ollama embedding model to turn every guidance and law proposition into a vector, then a small in-house cosine function keeps only the nearest law candidates |
| | `anthropic` | Looks at those shortlisted pairs and decides the relationship (aligned, conflicting, missing, etc.), then writes a summary per guidance proposition |
| **Match Adjudicator** | `anthropic` | Re-reads Matcher’s uncertain/flagged pairs with the surrounding page and legal context, and can change the call |
| **Audit Assembler** | `beautifulsoup4` | Pulls GOV.UK HTML for each audited page and strips it down to readable prose |
| | `textstat` | Scores that prose with SMOG and converts it into a reading-age number for the frontend |
| **Guidance Discovery** | — | No data/NLP library. It just downloads candidate GOV.UK pages via the public Search and Content APIs |

**Scope Planner** is manual; it has no Python app.

There is no pandas, polars, numpy, scikit-learn, spaCy, FAISS, or lxml in runtime app dependencies. The only classic NLP stack is NLTK (Relevance Filter), BeautifulSoup + textstat (Assembler), and Ollama embeddings with a handwritten cosine (Matcher). Everything else that touches content is an LLM client.

## Related views

- [dependencies.md](dependencies.md) — per-step LLM path, HTTP APIs, stand-up checklist
- [pipeline.md](pipeline.md) — what happens to guidance and law, in order
- [c2-containers.md](c2-containers.md) — where runtime responsibilities live
