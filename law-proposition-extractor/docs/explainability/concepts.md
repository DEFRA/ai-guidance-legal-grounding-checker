# Law Proposition Extractor concepts

Plain-language conceptual model for Law Proposition Extractor’s legal units. Technical names appear
after the plain definition. Article 49a is used only as a worked illustration;
the concepts apply across instruments.

For each concept: **definition**, **why Law Proposition Extractor needs it**, **what it is not**,
**produced by**, **stored in**, **used by**, **example**.

---

## Source-register entry

**Definition:** A tracked legal source reference used to drive repeatable runs
(identity, URLs, jurisdiction hints).

**Why:** Operators need a durable list of instruments without re-typing fetch
details each run.

**Not:** The fetched text itself; not a legal conclusion.

**Produced by:** Source-registry / Law Discovery intake workflows.

**Stored in:** Source registry payloads / case inputs.

**Used by:** Case runs that resolve which sources to fetch.

**Example:** A register row for EUR 2009/1224 pointing at legislation.gov.uk.

---

## Source record

**Definition:** Run-level identity and metadata for one legal instrument in a
bundle (`sources.json`).

**Why:** Propositions and snapshots must hang off a stable source identity.

**Not:** The full XML/HTML body.

**Produced by:** Source intake.

**Stored in:** `sources.json`.

**Used by:** Workbench source inspectors, all downstream artifacts.

**Example:** `src-eur-2009-1224` for the Control Regulation fixture.

---

## Source snapshot

**Definition:** An immutable consumed text instance with content hash and
retrieval provenance.

**Why:** Reviewers must know exactly which bytes Law Proposition Extractor analysed.

**Not:** Automatically a legal as-of date; not proof that amendments were
applied by Law Proposition Extractor.

**Produced by:** Fetch/cache intake.

**Stored in:** `source_snapshots.json`.

**Used by:** Fragments, propositions, manifestation provenance UI.

**Example:** Snapshot hash for the offline Article 49a XML slice.

---

## Source manifestation

**Definition:** Authority-supplied version semantics on a snapshot (for example
`revised`), with optional as-of / revision evidence fields.

**Why:** Operators need to see how the publisher labelled the text Law Proposition Extractor
consumed.

**Not:** Independent amendment application by Law Proposition Extractor; not outstanding-effect
clearance.

**Produced by:** Parser/intake manifestation extraction.

**Stored in:** Snapshot manifestation fields / evidence.

**Used by:** Source-version provenance views.

**Example:** `DocumentStatus=revised` on legislation.gov.uk CLML.

---

## Source fragment

**Definition:** A structural subdivision of a snapshot (title, article,
paragraph, subparagraph, item, …) with a locator.

**Why:** Extraction and relationships need addressable units smaller than a
whole instrument.

**Not:** A proposition (a fragment may yield zero, one, or many propositions).

**Produced by:** Structural parse / fragmentation.

**Stored in:** `source_fragments.json`.

**Used by:** Selection, extraction jobs, grouping, relationships.

**Example:** `article:49a:paragraph:2`.

---

## Structural hierarchy

**Definition:** Parent/child tree among fragments (title → article → paragraph
→ …).

**Why:** Coverage rules and relative references depend on structure.

**Not:** A legal hierarchy of obligations vs exceptions by itself.

**Produced by:** Structural parse.

**Stored in:** Fragment parent links.

**Used by:** Selection preference rules, locator resolution.

**Example:** `title:iv` → `article:49a` → paragraphs 1–3.

---

## Legislative heading

**Definition:** Source-provided structural text naming or describing the subject
of a provision or container (for example a CLML `P1group/Title` or a container
descriptive `Title`). Stored as first-class fragment metadata
(`structural_heading`), not as operative `fragment_text`.

**Why:** Reviewers and extraction need the official subject label without
turning it into a proposition or splicing it into evidence quotes.

**Not:** The instrument title; not a proposition label; not a locator display
label; not a multi-provision cross-heading assigned to an arbitrary article;
not commentary or footnote bodies.

**Produced by:** CLML structural parse (safe single-owner group Title; container
Number + descriptive Title kept separate).

**Stored in:** `source_fragments.json` on the owning fragment only; descendants
resolve via parent links. Also projected into
`proposition_extraction_jobs.json` as `structural_heading_contexts`.

**Used by:** Extraction prompt structural context (non-operative), Workbench
article chrome / Why panel, source fidelity audits.

**Example:** Article 49a — “Separate stowage of catches below the minimum
conservation reference sizes”.

**Contract:** Offline multi-instrument coverage lives in
`tests/fixtures/structural_source/` and
[structural-source-fixtures.md](structural-source-fixtures.md). Heading context
may improve retrieval and reviewer orientation, but a heading-only match is not
substantive evidence that guidance matches a legal proposition. Headings are not
classified for materiality/completeness here.

---

## Structural extraction frontier

**Definition:** The set of fragments actually selected for extraction after
coverage and skip rules.

**Why:** Avoids double-extracting parents and covered descendants.

