import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  analyzeExportCompositionTrace,
  buildExportCompositionTraceReport,
  writeExportCompositionTraceReport,
} from "@/lib/export-composition-trace-io";
import { enrichEffectiveLawStatements } from "@/lib/export-composition-trace";

describe("export-composition-trace", () => {
  it("builds export composition trace report from slurry export", () => {
    const exportDir = process.env.EXPORT_COMPOSITION_TRACE_EXPORT_DIR;
    if (!exportDir) {
      return;
    }

    const analysis = analyzeExportCompositionTrace(exportDir);
    expect(analysis.statementsWithCompositionTrace).toBeGreaterThan(0);

    const report = buildExportCompositionTraceReport(analysis);
    expect(report).toContain("# Export composition trace report");
    expect(report).toContain("should_inline");

    const outputPath = process.env.EXPORT_COMPOSITION_TRACE_REPORT_PATH;
    if (outputPath) {
      writeExportCompositionTraceReport(outputPath, report);
    }
  });

  it("enriches all statements in a bundle", () => {
    const exportDir = process.env.EXPORT_COMPOSITION_TRACE_EXPORT_DIR;
    if (!exportDir) {
      return;
    }

    const root = resolve(exportDir);
    const input = {
      propositions: JSON.parse(readFileSync(resolve(root, "propositions.json"), "utf-8")),
      source_fragments: JSON.parse(readFileSync(resolve(root, "source_fragments.json"), "utf-8")),
      source_records: JSON.parse(readFileSync(resolve(root, "sources.json"), "utf-8")),
      effective_law_statements: JSON.parse(
        readFileSync(resolve(root, "effective_law_statements.json"), "utf-8"),
      ),
    };
    const enriched = enrichEffectiveLawStatements(input);
    expect(enriched.statements.every((row) => (row.composition_trace?.length ?? 0) > 0)).toBe(
      true,
    );
  });
});
