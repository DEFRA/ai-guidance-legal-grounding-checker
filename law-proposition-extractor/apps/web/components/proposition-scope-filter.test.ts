import { describe, expect, it } from "vitest";

import {
  formatArticleClusterHeading,
  prettifyArticleHeadingFragment,
  propositionMatchesPrimaryVisibleScopeFilter,
  scopeMatchesTaxonomyFilter,
} from "./proposition-explorer-helpers";
import { completenessDisplayLabel, completenessNormalizedStatus } from "./structured-proposition-ui";

describe("propositionMatchesPrimaryVisibleScopeFilter", () => {
  const scopeById = new Map([
    [
      "equine",
      { id: "equine", slug: "equine", label: "Equine", synonyms: ["equidae"] },
    ],
    [
      "bovine",
      { id: "bovine", slug: "bovine", label: "Bovine", synonyms: ["cattle", "bovidae"] },
    ],
    [
      "non_equine_meta",
      {
        id: "non_equine_meta",
        slug: "non_equine_meta",
        label: "Non-equine species list",
        synonyms: [],
      },
    ],
  ]);

  const link = (pid: string, scope: string, relevance: string, confidence: string) => ({
    proposition_id: pid,
    scope_id: scope,
    relevance,
    confidence,
  });

  it("excludes bovine-only proposition for scope=equine (primary links)", () => {
    const links = [link("p-bov", "bovine", "direct", "high")];
    expect(propositionMatchesPrimaryVisibleScopeFilter("p-bov", "equine", links, scopeById)).toBe(
      false
    );
  });

  it("includes bovine proposition for scope=bovine", () => {
    const links = [link("p-bov", "bovine", "direct", "high")];
    expect(propositionMatchesPrimaryVisibleScopeFilter("p-bov", "bovine", links, scopeById)).toBe(
      true
    );
  });

  it('does not treat substring "equine" inside label as match', () => {
    const links = [link("p-ne", "non_equine_meta", "direct", "high")];
    expect(propositionMatchesPrimaryVisibleScopeFilter("p-ne", "equine", links, scopeById)).toBe(
      false
    );
  });

  it("excludes when equine exists only on non-primary links", () => {
    const links = [
      link("p1", "bovine", "direct", "high"),
      link("p1", "equine", "contextual", "medium"),
    ];
    expect(propositionMatchesPrimaryVisibleScopeFilter("p1", "equine", links, scopeById)).toBe(
      false
    );
  });

  it("matches synonym exact token equidae on primary equine scope record", () => {
    const links = [link("p-eq", "equine", "direct", "high")];
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-eq", "equidae", links, scopeById)
    ).toBe(true);
  });

  it("excludes deterministic direct/high label-only links from primary filter", () => {
    const links = [
      {
        proposition_id: "p-label-only",
        scope_id: "equine",
        relevance: "direct",
        confidence: "high",
        method: "deterministic",
        signals: { evidence_field: "proposition_label" },
      },
    ];
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-label-only", "equine", links, scopeById)
    ).toBe(false);
  });

  it("includes deterministic direct/high grounded structured links in primary filter", () => {
    const links = [
      {
        proposition_id: "p-structured",
        scope_id: "equine",
        relevance: "direct",
        confidence: "high",
        method: "deterministic",
        signals: { evidence_field: "legal_subject" },
      },
    ];
    expect(
      propositionMatchesPrimaryVisibleScopeFilter("p-structured", "equine", links, scopeById)
    ).toBe(true);
  });
});

describe("scopeMatchesTaxonomyFilter", () => {
  it("slug exact match", () => {
    const sc = { slug: "equine", label: "Equine", synonyms: [] };
    expect(scopeMatchesTaxonomyFilter("equine", "equine", sc)).toBe(true);
    expect(scopeMatchesTaxonomyFilter("equine", "bovine", { slug: "bovine", label: "Bovine" })).toBe(
      false
    );
  });
});

describe("prettifyArticleHeadingFragment / formatArticleClusterHeading", () => {
  it("capitalizes article N in ref: titles", () => {
    expect(prettifyArticleHeadingFragment("article 4 — verification of ear tags")).toBe(
      "Article 4 — verification of ear tags"
    );
  });

  it("formats ref: cluster keys for display", () => {
    expect(formatArticleClusterHeading("ref:article 4 — bovine")).toBe(
      "Article 4 — bovine"
    );
  });
});

describe("completenessNormalizedStatus + completenessDisplayLabel", () => {
  it("normalizes hyphenated API values", () => {
    expect(completenessNormalizedStatus("context-dependent")).toBe("context_dependent");
    expect(completenessDisplayLabel("context_dependent")).toBe("Needs context");
  });

  it("renders visible labels for standard statuses", () => {
    expect(completenessDisplayLabel(completenessNormalizedStatus("complete"))).toBe("Complete");
    expect(completenessDisplayLabel(completenessNormalizedStatus("fragmentary"))).toBe(
      "Fragmentary"
    );
    expect(completenessDisplayLabel("not_assessed")).toBe("Not assessed");
  });
});
