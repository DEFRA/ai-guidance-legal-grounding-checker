import { describe, expect, it } from "vitest";

import {
  canonicalArticleClusterKey,
  canonicalStructuredListPathKey,
  formatArticleClusterDisplayHeading,
  formatStructuredLocatorLabel,
  propositionDisplayLabel,
  relatedCrossReferenceDisplayLine,
} from "./proposition-explorer-helpers";

describe("canonicalStructuredListPathKey", () => {
  it("normalizes equine pilot list locator", () => {
    expect(canonicalStructuredListPathKey("article:109:list:1-d-i/foo")).toBe("109:1-d-i");
    expect(canonicalStructuredListPathKey("article:114:list:1-a")).toBe("114:1-a");
  });

  it("returns null without :list:", () => {
    expect(canonicalStructuredListPathKey("article:109/full")).toBe(null);
  });
});

describe("formatStructuredLocatorLabel", () => {
  it("matches pipeline-style paths", () => {
    expect(formatStructuredLocatorLabel("article:109:list:1-a-i")).toBe("Art 109 §1(a)(i)");
    expect(formatStructuredLocatorLabel("article:114:list:1-b")).toBe("Art 114 §1(b)");
  });
});

describe("formatArticleClusterDisplayHeading", () => {
  it("adds thematic subtitle for known articles", () => {
    expect(formatArticleClusterDisplayHeading("article:109")).toBe(
      "Article 109 — database of kept terrestrial animals"
    );
    expect(formatArticleClusterDisplayHeading("article:114")).toBe(
      "Article 114 — identification of kept equine animals"
    );
    expect(formatArticleClusterDisplayHeading("article:99")).toBe("Article 99");
  });

  it("prefers captured legislative heading over compatibility subtitles", () => {
    expect(
      formatArticleClusterDisplayHeading("article:109", {
        legislativeHeading: "database of kept terrestrial animals (official)",
      })
    ).toBe("Article 109 — database of kept terrestrial animals (official)");
    expect(
      formatArticleClusterDisplayHeading("article:49a", {
        legislativeHeading:
          "Separate stowage of catches below the minimum conservation reference sizes",
      })
    ).toBe(
      "Article 49a — Separate stowage of catches below the minimum conservation reference sizes"
    );
  });
});

describe("canonicalArticleClusterKey", () => {
  it("uses fragment_locator article over parent-scoped article_reference (Art 109 vs 114 list)", () => {
    const oa = {
      article_reference: "Article 109 — database of kept terrestrial animals",
      fragment_locator: "article:114:list:1-a/foo",
    };
    expect(canonicalArticleClusterKey(oa)).toBe("article:114");
  });

  it("keeps Article 109 when locator and reference agree on 109", () => {
    const oa = {
      article_reference: "Article 109",
      fragment_locator: "article:109:list:1-d-i",
    };
    expect(canonicalArticleClusterKey(oa)).toBe("article:109");
  });

  it("falls back to article_reference when fragment cannot be parsed to an article", () => {
    const oa = {
      article_reference: "Article 112",
      fragment_locator: "document:full",
    };
    expect(canonicalArticleClusterKey(oa)).toBe("article:112");
  });
});

describe("relatedCrossReferenceDisplayLine", () => {
  it("returns banner when reference cites a later article than fragment_locator", () => {
    expect(
      relatedCrossReferenceDisplayLine({
        article_reference: "Article 114",
        fragment_locator: "article:109:list:1-d-i",
      })
    ).toBe("Related cross-reference to Article 114");
  });

  it("returns null when locator already targets the cited article (not an in-host forward cite)", () => {
    expect(
      relatedCrossReferenceDisplayLine({
        article_reference: "Article 109 — parent",
        fragment_locator: "article:114:list:1-a",
      })
    ).toBe(null);
  });
});

describe("propositionDisplayLabel", () => {
  it("uses curated path tails for structured lists", () => {
    const oa = {
      fragment_locator: "article:109:list:1-d-i",
      label:
        "Art 109 §1(d)(i) — member states shall establish and maintain a computer database for the recording of at least something long",
      proposition_text: "",
    };
    expect(propositionDisplayLabel(oa)).toBe(
      "Art 109 §1(d)(i) — equine identification information"
    );
  });

  it("uses Art 114 structured tails", () => {
    expect(
      propositionDisplayLabel({
        fragment_locator: "article:114:list:1-c",
        label: "long extraction label unchanged in id",
      })
    ).toBe("Art 114 §1(c) — lifetime identification document");
  });

  it("rewrites xml:article-N-M extraction labels into Article N(M) headings", () => {
    expect(
      propositionDisplayLabel({
        label:
          "xml:article-1-2 — this apply without prejudice to decision 96/78/ec and other measures",
      })
    ).toBe(
      "Article 1(2) — This applies without prejudice to Decision 96/78/EC and other measures",
    );
  });

  it("rewrites xml:article-N-1 to Article N(1) + readable remainder", () => {
    expect(
      propositionDisplayLabel({
        label: "xml:article-1-1 — this apply to delegated acts pursuant to directive 12/345/ec",
      })
    ).toBe(
      "Article 1(1) — This applies to delegated acts pursuant to Directive 12/345/EC",
    );
  });

  it("keeps definition labels as Definition — term", () => {
    expect(
      propositionDisplayLabel({
        fragment_locator: "article:2",
        label: "Definition — “keeper”",
        proposition_text: "keeper means a natural or legal person responsible for equidae.",
      })
    ).toBe("Definition — “keeper”");
  });
});
