# Artifacts and lineage

How Law Proposition Extractor data moves through persisted artifacts, and how IDs join stages.

## Artifact map (explainability lens)

| Artifact | Purpose | Primary producer | Primary inputs | Principal consumers | Optional / required | Explainability role |
| --- | --- | --- | --- | --- | --- | --- |
| Source registry / case input | Declares sources and run configuration | Operator / Law Discovery | Category / register | Runner intake | required for registry-driven runs | Configuration provenance |
| `sources.json` | Source records | Intake + export | Registry / fetch | Workbench, all downstream | required | Source identity |
| `source_snapshots.json` | Immutable text + manifestation fields | Intake + export | Fetch bytes | Fragments, provenance UI | required | Snapshot / manifestation evidence |
| `source_fragments.json` | Structural fragments (+ optional `number_label` / `structural_heading`) | Fragmentation + export | Snapshots | Selection, extraction, groups, structural-source inspector | required | Locator tree + legislative heading metadata |
| Source fetch / parse traces | Stage diagnostics | Runner / exporter | Intake | Ops trace UI | optional | Operational audit |
| `proposition_extraction_jobs.json` | Per-fragment selection/extraction outcomes | Runner | Frontier decisions | Repair, frontier audit | evolving / usual | Selection outcomes |
| Extraction call traces (`extraction_llm_call_traces.json`) | LLM call metadata | Extraction | Model calls | Quality / repair | optional | Model-call references (not CoT) |
| `propositions.json` | Retained propositions | Runner | Extraction + reconciliation | Groups, relationships, UI | required | Subjects of many decisions |
| Completeness assessments | Self-containment rows | Completeness stage | Propositions | Quality gates | evolving | Partial |
| `proposition-relationships.json` | Generic locator edges | Export effective-law path | Propositions | Effective law, Proposition Matcher | evolving | Generic context |
| `legal_rule_groups.json` | Shared-fragment groups | `legal_rule_groups` | Propositions + fragments | Typed relationships | optional on old exports | Group subjects |
| `legal_rule_relationships.json` | Typed `exception_to` / `triggered_by` | `legal_rule_relationships` | Props + groups | Effective law, Why panel | optional on old exports | Relationship subjects |
| `effective_law_statements.json` | Statements + required context | `effective_law` | Props + relationships | Law view, Proposition Matcher, Why panel | usual | Statement subjects |
| `proposition_matcher_law_candidates.json` | Guidance matching queue | `proposition_matcher_law_candidates` | Effective-law statements | Proposition Matcher | usual | Downstream projection |
| `source_legal_effects.json` | Publisher-reported effects | Source-effect parse + reconcile | Snapshot XML | Workbench source-effect cards | optional on old exports | Provenance boundary |
| `decision_explanations.json` | DecisionExplanation records | Heuristic emitters via runner/export | Decision facts | Workbench Why panel, audits | optional on old exports | **Primary explainability artifact** |
| Review decisions | Human verdicts | Review workflows | Artifacts | Governance | append-only store | Human role |
| Divergence artifacts | Comparison assessments | Divergence stage | Proposition pairs | Divergence UI | optional | Optional LLM stage |
| `MODEL.md` | Human-readable run metadata | `run_model_md` | Run settings / metrics | Operators | usual | Run narrative, not CoT |

Use actual export filenames from this table. Older historical names should not be
silently preserved when superseded.

## Lineage chains

### Legal structure chain

```text
SourceSnapshot
  → SourceFragment
    → Proposition
      → LegalRuleGroup
        → LegalRuleRelationship
          → EffectiveLawStatement
```

### Explanation chain

```text
FragmentSelectionDecision
  → DecisionExplanation
    → Workbench Why panel
```

Composition, classification, grouping, relationship, effective-law, provenance
(manifestation / as-of), and source-effect (parse / relevance / consumption)
decisions follow the same pattern: decision site → `decision_explanations.json`
→ panel. Preferred stage order for consumers:
`provenance` → `selection` → `extraction` → `classification` → `grouping` →
`relationship` → `effective_law` → `source_effect`.

## How IDs join artifacts

| ID prefix / field | Joins |
| --- | --- |
| `source_record_id` | sources ↔ snapshots ↔ fragments ↔ propositions |
| `source_snapshot_id` | snapshot instance used by fragments/props |
| `source_fragment_id` / `fragment_locator` | fragment ↔ extraction job ↔ proposition |
| proposition `id` (`prop:…`) | propositions ↔ groups ↔ relationships ↔ statements ↔ explanations |
| `rulegrp:…` | legal rule groups ↔ relationship targets ↔ context inheritance |
| `legalrel:…` | relationships ↔ effective-law context `relationship_id` |
| `lawstmt:…` | effective-law statements ↔ Why panel subjects |
| `decision:…` | DecisionExplanation rows |
| `extractcand:…` | suppressed extraction candidates in explanations |
| `bcand:…` | Proposition Matcher candidates |

Workbench indexes DecisionExplanations by subject and stage; it does not rerun
heuristics to reconstruct IDs.

## Provenance boundaries

- A consumed **revised** source does **not** prove Law Proposition Extractor independently applied
  every amendment.
- A **source-effect annotation** does **not** prove the affecting instrument was
  independently consumed.
- A **retrieval timestamp** is **not** automatically a legal as-of date.
- `version_id` / cache keys are run/storage keys, not manifestation law dates.
- Decision explanations describe **process**, not legal approval.

## Related documents

- [Artifact reference](../reference/artifacts.md)
- [Effective-law layers](../architecture/effective-law-layers.md)
- [Pipeline](pipeline.md)
- [Article 49a walkthrough](article-49a-walkthrough.md)
