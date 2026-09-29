import { describe, expect, it } from "vitest";

import {
  analyzeUnresolvedLocatorClosure,
  buildUnresolvedLocatorClosureReport,
  writeUnresolvedLocatorClosureReport,
} from "@/lib/analyze-unresolved-locator-closure";

describe("analyze-unresolved-locator-closure", () => {
  it("builds a non-empty unresolved locator closure report from the slurry export", () => {
    const exportDir = process.env.UNRESOLVED_LOCATOR_EXPORT_DIR;
    if (!exportDir) {
      return;
    }

    const analysis = analyzeUnresolvedLocatorClosure(exportDir);
    expect(analysis.unresolvedLocatorTotal).toBeGreaterThan(0);
    expect(analysis.topLocators.length).toBeGreaterThan(0);

    const report = buildUnresolvedLocatorClosureReport(analysis);
    expect(report).toContain("# Unresolved locator closure report");
    expect(report).toContain("## 3. Top 30 unresolved locator strings");
    expect(report).toContain("## 7. Recommendation");

    const outputPath = process.env.UNRESOLVED_LOCATOR_REPORT_PATH;
    if (outputPath) {
      writeUnresolvedLocatorClosureReport(outputPath, report);
    }
  });
});
