# ADR-0008: Operate LiteLLM as an external gateway sidecar

## Status

Accepted

## Context

Law Proposition Extractor code talks to an OpenAI-compatible endpoint via `LAW_PROPOSITION_EXTRACTOR_LLM_BASE_URL` (default `http://127.0.0.1:4000/v1`) and does not embed LiteLLM internals. Local development starts LiteLLM proxy as a separate process (`uvx litellm[proxy] ...`) with model routing in `config/litellm.yaml`.

## Decision

LiteLLM is run as an external sidecar gateway process, while Law Proposition Extractor keeps only a thin client package for gateway access and model-profile usage.

## Consequences

Model routing and provider policy stay operationally decoupled from application code, and gateway upgrades can happen without changing pipeline logic. Runtime now depends on sidecar availability and correct environment wiring.
