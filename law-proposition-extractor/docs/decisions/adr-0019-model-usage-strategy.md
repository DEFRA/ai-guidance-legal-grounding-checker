# ADR-0019: Model usage strategy

## Status

Accepted

## Context

Law Proposition Extractor processes legal texts into structured propositions. Many systems rely heavily on language models, which reduces auditability and trust.

## Decision

Law Proposition Extractor adopts a deterministic-first pipeline with controlled model usage.

- Source intake, categorisation, and completeness are deterministic
- Proposition extraction may use a local model
- Divergence reasoning may optionally use a frontier model
- Narrative output is template-based

## Consequences

- Improved auditability
- Reproducible outputs
- Clear separation between deterministic and model-assisted logic
- Easier governance and review

## Related ADRs

- ADR-0014 (Proposition-first architecture)
- ADR-0009 (Source provenance)
