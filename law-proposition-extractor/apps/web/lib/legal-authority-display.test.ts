import { describe, expect, it } from "vitest";

import type { PropositionRow } from "@/lib/law-statements-index";
import type { InlineLegalReference } from "@/lib/statement-inline-references";

import {
  authorityHeadlineSummary,
  authorityWhyItMatters,
  supportingPropositionCountLabel,
} from "./legal-authority-display";

const propositionById = new Map<string, PropositionRow>([
  [
    "prop:schedule",
    {
      id: "prop:schedule",
      proposition_text: "Defines the derogation conditions for record keeping.",
    },
  ],
  [
    "prop:reg36",
    {
      id: "prop:reg36",
      proposition_text: "Requires calculations and records to be retained for five years.",
    },
  ],
  [
    "prop:para10",
    {
      id: "prop:para10",
      proposition_text: "Defines crops with high nitrogen demand.",
    },
  ],
]);

function buildReference(overrides: Partial<InlineLegalReference>): InlineLegalReference {
  return {
    id: "statement::Schedule 3::10",
    sourceId: "statement",
    locator: "Schedule 3",
    label: "Schedule 3",
    start: 10,
    end: 20,
    accent: "resolved_container",
    status: "resolved_container",
    materialRole: "constrains_statement",
    incorporationLabel: "Should split into multiple statements",
    whyThisMatters: "Constrains statement",
    summary: "This expands to 5 propositions / 2 source fragments",
    propositionIds: ["prop:schedule"],
    sourceFragmentIds: ["frag-1"],
    sourceExcerpt: "Schedule 3 excerpt text.",
    resolvedLocator: "schedule 3",
    rawLocators: ["Schedule 3"],
    resolutionMode: "container",
    ...overrides,
  };
}

describe("legal-authority-display", () => {
  it("prefers proposition text for one-line authority summaries", () => {
    expect(
      authorityHeadlineSummary(
        buildReference({
          label: "Schedule 3",
          propositionIds: ["prop:schedule"],
        }),
        propositionById,
      ),
    ).toBe("Defines the derogation conditions for record keeping.");

    expect(
      authorityHeadlineSummary(
        buildReference({
          label: "regulation 36(4)",
          locator: "regulation 36(4)",
          propositionIds: ["prop:reg36"],
          status: "resolved",
          accent: "resolved",
          resolutionMode: "exact",
        }),
        propositionById,
      ),
    ).toBe("Requires calculations and records to be retained for five years.");

    expect(
      authorityHeadlineSummary(
        buildReference({
          label: "paragraph 10",
          locator: "paragraph 10",
          propositionIds: ["prop:para10"],
          status: "resolved",
          accent: "resolved",
          resolutionMode: "exact",
        }),
        propositionById,
      ),
    ).toBe("Defines crops with high nitrogen demand.");
  });

  it("falls back to why-it-matters and material roles without exposing IDs", () => {
    const summary = authorityHeadlineSummary(
      buildReference({
        propositionIds: [],
        whyThisMatters: "Reviewer attention required for this reference",
        sourceExcerpt: null,
      }),
      propositionById,
    );

    expect(summary).toContain("Reviewer attention required");
    expect(summary).not.toContain("prop:");
    expect(summary).not.toContain("frag-");
  });

  it("labels supporting proposition counts in reviewer language", () => {
    expect(supportingPropositionCountLabel(12)).toBe("12 supporting propositions");
    expect(supportingPropositionCountLabel(1)).toBe("1 supporting proposition");
    expect(supportingPropositionCountLabel(0)).toBe("No supporting propositions");
  });

  it("surfaces why-it-matters copy for the card body", () => {
    expect(
      authorityWhyItMatters(
        buildReference({
          whyThisMatters: "Constrains statement",
        }),
      ),
    ).toBe("Constrains statement");
  });
});