**Not:** The frontier *model* (LLM mode); not divergence “frontier reasoning”.

**Produced by:** Selection heuristics.

**Stored in:** Extraction jobs + selection DecisionExplanations.

**Used by:** Extraction requests.

**Example:** Paragraphs 1–3 selected; Article 49a parent and paragraph 2(a)
suppressed.

---

## Extraction candidate

**Definition:** A model- or heuristic-proposed structured row before retention.

**Why:** Audit suppressed alternatives without promoting them into law outputs.

**Not:** A retained proposition.

**Produced by:** Extraction (often LLM).

**Stored in:** Traces / DecisionExplanations with `extractcand:` subjects.

**Used by:** Composition and deduplication decisions.

**Example:** A stem-only row rejected because a terminal composition covers it.

---

## Proposition

**Definition:** An atomic legal statement retained from source text, with
evidence and classification fields.

**Why:** Comparable review unit for inventory, relationships, and divergence.

**Not:** A complete statement of all applicable law; not an effective-law
statement.

**Produced by:** Extraction + deterministic reconciliation.

**Stored in:** `propositions.json`.

**Used by:** Groups, relationships, effective law, Proposition Matcher, Workbench.

**Example:** P1 — place sub-MCRS catches so they are identifiable.

---

## Structured-list path

**Definition:** A deterministic path label for a terminal in a compound list
(for example `2-a-ii`).

**Why:** Compound paragraphs must become multiple propositions without losing
branch identity.

**Not:** A locator by itself (though related).

**Produced by:** Structured-list reconciliation.

**Stored in:** Extraction debug metadata / explanations.

**Used by:** Deduplication, walkthroughs, review UI.

**Example:** E2 path `2-a-ii`.

---

## Proposition completeness

**Definition:** Assessment of whether a proposition is self-contained enough for
comparison/review.

**Why:** Incomplete units confuse divergence and guidance matching.

**Not:** Proof that all related law has been attached.

**Produced by:** Completeness assessment stage.

**Stored in:** Completeness artifacts / debug fields.

**Used by:** Quality gates, review triage.

**Example:** A proposition marked complete when evidence quote resolves.

---

## Legal-effect classification

**Definition:** Deterministic assignment of `legal_effect_type` (obligation,
prohibition, derogation, …).

**Why:** Downstream relationships and review filters need effect type.

**Not:** A full doctrinal classification by a lawyer.

**Produced by:** `classification.derive_legal_effect`.

**Stored in:** Proposition fields + DecisionExplanations.

**Used by:** Relationship cues, Workbench filters.

**Example:** E1–E3 classified as derogation.

---

## Legal rule group

**Definition:** Two or more retained propositions sharing one reliable source
fragment / canonical locator.

**Why:** Exceptions and triggers often target a paragraph-set, not one sentence.

**Not:** A duplicate group; not a UI folder.

**Produced by:** `grouping.create_shared_fragment_rule_group`.

**Stored in:** `legal_rule_groups.json`.

**Used by:** Typed relationships, effective-law expansion.

**Example:** Paragraph-1 group = {P1, P2}.

---

## Generic locator relationship

**Definition:** Mechanical proposition↔locator edge (cross-reference resolution)
without a typed legal role.

**Why:** Ordinary references must remain visible even when not exceptions.

**Not:** A typed `exception_to` / `triggered_by` relationship.

**Produced by:** Locator relationship construction.

**Stored in:** `proposition-relationships.json`.

**Used by:** Effective-law generic context (may be suppressed when typed context
already covers the same connection).

**Example:** A plain “paragraph 1” reference edge.

---

## Typed legal relationship

**Definition:** High-confidence legal connection such as `exception_to` or
`triggered_by`, usually targeting a legal rule group.

**Why:** Reviewers need exception/trigger structure, not only text similarity.

**Not:** Every cross-reference; not Article 14 merely because it is mentioned.

**Produced by:** Relationship inference heuristics.

**Stored in:** `legal_rule_relationships.json`.

**Used by:** Effective-law typed context, Workbench Why panel.

**Example:** E2 `exception_to` paragraph-1 group.

---

## Effective-law statement

**Definition:** Guidance-facing presentation of one or more propositions with
required context roles.

**Why:** Reviewers need “this rule + its exceptions/triggers” without manually
joining artifacts.

**Not:** A raw proposition; not proof of current consolidated law.

**Produced by:** Effective-law composition.

**Stored in:** `effective_law_statements.json`.

**Used by:** Law view, Proposition Matcher candidates, Why panel.

**Example:** P1 statement listing applicable exceptions E1–E3.

---

## Required context

**Definition:** Attached context rows on an effective-law statement
(`applicable_exception`, `exception_target`, `trigger_condition`, ordinary
references, …).

**Why:** Makes group-targeted relationships concrete per statement.

**Not:** Automatically every cited instrument.

**Produced by:** Effective-law expansion heuristics.

**Stored in:** Statement `required_context`.

**Used by:** Workbench typed-context sections.

**Example:** P3’s `trigger_condition` rows for E1–E3.

---

## Source legal effect

