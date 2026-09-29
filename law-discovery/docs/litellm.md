# LiteLLM and AI routing

Law Discovery uses AI **only** through **Pydantic AI**. Application code must **not** call OpenAI, Anthropic, Google, Gemini, Ollama, the LiteLLM Python SDK, or other provider SDKs directly.

**LiteLLM is only for model routing.** It is not a discovery substrate and does not replace Lex for finding legal sources.

## Intended stack

```
Law Discovery application code
        ↓
   Pydantic AI          ← typed agents, structured outputs → Pydantic models
        ↓
LiteLLM OpenAI-compatible proxy   ← model routing, provider keys, aliases
        ↓
 underlying model provider        ← OpenAI, Anthropic, Azure, etc. (configured in LiteLLM)
```

## What Pydantic AI is used for (V1)

| Feature | Pydantic output model | Required? |
|---------|----------------------|-----------|
| Category expansion | additional synonyms, rationale | optional |
| Candidate relevance assessment | structured relevance rationale | optional |

All model responses must validate into Pydantic models before Law Discovery uses them in business logic.

## Environment variables

```bash
# AI provider selection (V1: litellm only)
LAW_DISCOVERY_AI_PROVIDER=litellm
LAW_DISCOVERY_AI_MODEL=<model-or-litellm-alias>

# LiteLLM OpenAI-compatible proxy
LAW_DISCOVERY_LITELLM_BASE_URL=http://localhost:4000/v1
LAW_DISCOVERY_LITELLM_API_KEY=<key>
```

| Variable | Required for AI | Description |
|----------|-----------------|-------------|
| `LAW_DISCOVERY_AI_PROVIDER` | yes | Must be `litellm` in V1 |
| `LAW_DISCOVERY_AI_MODEL` | yes | Model name or LiteLLM alias passed to Pydantic AI |
| `LAW_DISCOVERY_LITELLM_BASE_URL` | yes | Proxy base URL including `/v1` |
| `LAW_DISCOVERY_LITELLM_API_KEY` | depends | API key if the proxy requires authentication |

When these are unset, AI features are disabled. **Deterministic commands** (`build-query-plan`, `discover --no-network`, `make-register`, `export-for-law-proposition-extractor`, etc.) work without LiteLLM.

## Configuration behaviour

- `LAW_DISCOVERY_AI_PROVIDER=litellm` → Law Discovery constructs a Pydantic AI model pointing at `LAW_DISCOVERY_LITELLM_BASE_URL`
- Model id comes from `LAW_DISCOVERY_AI_MODEL` (not hard-coded provider names in application code)
- Failures to parse AI output into Pydantic models are errors, not silent fallbacks to raw text

## Local development

Run LiteLLM (or your organisation's shared proxy) separately:

```bash
# illustrative — use your org's LiteLLM setup
litellm --config config.yaml
```

Point Law Discovery at the proxy:

```bash
export LAW_DISCOVERY_AI_PROVIDER=litellm
export LAW_DISCOVERY_AI_MODEL=law-discovery-default
export LAW_DISCOVERY_LITELLM_BASE_URL=http://localhost:4000/v1
export LAW_DISCOVERY_LITELLM_API_KEY=sk-local
```

Check status:

```bash
law-discovery ai-status
```

## Testing

- Unit tests mock HTTP or use deterministic fallbacks
- `pytest` must not require live models or network access
- See `tests/test_ai.py`

## Non-goals

- LiteLLM does not search legislation — use Lex for discovery ([lex-api-notes.md](lex-api-notes.md))
- Law Discovery does not embed LiteLLM as an in-process SDK dependency for routing; the proxy is HTTP OpenAI-compatible
