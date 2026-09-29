import { readFileSync, writeFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { enrichEffectiveLawStatements } from "@/lib/export-composition-trace";

describe("export-composition-trace-enrich", () => {
  it("enriches statements from ENRICH_INPUT_PATH when set by pipeline bridge", () => {
    const inputPath = process.env.ENRICH_INPUT_PATH;
    const outputPath = process.env.ENRICH_OUTPUT_PATH;
    if (!inputPath || !outputPath) {
      return;
    }

    const input = JSON.parse(readFileSync(inputPath, "utf-8"));
    const enriched = enrichEffectiveLawStatements(input);
    writeFileSync(outputPath, JSON.stringify(enriched), "utf-8");
  });

  it("adds composition_trace to a minimal statement", () => {
    const payload = {
      propositions: [
        {
          id: "prop-core",
          proposition_text: "An occupier must not cause pollution.",
          fragment_locator: "regulation 2(1)",
          source_fragment_id: "frag-1",
        },
      ],
      source_fragments: [{ id: "frag-1", fragment_text: "An occupier must not cause pollution." }],
      source_records: [],
      effective_law_statements: {
        schema_version: "1",
        run_id: "run-test",
        statements: [
          {
            id: "lawstmt:test",
            statement_text: "An occupier must not cause pollution.",
            presentation_role: "guidance_matching_candidate",
            standalone_status: "standalone",
            confidence: "high",
            source_proposition_ids: ["prop-core"],
            supporting_proposition_ids: [],
            required_context: [],
            connector_context: [],
            warnings: [],
          },
        ],
      },
    };

    const enriched = enrichEffectiveLawStatements(payload);
    const statement = enriched.statements[0]!;
    expect(statement.composition_trace?.length).toBeGreaterThan(0);
    expect(statement.composition_trace?.[0]?.role).toBe("core_proposition");
    expect(statement.composition_trace?.[0]?.incorporation).toBeDefined();
  });
});
