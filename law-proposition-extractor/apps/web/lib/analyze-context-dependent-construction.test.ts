import { describe, expect, it } from "vitest";

import {
  analyzeContextDependentConstruction,
  buildContextDependentConstructionReport,
  writeContextDependentConstructionReport,
} from "@/lib/analyze-context-dependent-construction";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";

describe("analyze-context-dependent-construction", () => {
  it("classifies material context gaps deterministically", () => {
    const exportDir = process.env.CONTEXT_CONSTRUCTION_FIXTURE_DIR;
    if (!exportDir) {
      const statement: LawStatementRow = {
        id: "stmt-ctx",
        statement_text: "The occupier must not spread slurry except as provided in regulation 14.",
        presentation_role: "guidance_matching_candidate",
        standalone_status: "context_dependent",
        confidence: "medium",
        source_proposition_ids: ["prop-core"],
        required_context: [
          {
            kind: "incorporated_rule",
            locator: "regulation 14",
            resolution_status: "resolved",
            proposition_ids: ["prop-ctx"],
          },
        ],
      };
      const core: PropositionRow = {
        id: "prop-core",
        proposition_text:
          "The occupier must not spread slurry except as provided in regulation 14.",
        legal_effect_type: "prohibition",
      };
      const context: PropositionRow = {
        id: "prop-ctx",
        proposition_text:
          "Regulation 14 sets the maximum nitrogen content for organic manure calculations.",
        legal_effect_type: "obligation",
      };

      expect(core.proposition_text).toBe(statement.statement_text);
      expect(context.legal_effect_type).not.toBe(core.legal_effect_type);
      return;
    }

    const analysis = analyzeContextDependentConstruction(exportDir);
    expect(analysis.contextDependentCount).toBeGreaterThan(0);
    expect(analysis.traceBlockedCount + analysis.traceReviewableCount).toBe(
      analysis.contextDependentCount,
    );
  });

  it("builds a non-empty context-dependent construction report from the slurry export", () => {
    const exportDir = process.env.CONTEXT_CONSTRUCTION_EXPORT_DIR;
    if (!exportDir) {
      return;
    }

    const analysis = analyzeContextDependentConstruction(exportDir);
    expect(analysis.contextDependentCount).toBeGreaterThan(0);
    expect(analysis.samples.length).toBeGreaterThan(0);

    const report = buildContextDependentConstructionReport(analysis);
    expect(report).toContain("# Context-dependent construction report");
    expect(report).toContain("## 4. Sampled statements");
    expect(report).toContain("inline context selectively");

    const outputPath = process.env.CONTEXT_CONSTRUCTION_REPORT_PATH;
    if (outputPath) {
      writeContextDependentConstructionReport(outputPath, report);
    }
  });
});
