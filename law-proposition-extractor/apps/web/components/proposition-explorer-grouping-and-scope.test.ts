import { describe, expect, it } from "vitest";

import {
  propositionGroupMetaChipText,
  propositionMatchesPrimaryVisibleScopeFilter,
  scopeFilterDisplayLabel,
  type UnknownRecord,
} from "./proposition-explorer-helpers";

describe("propositionGroupMetaChipText", () => {
  it("formats EU/UK two-row pair with same wording", () => {
    expect(
      propositionGroupMetaChipText({
        sourceRowCount: 2,
        allSameWording: true,
        jurisdictionBadgeLabels: ["EU", "UK"],
      })
    ).toBe("🇪🇺 EU / 🇬🇧 UK · same wording");
  });

  it("formats EU/UK two-row pair with different wording", () => {
    expect(
      propositionGroupMetaChipText({
        sourceRowCount: 2,
        allSameWording: false,
        jurisdictionBadgeLabels: ["UK", "EU"],
      })
    ).toBe("🇪🇺 EU / 🇬🇧 UK · different wording");
  });

  it("uses source-row count for non EU/UK pairs", () => {
    expect(
      propositionGroupMetaChipText({
        sourceRowCount: 2,
        allSameWording: true,
        jurisdictionBadgeLabels: ["EU", "FR"],
      })
    ).toBe("2 source rows · 🇪🇺 EU, FR · same wording");
  });

  it("uses single-source-row label with jurisdiction", () => {
    expect(
      propositionGroupMetaChipText({
        sourceRowCount: 1,
        allSameWording: true,
        jurisdictionBadgeLabels: ["EU"],
      })
    ).toBe("Single source row · 🇪🇺 EU");
  });
});

describe("scopeFilterDisplayLabel", () => {
  it("maps germinal_products preset token", () => {
    expect(scopeFilterDisplayLabel("germinal_products")).toBe("Germinal products");
  });
});

describe("Article 109-style scope filtering (primary links only)", () => {
  const scopeById = new Map<string, UnknownRecord>([
    [
      "equine",
      { id: "equine", slug: "equine", label: "Equine", synonyms: ["horse"] },
    ],
    [
      "bovine",
      { id: "bovine", slug: "bovine", label: "Bovine", synonyms: [] },
    ],
    [
      "germinal_products",
      {
        id: "germinal_products",
        slug: "germinal_products",
        label: "Germinal products",
        synonyms: [],
      },
    ],
  ]);

  const links: UnknownRecord[] = [
    {
      proposition_id: "p-equine",
      scope_id: "equine",
      relevance: "direct",
      confidence: "high",
      inheritance: "explicit",
    },
    {
      proposition_id: "p-bovine",
      scope_id: "bovine",
      relevance: "direct",
      confidence: "high",
      inheritance: "explicit",
    },
    {
      proposition_id: "p-germinal",
      scope_id: "germinal_products",
      relevance: "direct",
      confidence: "high",
      inheritance: "explicit",
    },
  ];

  it("with no scope filter, both bovine and equine primaries match", () => {
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-bovine", "", links, scopeById)
    ).toBe(true);
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-equine", "", links, scopeById)
    ).toBe(true);
  });

  it("scope=equine hides bovine-only primary row", () => {
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-equine", "equine", links, scopeById)
    ).toBe(true);
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-bovine", "equine", links, scopeById)
    ).toBe(false);
  });

  it("bovine and germinal_products presets only show matching primaries", () => {
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-bovine", "bovine", links, scopeById)
    ).toBe(true);
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-equine", "bovine", links, scopeById)
    ).toBe(false);
    expect(
      propositionMatchesPrimaryVisibleScopeFilter(
        "p-germinal",
        "germinal_products",
        links,
        scopeById
      )
    ).toBe(true);
    expect(
      propositionMatchesPrimaryVisibleScopeFilter(
        "p-equine",
        "germinal_products",
        links,
        scopeById
      )
    ).toBe(false);
  });
});
