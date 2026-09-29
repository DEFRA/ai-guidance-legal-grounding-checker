import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  classificationFromProposition,
  DEFAULT_EXPLORER_CLASSIFICATION_FILTERS,
  legalEffectDisplayLabel,
  matchesExplorerClassificationFilters,
  propositionInformativeLabel,
  tierDisplayLabel,
} from "@/components/proposition-classification-ui";
import {
  humanReviewNotesForDisplay,
  territorialApplicationFromProposition,
} from "@/components/proposition-explorer-helpers";

type RegressionFixture = {
  raw_extraction: Record<string, unknown>;
  extraction_meta: Record<string, unknown>;
  expected: {
    ui: {
      tier_label: string;
      legal_effect_label: string;
      informative_label: string;
      territory: string;
      compliance_relevant: boolean;
      comparison_anchor: boolean;
      hidden_in_compliance_only_filter: boolean;
    };
    territorial_application: string[];
    proposition_tier: string;
    legal_effect_type: string;
    review_notes: null;
  };
};

const FIXTURE_PATH = join(
  __dirname,
  "../../../tests/fixtures/regression/agricultural_land_england_territorial_application.json"
);

const FIXTURE = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8")) as RegressionFixture;

function normalizedExplorerArtifact(): Record<string, unknown> {
  const { expected } = FIXTURE;
  return {
    ...FIXTURE.raw_extraction,
    proposition_tier: expected.proposition_tier,
    legal_effect_type: expected.legal_effect_type,
    territorial_application: expected.territorial_application,
    is_compliance_relevant: expected.ui.compliance_relevant,
    is_comparison_anchor: expected.ui.comparison_anchor,
    label: expected.ui.informative_label,
    review_notes: expected.review_notes,
    extraction_debug_meta: {
      ...FIXTURE.extraction_meta,
      display_label: FIXTURE.extraction_meta.display_label,
    },
    notes: "",
  };
}

describe("regression fixture: agricultural land England territorial application", () => {
  it("formats classification chips and informative label for explorer UI", () => {
    const oa = normalizedExplorerArtifact();
    const view = classificationFromProposition(oa);
    const ui = FIXTURE.expected.ui;

    expect(tierDisplayLabel(view.tier)).toBe(ui.tier_label);
    expect(legalEffectDisplayLabel(view.legalEffectType)).toBe(ui.legal_effect_label);
    expect(propositionInformativeLabel(oa)).toBe(ui.informative_label);
    expect(territorialApplicationFromProposition(oa)).toEqual([ui.territory]);
    expect(view.isComplianceRelevant).toBe(ui.compliance_relevant);
    expect(view.isComparisonAnchor).toBe(ui.comparison_anchor);
  });

  it("does not surface extraction meta blob as human review notes", () => {
    const legacyNotes = `judit_extraction_meta:${JSON.stringify(FIXTURE.extraction_meta)}`;
    const oa = {
      ...FIXTURE.raw_extraction,
      notes: legacyNotes,
      review_notes: null,
      extraction_debug_meta: FIXTURE.extraction_meta,
    };
    expect(humanReviewNotesForDisplay(oa)).toBeNull();
  });

  it("excludes scope proposition from compliance-only explorer filter", () => {
    const oa = normalizedExplorerArtifact();
    expect(
      matchesExplorerClassificationFilters(oa, {
        ...DEFAULT_EXPLORER_CLASSIFICATION_FILTERS,
        complianceRelevantOnly: true,
      })
    ).toBe(false);
    expect(
      matchesExplorerClassificationFilters(oa, DEFAULT_EXPLORER_CLASSIFICATION_FILTERS)
    ).toBe(true);
  });

  it("documents problematic raw extraction categories for regression", () => {
    expect(FIXTURE.raw_extraction.categories).toEqual(["obligation"]);
    expect(FIXTURE.raw_extraction.cross_reference_key).toBe("uk:these-regulations:apply-to");
    expect(FIXTURE.raw_extraction.label).toBe("Territorial application");
  });
});
