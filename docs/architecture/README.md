# Architecture

C4 views for **Guidance to Law Comparison** (this repository’s content-audit pipeline).

**Audience:** developers new to the repo, content designers, legal/domain specialists, and stakeholders who need the system shape without implementation detail.

**Diagram format:** canonical sources are D2 under [`docs/diagrams/`](../diagrams/). Generated SVGs are committed. Regenerate with `just diagrams` from the repository root. See [diagram convention](../diagrams/README.md).

## Views

| Level | Doc | Diagram | Answers |
| --- | --- | --- | --- |
| C1 — System Context | [c1-system-context.md](c1-system-context.md) | [c1-system-context.svg](../diagrams/generated/architecture/c1-system-context.svg) | Who uses it, what it does, material externals |
| C2 — Containers | [c2-containers.md](c2-containers.md) | [c2-containers.svg](../diagrams/generated/architecture/c2-containers.svg) | Where major runtime responsibilities live (canonical container view; locked unless the architecture changes) |
| Pipeline (process) | [pipeline.md](pipeline.md) | [end-to-end.svg](../diagrams/generated/pipeline/end-to-end.svg) | Current Guidance → Law journey |
| Proposition comparison (concept) | [proposition-comparison.md](proposition-comparison.md) | [proposition-comparison.svg](../diagrams/generated/concepts/proposition-comparison.svg) | Generalisation direction — not current capability |
| Dependencies | [dependencies.md](dependencies.md) | — | Per-step LLM path, HTTP APIs, stand-up checklist |
| Python data libraries | [python-data-libraries.md](python-data-libraries.md) | — | Per-app libraries that transform content (not CLI/runtime machinery) |

## Related docs

- **Diagram convention (D2):** [docs/diagrams/README.md](../diagrams/README.md)
- **How to run / prerequisites:** [RUNBOOK.md](../../RUNBOOK.md)
- **Component identity:** [`components.manifest.yaml`](../../components.manifest.yaml)
- **Law Proposition Extractor internals:** [system overview](../../law-proposition-extractor/docs/architecture/system-overview.md) · [diagram assets](../../law-proposition-extractor/docs/assets/diagrams/README.md)

C1 → C2 is a zoom-in from system context to runnable containers. C2 groups runtime responsibilities; it is not a stage-order diagram. The pipeline diagram is a **process** view of today’s Guidance → Law product. The proposition-comparison concept diagram is a **generalisation direction**, not a claim that Matcher is source-agnostic.
