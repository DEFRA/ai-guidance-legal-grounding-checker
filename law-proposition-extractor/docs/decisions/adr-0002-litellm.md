# ADR-0002: Use LiteLLM as the LLM gateway

## Status

Accepted

## Decision

All model traffic goes through LiteLLM.

## Why

This keeps local/private and cloud model usage behind one interface and makes routing policies explicit.
