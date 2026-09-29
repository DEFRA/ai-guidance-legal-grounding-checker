import { describe, expect, it } from "vitest";

import {
  buildContextClosureImpactReport,
  writeContextClosureImpactReport,
} from "@/lib/compare-context-closure-impact";

describe("compare-context-closure-impact", () => {
  it("builds a non-empty post context-closure impact report", () => {
    const exportDir = process.env.CONTEXT_CLOSURE_IMPACT_EXPORT_DIR;
    const beforeEffective = process.env.CONTEXT_CLOSURE_IMPACT_BEFORE_EFFECTIVE;
    const afterEffective = process.env.CONTEXT_CLOSURE_IMPACT_AFTER_EFFECTIVE;
    if (!exportDir || !beforeEffective || !afterEffective) {
      return;
    }

    const report = buildContextClosureImpactReport({
      exportDir,
      beforeEffectiveLawPath: beforeEffective,
      afterEffectiveLawPath: afterEffective,
    });

    expect(report).toContain("# Post context-closure impact report");
    expect(report).toContain("## 1. Context closure");
    expect(report).toContain("## 2. Composition opacity");

    const outputPath = process.env.CONTEXT_CLOSURE_IMPACT_REPORT_PATH;
    if (outputPath) {
      writeContextClosureImpactReport(outputPath, report);
    }
  });
});
