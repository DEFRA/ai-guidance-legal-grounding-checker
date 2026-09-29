# Law Proposition Extractor pipeline (explainability view)

This documents the **current** Law Proposition Extractor pipeline as implemented in
`law_proposition_extractor_pipeline.runner` and `law_proposition_extractor_pipeline.export`, not an aspirational design.

Product shape: **source → propositions → legal structure → review**.
Divergence is optional. Workbench review consumes export artifacts via the ops
API.

## Data-flow overview

```mermaid
flowchart TD
  Law Discovery["Law Discovery / source-register intake"] --> Fetch["Source fetch and snapshot"]
  Fetch --> Parse["Parse and structural hierarchy"]
  Parse --> Manifest["Manifestation and source-effect parsing"]
  Manifest --> Select["Fragment selection / extraction frontier"]
  Select --> ExtractReq["Extraction request"]
  ExtractReq --> Reconcile["Structured-list reconciliation"]
  Reconcile --> Props["Proposition construction"]
  Props --> Classify["Post-extraction classification"]
  Classify --> Complete["Completeness and scope"]
  Complete --> Groups["Legal rule groups"]
  Groups --> Generic["Generic locator relationships"]
  Generic --> Typed["Typed legal relationships"]
  Typed --> Eff["Effective-law statements"]
  Eff --> Proposition Matcher["Proposition Matcher candidates"]
  Proposition Matcher --> Div["Optional divergence"]
  Div --> Review["Workbench review"]
```

## Stage table

| Stage | Purpose | Principal inputs | Principal outputs | Artifacts | Method | Primary modules / symbols | Caches | Diagnostics | Explanation support |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Law Discovery / source-register intake | Resolve case sources | Case JSON, registry | Source identities | Case inputs / registry | configuration + deterministic | `file_input`, `source_bundle_intake` | registry files | intake errors | not yet recorded |
| Source fetch and snapshot | Obtain immutable text | Source URLs / cache keys | Snapshots | `source_snapshots.json`, fetch traces | deterministic | `sources.cache`, intake fetch | source cache | HTTP/parse failures | partially recorded (provenance fields) |
| Source parsing and structural hierarchy | Build fragment tree + capture legislative headings | Snapshot bytes | Fragments + parents + `number_label` / `structural_heading` | `source_fragments.json` | deterministic | `sources.adapters`, `sources.clml_heading`, `source_fragmentation`, `structural_headings` | derived parse cache | multi-provision Title diagnostics | not yet recorded (heading is source metadata, not a DecisionExplanation) |
| Manifestation and source-effect parsing | Record publisher manifestation + effect annotations | Snapshot / CLML | Manifestation fields, effect rows | snapshot fields, `source_legal_effects.json`, DecisionExplanations | deterministic | manifestation resolve, `source_legal_effects`, relevance capture | — | outstanding-effects status | **recorded** |
| Fragment selection | Choose extraction frontier | Fragments, required locators, focus terms | Selection decisions | extraction jobs | configuration + deterministic | `structural_extraction_frontier`, selection heuristics | — | overlap / skip reasons | **recorded** |
| Structural extraction frontier | Final selected set after coverage | Selection decisions | Selected fragment set | jobs + DecisionExplanations | deterministic | `prefer_required_children`, `prefer_required_ancestor` | — | unresolved overlap | **recorded** |
| Extraction request | Call extractor per selected fragment | Selected fragments, inherited heading contexts, prompts | Candidate rows / traces | `proposition_extraction_jobs.json` (`structural_heading_contexts`), LLM call traces | LLM (frontier/local) or heuristic | `extract`, `structural_headings`, LLM client | derived extraction cache (prompt v3+) | validation errors | partially recorded (`candidate_origin`); headings are labelled non-operative prompt context |
| Structured-list reconciliation | Compose terminals; suppress duplicates | Candidate rows | Retained compositions | propositions + explanations | deterministic | structured-list heuristics | — | rejected non-terminals | **recorded** |
| Proposition construction | Materialise retained propositions | Composed rows | Propositions | `propositions.json` | deterministic (after model proposal) | extract merge / runner | — | evidence match warnings | **recorded** (composition subjects) |
| Post-extraction classification | Assign legal-effect types | Propositions | `legal_effect_type` | propositions + explanations | deterministic | `classification.derive_legal_effect` | — | classify diagnostics | **recorded** |
| Completeness and scope | Assess self-containment; link scope | Propositions | Completeness / scope rows | completeness artifacts | deterministic | `proposition_completeness`, `scope_linking` | — | incomplete flags | not yet recorded |
| Legal rule groups | Group shared-fragment propositions | Propositions + fragments | Groups | `legal_rule_groups.json` | deterministic | `legal_rule_groups` | — | grouping diagnostics | **recorded** |
| Generic locator relationships | Mechanical cross-reference edges | Propositions | Locator edges | `proposition-relationships.json` | deterministic | `effective_law` relationship builders | — | unresolved locators | partially recorded |
| Typed legal relationships | Infer `exception_to` / `triggered_by` | Props + groups | Typed edges | `legal_rule_relationships.json` | deterministic | `legal_rule_relationships` | — | unresolved inference | **recorded** |
| Effective-law statements | Compose reviewer context | Props + relationships | Statements + context | `effective_law_statements.json` | deterministic | `effective_law` | — | composition warnings | **recorded** |
| Proposition Matcher candidates | Project matching queue | Effective-law statements | Candidates | `proposition_matcher_law_candidates.json` | deterministic | `proposition_matcher_law_candidates` | — | dedupe metadata | not yet recorded |
| Optional divergence | Compare aligned propositions | Proposition inventory | Assessments | divergence artifacts | hybrid (optional LLM) | compare / divergence | — | pairing gaps | not yet recorded |
| Workbench review | Human inspection and verdicts | Export bundle | Review decisions | review stores; Why panel | human | ops API + web Workbench | — | missing explanations on old runs | **recorded** (projection) |

