# Proposition-fidelity benchmark fixtures

Offline multi-instrument matrix for whether Law Proposition Extractor converts structurally parsed
legislation into faithful, atomic, context-aware legal propositions.

## Commands

```bash
just run-proposition-fidelity-benchmark
just check-proposition-fidelity-benchmark
just test-proposition-fidelity
```

## Layout

- `manifest.json` — case inventory + provenance
- `baseline.json` — committed baseline for regression checks
- `cases/<case_id>/gold.json` — human semantic gold contract
- `cases/<case_id>/response.json` — offline extraction response (dry path)
- `cases/<case_id>/fragment_text.txt` — optional operative-text override

Article 49a uses the existing acceptance pipeline and frontier responses under
`tests/fixtures/article_49a_legal_structure/`.

## Distinctions

| Contract | Question |
| --- | --- |
| Structural-source fidelity | Hierarchy / headings / operative boundaries |
| Proposition fidelity | Operative legal claims (this matrix) |
| Legal review | Acceptability for intended legal use |

### Action fidelity

Evaluated as legal-action invariants (predicate, polarity, legal effect,
material objects)—not brittle modal phrases alone. Optional gold field
`action_expectation` enables structured comparison; simple `required_action`
rows keep the legacy substring matcher.

Article 49a example: “shall not be mixed” and “must not mix” may be the same
prohibition; `need not` / `should not` are not automatically equivalent.

No network or LLM calls. Law Proposition Extractor-only — Proposition Matcher and divergence are out of scope.
