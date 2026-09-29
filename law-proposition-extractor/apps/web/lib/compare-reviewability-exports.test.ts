import { describe, expect, it } from "vitest";

import {
  buildReviewabilityReport,
  writeReviewabilityReport,
} from "@/lib/compare-reviewability-exports";

describe("compare-reviewability-exports", () => {
  it("builds a non-empty reviewability comparison report", () => {
    const beforeDir = process.env.REVIEWABILITY_BEFORE_DIR;
    const afterDir = process.env.REVIEWABILITY_AFTER_DIR;
    if (!beforeDir || !afterDir) {
      return;
    }

    const report = buildReviewabilityReport({
      beforeDir,
      afterDir,
      beforeEffectiveLawPath: process.env.REVIEWABILITY_BEFORE_EFFECTIVE,
      beforeLabel: "Previous export (279-fragment intake, json-repaired extraction)",
      afterLabel: "Regenerated export (727-fragment intake, frontier extraction)",
    });

    expect(report).toContain("# Reviewability improvement report");
    expect(report).toContain("## 1. Statement counts");

    const outputPath = process.env.REVIEWABILITY_REPORT_PATH;
    if (outputPath) {
      writeReviewabilityReport(outputPath, report);
    }
  });
});