Explanation support labels:

- **recorded** — DecisionExplanation emission exists for material decisions
- **partially recorded** — some provenance/fields exist without full decision records
- **not yet recorded** — no DecisionExplanation coverage yet

## What the language model does

For extraction:

1. Receives selected fragment operative text, optional inherited
   **structural legislative heading** context (labelled non-operative), and
   structured prompt/schema.
2. **Proposes** structured proposition rows (text fields, optional
   `provision_type`, evidence quotes, list-path hints). Headings must not become
   standalone propositions or evidence quotes.
3. May participate in optional divergence reasoning when enabled.

Heading data flow (source fidelity, not proposition creation):

```text
CLML structural heading (P1group/Title, container Title)
  → SourceFragment.structural_heading / number_label
  → inherited extraction-job structural_heading_contexts
  → Workbench structural display / Why panel
```

Inspect / regress this contract with `just inspect-structural-fixtures` and
`just check-structural-fixtures` (see
[structural-source-fixtures.md](structural-source-fixtures.md)). The inspector
reports hierarchy, unassigned cross-headings, and operative-text heading leaks
without changing Proposition Matcher or divergence behaviour.

Separately, the offline **proposition-fidelity** benchmark
(`just run-proposition-fidelity-benchmark` /
`just check-proposition-fidelity-benchmark`; see
[proposition-fidelity-benchmark.md](proposition-fidelity-benchmark.md)) asks
whether retained propositions preserve actors, actions, conditions, exceptions,
thresholds, evidence, and legal-effect classifications across several instrument
styles. Structural-source fidelity and proposition fidelity are different
contracts; neither replaces human legal review.

The model does **not** finalise the extraction frontier, legal-effect
classification, rule groups, typed relationships, or effective-law context.

## What deterministic code does afterwards

After extraction proposals:

1. Validates evidence quotes / schema.
2. Reconciles structured lists (compose terminals; suppress duplicates; preserve
   distinct same-path claims; reject non-terminals).
3. Retains propositions with opaque IDs.
4. Assigns legal-effect classification.
5. Builds legal rule groups.
6. Resolves generic locator relationships.
7. Infers typed relationships when cue + target are safe.
8. Expands effective-law required context (including typed-over-generic
   precedence).
9. Projects Proposition Matcher candidates.
10. Emits `decision_explanations.json` and export traces.

Deterministic post-processing improves structure and auditability. It does
**not** prove substantive legal correctness. Human review remains required.

## Roles at a glance

| Role | Examples |
| --- | --- |
| Configuration | Required locators, extraction mode, fallback policy |
| Deterministic | Selection coverage, composition, classification, groups, relationships, effective law |
| LLM | Frontier/local extraction proposals; optional divergence reasoning |
| Hybrid | Stages that accept model fields as inputs but decide deterministically |
| Human | Workbench review verdicts; guidance-ready promotion |

## Visual suite

See the [source-to-statement pipeline diagram](diagrams.md#source-to-statement-pipeline)
in the [diagram meeting script](diagrams.md). The diagram encodes configuration,
deterministic, LLM, and human stages with shape + label markers (not colour alone).

## Related documents

- [Concepts](concepts.md)
- [Diagrams](diagrams.md)
- [Heuristics](heuristics.md)
- [Artifacts and lineage](artifacts-and-lineage.md)
- [Article 49a walkthrough](article-49a-walkthrough.md)
- [Architecture pipeline overview](../architecture/pipeline-overview.md)
