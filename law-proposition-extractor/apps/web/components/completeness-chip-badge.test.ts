import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CompletenessChipBadge } from "./structured-proposition-ui";

describe("CompletenessChipBadge", () => {
  it("renders visible text for complete", () => {
    const html = renderToStaticMarkup(
      createElement(CompletenessChipBadge, { pipelineStatus: "complete" })
    );
    expect(html).toContain("Complete");
    expect(html).toMatch(/>[^<]*Complete[^<]*</);
  });

  it("renders visible text for context_dependent", () => {
    const html = renderToStaticMarkup(
      createElement(CompletenessChipBadge, { pipelineStatus: "context_dependent" })
    );
    expect(html).toContain("Needs context");
  });

  it("renders visible text for fragmentary", () => {
    const html = renderToStaticMarkup(
      createElement(CompletenessChipBadge, { pipelineStatus: "fragmentary" })
    );
    expect(html).toContain("Fragmentary");
  });

  it("renders visible text for not_assessed (noAssessment)", () => {
    const html = renderToStaticMarkup(
      createElement(CompletenessChipBadge, { noAssessment: true })
    );
    expect(html).toContain("Not assessed");
  });

  it("renders visible text for unknown (unrecognized status)", () => {
    const html = renderToStaticMarkup(
      createElement(CompletenessChipBadge, { pipelineStatus: "not-a-valid-status" })
    );
    expect(html).toContain("Unknown");
  });

  it("chip body is not whitespace-only", () => {
    const html = renderToStaticMarkup(
      createElement(CompletenessChipBadge, { pipelineStatus: "complete" })
    );
    const inner = html.replace(/<[^>]+>/g, "").trim();
    expect(inner.length).toBeGreaterThan(0);
  });
});
