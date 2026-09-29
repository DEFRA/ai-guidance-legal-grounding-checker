import { describe, expect, it } from "vitest";

import {
  analyzeCompositionTraces,
  buildCompositionTraceReport,
  writeCompositionTraceReport,
} from "@/lib/analyze-composition-traces-io";
import { buildCompositionTrace } from "@/lib/analyze-composition-traces";
import {
  buildStatementRecipe,
  type CompositionBuildContext,
  type SourceFragmentRow,
} from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow, SourceRow } from "@/lib/law-statements-index";

describe("analyze-composition-traces", () => {
  it("builds deterministic traces from recipe rows and proposition refs", () => {
    const statement: LawStatementRow = {
      id: "stmt-1",
      statement_text: "A must do X. Unless Y applies.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "context_dependent",
      confidence: "high",
      source_proposition_ids: ["prop-core"],
      supporting_proposition_ids: ["prop-support"],
      required_context: [
        {
          locator: "reg 2(1)",
          resolution_status: "resolved",
          proposition_ids: ["prop-ctx"],
        },
      ],
      connector_context: [],
      warnings: [],
    };
    const context: CompositionBuildContext = {
      propositionById: new Map<string, PropositionRow>([
        [
          "prop-core",
          {
            id: "prop-core",
            proposition_text: "A must do X",
            fragment_locator: "reg 4",
            source_fragment_id: "frag-1",
          },
        ],
        [
          "prop-support",
          {
            id: "prop-support",
            proposition_text: "Unless Y applies",
            fragment_locator: "reg 5",
            source_fragment_id: "frag-2",
          },
        ],
        [
          "prop-ctx",
          {
            id: "prop-ctx",
            proposition_text: "Y means ...",
            fragment_locator: "reg 2(1)",
            source_fragment_id: "frag-3",
          },
        ],
      ]),
      sourceById: new Map<string, SourceRow>(),
      fragmentById: new Map<string, SourceFragmentRow>([
        ["frag-1", { id: "frag-1", fragment_text: "A must do X" }],
        ["frag-2", { id: "frag-2", fragment_text: "Unless Y applies" }],
        ["frag-3", { id: "frag-3", fragment_text: "Y means ..." }],
      ]),
    };

    const recipe = buildStatementRecipe(statement, context);
    expect(recipe.length).toBe(3);

    const trace = buildCompositionTrace(statement, context);
    expect(trace.length).toBeGreaterThan(1);
    expect(trace.some((fragment) => fragment.proposition_ids.includes("prop-core"))).toBe(true);
    expect(trace.some((fragment) => fragment.role !== "unknown")).toBe(true);
  });

  it("builds a non-empty composition trace report from the slurry export", () => {
    const exportDir = process.env.COMPOSITION_TRACE_EXPORT_DIR;
    if (!exportDir) {
      return;
    }

    const analysis = analyzeCompositionTraces(exportDir);
    expect(analysis.opaqueStatementCount).toBeGreaterThan(0);
    expect(analysis.samples.length).toBeGreaterThan(0);

    const report = buildCompositionTraceReport(analysis);
    expect(report).toContain("# Composition trace report");
    expect(report).toContain("## 3. Sampled statements");
    expect(report).toContain("composition_trace");

    const outputPath = process.env.COMPOSITION_TRACE_REPORT_PATH;
    if (outputPath) {
      writeCompositionTraceReport(outputPath, report);
    }
  });
});
