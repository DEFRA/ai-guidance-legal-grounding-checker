# Law Proposition Extractor explainability handbook

Law Proposition Extractor turns authoritative legal sources into reviewable legal units and records
**why** each retained unit was selected, composed, classified, grouped, linked,
and contextualised.

## What is Law Proposition Extractor doing?

Law Proposition Extractor consumes source-register / case inputs, fetches and snapshots legal text,
parses structural fragments, extracts **propositions** (atomic legal statements),
then builds deterministic legal structure on top: legal-effect classification,
legal rule groups, typed relationships (`exception_to`, `triggered_by`),
effective-law statements with required context, Proposition Matcher matching candidates,
and optional divergence assessment for human review in the Workbench.

## What does “explainability” mean here?

**Law Proposition Extractor explanations describe the recorded processing decisions that created an
output. They are not model chain-of-thought and do not replace legal review.**

A `DecisionExplanation` is execution evidence emitted at the decision site:
subject, outcome, rule ID/version, deterministic summary, and structured
evidence. The Workbench “Why did Law Proposition Extractor produce this?” panel projects those
records; it does not invent new reasoning.

## Which parts use an LLM?

Typically:

- frontier / local **proposition extraction** (structured row proposals)
- optional **divergence reasoning** when that mode is enabled

## Which parts are deterministic?

Typically:

- source fetch, snapshot, parse, structural hierarchy
- fragment selection / extraction frontier rules
- structured-list reconciliation (composition, deduplication)
- legal-effect classification
- legal rule groups and typed relationships
- effective-law context expansion
- Proposition Matcher candidate projection
- decision-explanation emission and Workbench projection

Configuration selects required locators and run modes. Humans review and decide
governance outcomes. Deterministic post-processing does **not** prove
substantive legal correctness.

## Where can I inspect why one statement was produced?

1. Open the statement in the Review Workbench.
2. Expand **Why did Law Proposition Extractor produce this?**
3. Read Overview → stage timeline/evidence → technical details.
4. Or inspect `decision_explanations.json` in the export bundle.

## Handbook map

| Document | Audience emphasis | Contents |
| --- | --- | --- |
| [Concepts](concepts.md) | Lawyer / policy | Plain-language legal units and required distinctions |
| [Pipeline](pipeline.md) | All | Stage order, methods, LLM vs deterministic split |
| [Diagrams](diagrams.md) | All (meeting script) | Visual explainability suite (D2 → SVG) |
| [Heuristics](heuristics.md) | Developer / auditor | Generated catalogue from the typed registry |
| [Artifacts and lineage](artifacts-and-lineage.md) | Developer / auditor | Artifact producers, consumers, ID joins |
| [Article 49a walkthrough](article-49a-walkthrough.md) | All | Generated worked example from the acceptance fixture |
| [Structural-source fixtures](structural-source-fixtures.md) | Developer / auditor | Offline multi-instrument hierarchy/heading contract |
| [Proposition-fidelity benchmark](proposition-fidelity-benchmark.md) | Developer / auditor / lawyer | Offline multi-instrument operative-claim fidelity |
| [Live proposition calibration](live-proposition-calibration.md) | Developer / auditor | Live frontier + prompt v3 vs gold contracts |
| [Glossary](glossary.md) | All | Controlled terminology |

## Related references

- Workbench panel contract (this handbook’s README history lives here; see also the panel section below)
- [Effective-law layers](../architecture/effective-law-layers.md)
- [Pipeline overview](../architecture/pipeline-overview.md)
- [Artifact map](../reference/artifacts.md)
- [Law Proposition Extractor README](../../README.md)
- Offline fixture: `tests/fixtures/article_49a_legal_structure/`
- Structural-source matrix: `tests/fixtures/structural_source/` (`just check-structural-fixtures`)
- Proposition-fidelity matrix: `tests/fixtures/proposition_fidelity/` (`just check-proposition-fidelity-benchmark`)
- Live calibration artifacts: `calibration/proposition_fidelity/<run-id>/` (`just run-live-proposition-calibration`)

### Structural-source vs proposition fidelity vs legal review

| Contract | Question |
| --- | --- |
| Structural-source fidelity | Did Law Proposition Extractor parse the source hierarchy and context correctly? |
| Proposition fidelity | Did Law Proposition Extractor represent the operative legal claims correctly? |
| Legal review | Is the interpretation acceptable for the intended legal use? |

Benchmark passing does **not** replace legal review.

## Workbench “Why?” panel

The panel loads:

- `GET /ops/decision-explanations`
- `GET /ops/heuristics?referenced_only=true`

It shows overview, stage timeline with evidence, and technical details. Older
runs without `decision_explanations.json` keep source evidence and legal
context, and show that detailed decision explanations were not recorded.

## Regenerating generated sections

```bash
just generate-explainability-docs
just check-explainability-docs
# diagram suite only:
just generate-explainability-diagrams
just check-explainability-diagrams
# equivalent:
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline.explainability_docs generate
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline.explainability_docs check
```

Generated Markdown sections are marked with `<!-- BEGIN GENERATED: … -->` /
`<!-- END GENERATED: … -->`. Hand-written prose outside those markers is
preserved. Diagram sources live under
`docs/assets/diagrams/explainability/`; rendered SVGs under
`docs/assets/generated/diagrams/explainability/`. See [Diagrams](diagrams.md).
