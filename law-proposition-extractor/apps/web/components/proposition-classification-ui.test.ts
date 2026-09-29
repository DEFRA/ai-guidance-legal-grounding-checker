import { describe, expect, it } from "vitest";

import {
  classificationFromProposition,
  DEFAULT_EXPLORER_CLASSIFICATION_FILTERS,
  legalEffectDisplayLabel,
  legacyLegalEffectGuess,
  matchesExplorerClassificationFilters,
  partitionSummariesByScopeSecondary,
  propositionInformativeLabel,
  tierDisplayLabel,
} from "./proposition-classification-ui";

describe("classificationFromProposition (application scope example)", () => {
  const oa = {
    proposition_text: "These Regulations apply to agricultural land in England.",
    proposition_tier: "scope_rule",
    legal_effect_type: "application_scope",
    label: "Application to agricultural land in England",
    territorial_application: ["England"],
    is_compliance_relevant: false,
    is_comparison_anchor: true,
  };

  it("surfaces tier, effect, territory, and flags for UI cards", () => {
    const view = classificationFromProposition(oa);
    expect(tierDisplayLabel(view.tier)).toBe("Scope rule");
    expect(legalEffectDisplayLabel(view.legalEffectType)).toBe("Application scope");
    expect(propositionInformativeLabel(oa)).toBe("Application to agricultural land in England");
    expect(view.territorialApplication).toEqual(["England"]);
    expect(view.isComplianceRelevant).toBe(false);
    expect(view.isComparisonAnchor).toBe(true);
  });
});

describe("matchesExplorerClassificationFilters", () => {
  const scopeOa = {
    proposition_tier: "scope_rule",
    legal_effect_type: "application_scope",
    is_compliance_relevant: false,
    is_comparison_anchor: true,
  };

  it("includes scope rules in default view", () => {
    expect(matchesExplorerClassificationFilters(scopeOa, DEFAULT_EXPLORER_CLASSIFICATION_FILTERS)).toBe(
      true
    );
  });

  it("excludes scope rules when compliance-relevant only is enabled", () => {
    expect(
      matchesExplorerClassificationFilters(scopeOa, {
        ...DEFAULT_EXPLORER_CLASSIFICATION_FILTERS,
        complianceRelevantOnly: true,
      })
    ).toBe(false);
  });

  it("hides citation and commencement unless instrument metadata is shown", () => {
    const citation = { proposition_tier: "instrument_metadata", legal_effect_type: "citation" };
    expect(matchesExplorerClassificationFilters(citation, DEFAULT_EXPLORER_CLASSIFICATION_FILTERS)).toBe(
      false
    );
    expect(
      matchesExplorerClassificationFilters(citation, {
        ...DEFAULT_EXPLORER_CLASSIFICATION_FILTERS,
        showInstrumentMetadata: true,
      })
    ).toBe(true);
  });

  it("hides legacy unclassified citation rows using text heuristics", () => {
    const legacyCitation = {
      proposition_text: "These Regulations may be cited as the Example Regulations 2018.",
      action: "may be cited as",
      categories: ["obligation"],
    };
    expect(legacyLegalEffectGuess(legacyCitation)).toBe("citation");
    expect(
      matchesExplorerClassificationFilters(legacyCitation, DEFAULT_EXPLORER_CLASSIFICATION_FILTERS)
    ).toBe(false);
  });
});

describe("partitionSummariesByScopeSecondary", () => {
  it("splits scope_rule groups into a secondary bucket when collapse is enabled", () => {
    const propById = new Map<string, Record<string, unknown>>([
      [
        "p-scope",
        { id: "p-scope", proposition_tier: "scope_rule", legal_effect_type: "application_scope" },
      ],
      [
        "p-sub",
        { id: "p-sub", proposition_tier: "substantive_rule", legal_effect_type: "obligation" },
      ],
    ]);
    const summaries = [
      { group_id: "g1", row_ids: ["p-scope"] },
      { group_id: "g2", row_ids: ["p-sub"] },
    ] as Parameters<typeof partitionSummariesByScopeSecondary>[0];

    const { primary, scopeSecondary } = partitionSummariesByScopeSecondary(
      summaries,
      propById,
      true
    );
    expect(primary.map((s) => s.group_id)).toEqual(["g2"]);
    expect(scopeSecondary.map((s) => s.group_id)).toEqual(["g1"]);
  });
});
