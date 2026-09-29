import { describe, expect, it } from "vitest";

import {
  analyzeReviewabilityBlockers,
  buildReviewabilityBlockersReport,
  writeReviewabilityBlockersReport,
} from "@/lib/analyze-reviewability-blockers";

describe("analyze-reviewability-blockers", () => {
  it("builds a non-empty reviewability blockers report", () => {
    const exportDir = process.env.REVIEWABILITY_BLOCKERS_EXPORT_DIR;
    if (!exportDir) {
      return;
    }

    const analysis = analyzeReviewabilityBlockers(exportDir);
    expect(analysis.corruptedEvidenceTotal).toBeGreaterThan(0);
    expect(analysis.difficultStatementCount).toBeGreaterThan(0);

    const report = buildReviewabilityBlockersReport(analysis);
    expect(report).toContain("# Reviewability blockers report");
    expect(report).toContain("## 2. Top 50 corrupted evidence examples");

    const outputPath = process.env.REVIEWABILITY_BLOCKERS_REPORT_PATH;
    if (outputPath) {
      writeReviewabilityBlockersReport(outputPath, report);
    }
  });
});