**Definition:** Amendment/effect annotation **reported in the consumed XML**,
linked to affected locators where possible.

**Why:** Surface publisher-reported effects beside the snapshot.

**Not:** Proof Law Proposition Extractor applied the amendment or consumed the affecting
instrument independently.

**Produced by:** Source-effect parsing + consumption reconciliation.

**Stored in:** `source_legal_effects.json`.

**Used by:** Workbench source-effect cards.

**Example:** Commentary keys retained in the Article 49a fixture.

---

## Proposition Matcher law candidate

**Definition:** Narrow matching-queue row derived from effective-law statements
for guidance claim matching.

**Why:** Proposition Matcher should not match against raw uncontextualised propositions.

**Not:** A Law Proposition Extractor legal approval; not the full law layer.

**Produced by:** Proposition Matcher candidate projection.

**Stored in:** `proposition_matcher_law_candidates.json`.

**Used by:** Proposition Matcher / guidance handoff.

**Example:** Six Article 49a candidates carrying typed context.

---

## Divergence assessment

**Definition:** Optional comparison outcome between aligned propositions across
jurisdictions/modes.

**Why:** Supports divergence analysis without replacing single-jurisdiction
inventory.

**Not:** Required for every Law Proposition Extractor run.

**Produced by:** Divergence classification (optional LLM).

**Stored in:** Divergence artifacts / assessments.

**Used by:** Divergence Workbench views.

**Example:** Pairing two obligations that differ only in territorial wording.

---

## Review verdict

**Definition:** Human governance decision on a run artifact (accept / reject /
needs work, etc.).

**Why:** Legal outputs stay review datasets until promoted.

**Not:** An automatic model score.

**Produced by:** Human review workflows.

**Stored in:** Review-decision stores / traces.

**Used by:** Guidance-ready promotion governance.

**Example:** Accepting a proposition after checking evidence quotes.

---

## Heuristic

**Definition:** A named, versioned rule in the code-declared registry describing
a material Law Proposition Extractor decision.

**Why:** Stable rule IDs for explanations, tests, and audits.

**Not:** Free-form prompt text; not chain-of-thought.

**Produced by:** Developers (registry declarations).

**Stored in:** `law_proposition_extractor_pipeline.heuristics.registry`.

**Used by:** DecisionExplanations, handbook catalogue, ops heuristics API.

**Example:** `selection.prefer_required_ancestor` version `1`.

---

## Decision explanation

**Definition:** Portable record of a processing decision (subject, rule,
outcome, evidence).

**Why:** Lets lawyers and auditors inspect *what Law Proposition Extractor recorded*, not a
reconstructed story.

**Not:** Model chain-of-thought; not legal approval.

**Produced by:** Emission sites at decision time.

**Stored in:** `decision_explanations.json`.

**Used by:** Workbench Why panel, audits.

**Example:** Suppression of paragraph 2(a) with ancestor coverage evidence;
revised manifestation classification with basis `source_metadata`; Article 49a
source-effect inheritance onto paragraph statements.

---

## Diagnostic

**Definition:** Structured warning or unresolved condition accompanying a
decision or artifact.

**Why:** Surface uncertainty without inventing false certainty.

**Not:** A silent failure.

**Produced by:** Heuristics / export transforms.

**Stored in:** Decision diagnostics fields and artifact diagnostic lists.

**Used by:** Quality gates, Why panel technical details.

**Example:** Unresolved typed-relationship inference diagnostic.

---

## Required distinctions

### Snapshot vs manifestation vs legal as-of date

A **snapshot** is the bytes Law Proposition Extractor consumed. A **manifestation** is how the
publisher labelled that text (for example revised). A **legal as-of date** is a
legal question about applicable law at a date — not automatically equal to
`retrieved_at` or a cache `version_id`.

### Fragment vs proposition

A **fragment** is structural source text. A **proposition** is a retained legal
statement derived from one or more extraction decisions over fragments.

### Proposition vs effective-law statement

A **proposition** is the atomic unit. An **effective-law statement** presents
that unit (or a small set) with required context for review/matching.

### Legal rule group vs duplicate group

A **legal rule group** joins propositions that share a structural fragment for
legal targeting. A **duplicate group** flags near-identical candidates for
matching hygiene; it is not a legal target.

### Generic locator relationship vs typed legal relationship

**Generic** edges resolve references. **Typed** relationships assert a legal
role (`exception_to`, `triggered_by`) only with supported cues and safe targets.

### Source legal effect vs independently applied amendment

A **source legal effect** is publisher-reported annotation. **Independent
application** would mean Law Proposition Extractor itself reconstructed/applied the amending
instrument — which source-effect rows do not prove.

### Model output vs deterministic retained proposition

The model may **propose** rows. Deterministic code validates evidence,
reconciles lists, classifies, groups, links, and retains propositions.

### Complete proposition vs complete statement of all applicable law

**Completeness** of a proposition means the unit is self-contained enough for
pipeline purposes. It is **not** a claim that Law Proposition Extractor assembled every applicable
exception, amendment, and related instrument for the legal question.
