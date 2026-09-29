import { describe, expect, it } from "vitest";

import {
  articleClusterKeyFromRow,
  canonicalArticleFromFragmentLocator,
  canonicalLineageKeyForGrouping,
  collectRowContributionsForMergeDebug,
  groupKeyForPropositionRow,
  hiddenParentListSummaryExplorerNote,
  humanReadableArticleLocatorLineageStem,
  isRepealedOrEmptyFragment,
  mergeSemanticallyDuplicatePropositionGroups,
  normalizePropositionText,
  normalizePropositionTextForLineageGroup,
  partitionPropositionGroupsByArticleCluster,
  shouldShowPropositionGroupMergeLocatorDebug,
  shouldSuppressCoarseParentPropositionInDefaultView,
  suppressedParentListSummaryCountByArticleCluster,
  wordingFingerprintForPropositionGroupCompare,
  type UnknownRecord,
} from "./proposition-explorer-helpers";

function effRow(oa: UnknownRecord): UnknownRecord {
  return { original_artifact: oa, effective_status: "generated" };
}

describe("2015/262 Article 3 — duplicate explorer groups", () => {
  const srcEu262: UnknownRecord = {
    id: "sr-eu-262-art3",
    jurisdiction: "EU",
    title: "Commission Implementing Regulation (EU) 2015/262",
    citation: "(EU) 2015/262",
    metadata: { instrument_id: "EU 2015/262" },
  };
  const sources = [srcEu262];

  it("merges colon para and human §1 locators into one groupKey when texts match", () => {
    const colon = effRow({
      id: "dup-a",
      source_record_id: "sr-eu-262-art3",
      proposition_key: "legacy:article-3-para-1:p001",
      fragment_locator: "article:3:para:1",
      article_reference: "Article 3",
      proposition_text: "All equidae shall be identified in accordance with this Regulation.",
    });
    const human = effRow({
      id: "dup-b",
      source_record_id: "sr-eu-262-art3",
      proposition_key: "legacy:Article-3-1-frontier:p002",
      fragment_locator: "Article 3(1)",
      article_reference: "Article 3",
      proposition_text: "All equidae shall be identified in accordance with this Regulation.",
    });
    expect(groupKeyForPropositionRow(colon, sources)).toBe(groupKeyForPropositionRow(human, sources));
  });

  it("mergeSemanticallyDuplicatePropositionGroups collapses two partitioned groups to one card with two rows", () => {
    const colon = effRow({
      id: "dup-a",
      source_record_id: "sr-eu-262-art3",
      proposition_key: "k-a",
      fragment_locator: "article:3:para:1",
      proposition_text: "All equidae shall be identified in accordance with this Regulation.",
    });
    const human = effRow({
      id: "dup-b",
      source_record_id: "sr-eu-262-art3",
      proposition_key: "k-b",
      fragment_locator: "Article 3(1)",
      proposition_text: "All equidae shall be identified in accordance with this Regulation.",
    });
    const partitioned = partitionPropositionGroupsByArticleCluster([
      { key: "EU 2015/262\u001farticle:3:para:1", rows: [colon] },
      { key: "EU 2015/262\u001farticle:3:para:1-bis", rows: [human] },
    ]);
    const merged = mergeSemanticallyDuplicatePropositionGroups(partitioned, sources);
    expect(merged.length).toBe(1);
    expect(merged[0]?.rows.length).toBe(2);
    const md = merged[0]?.mergeDebug;
    expect(md).toBeDefined();
    expect(md?.mergedGroupCount).toBe(2);
    expect(md?.canonicalLineageKey).toBe("article:3:para:1");
    expect(md?.contributingLocatorForms).toContain("article:3:para:1");
    expect(md?.contributingLocatorForms).toContain("Article 3(1)");
    expect(md?.mergedArtifactIds).toEqual(["dup-a", "dup-b"].sort((a, b) => a.localeCompare(b)));
    expect([...(md?.contributingPropositionKeys ?? [])].sort((a, b) => a.localeCompare(b))).toEqual(
      ["k-a", "k-b"]
    );
    expect(md?.mergedGroupIds.length).toBe(2);
  });

  it("leaves Article 3(1), 3(2), and 3(4) as separate merged groups", () => {
    const p1 = effRow({
      id: "p1",
      source_record_id: "sr-eu-262-art3",
      proposition_key: "k1",
      fragment_locator: "article:3:para:1",
      proposition_text: "All equidae shall be identified in accordance with this Regulation.",
    });
    const p2 = effRow({
      id: "p2",
      source_record_id: "sr-eu-262-art3",
      proposition_key: "k2",
      fragment_locator: "article:3:para:2",
      proposition_text:
        "The keeper shall act in accordance with this Regulation on behalf of and in agreement with the owner.",
    });
    const p4 = effRow({
      id: "p4",
      source_record_id: "sr-eu-262-art3",
      proposition_key: "k4",
      fragment_locator: "Article 3(4)",
      proposition_text: "The competent authority shall record movement in the database.",
    });
    const merged = mergeSemanticallyDuplicatePropositionGroups(
      [
        { key: "a", rows: [p1] },
        { key: "b", rows: [p2] },
        { key: "c", rows: [p4] },
      ],
      sources
    );
    expect(merged.length).toBe(3);
  });
});

describe("shouldShowPropositionGroupMergeLocatorDebug", () => {
  it("hides panel when only one explorer group", () => {
    expect(
      shouldShowPropositionGroupMergeLocatorDebug({
        mergedGroupCount: 1,
        mergedGroupIds: ["a"],
        mergedArtifactIds: ["x"],
        canonicalLineageKey: "article:3:para:1",
        contributingLocatorForms: ["a", "b"],
        contributingPropositionKeys: [],
      })
    ).toBe(false);
  });

  it("shows when multiple locators were folded together", () => {
    expect(
      shouldShowPropositionGroupMergeLocatorDebug({
        mergedGroupCount: 2,
        mergedGroupIds: ["g1", "g2"],
        mergedArtifactIds: ["a"],
        canonicalLineageKey: "article:3:para:1",
        contributingLocatorForms: ["Article 3(1)", "article:3:para:1", "article_cluster:article:3"],
        contributingPropositionKeys: ["k1", "k2"],
      })
    ).toBe(true);
  });

  it("shows when same locator string but distinct artifacts", () => {
    expect(
      shouldShowPropositionGroupMergeLocatorDebug({
        mergedGroupCount: 2,
        mergedGroupIds: ["g1", "g2"],
        mergedArtifactIds: ["id1", "id2"],
        canonicalLineageKey: "article:3:para:1",
        contributingLocatorForms: ["article:3:para:1", "article_cluster:article:3"],
        contributingPropositionKeys: [],
      })
    ).toBe(true);
  });

  it("hides when one locator form and one artifact despite two merged group ids", () => {
    expect(
      shouldShowPropositionGroupMergeLocatorDebug({
        mergedGroupCount: 2,
        mergedGroupIds: ["g1", "g2"],
        mergedArtifactIds: ["only"],
        canonicalLineageKey: null,
        contributingLocatorForms: ["article_cluster:article:3"],
        contributingPropositionKeys: [],
      })
    ).toBe(false);
  });
});

describe("collectRowContributionsForMergeDebug", () => {
  it("captures fragment locator and proposition_key from row", () => {
    const r = effRow({
      id: "p1",
      source_record_id: "s1",
      proposition_key: "pk-1",
      fragment_locator: "Article 3(1)",
      article_reference: "Article 3",
    });
    const c = collectRowContributionsForMergeDebug(r);
    expect(c.locatorForms).toContain("Article 3(1)");
    expect(c.locatorForms).toContain("article_ref:Article 3");
    expect(c.propositionKeys).toContain("pk-1");
  });
});

describe("wordingFingerprintForPropositionGroupCompare", () => {
  it("treats identical proposition_text but different labels as diff wording", () => {
    const eu = {
      proposition_text: "The Member States shall ensure X.",
      label: "Art 109 §1(d)(i) — database — equine unique code",
    };
    const uk = {
      proposition_text: "The Member States shall ensure X.",
      label: "Art 109 §1(d)(i) — equine database — unique code",
    };
    expect(wordingFingerprintForPropositionGroupCompare(eu)).not.toBe(
      wordingFingerprintForPropositionGroupCompare(uk)
    );
  });
});

describe("normalizePropositionTextForLineageGroup", () => {
  it("aligns UK/EU microcopy for transmission duty (optional article)", () => {
    const eu = "Operators of kept animals must ensure that the information on those animals is transmitted.";
    const uk = "Operators of kept animals must ensure that information on those animals is transmitted.";
    expect(normalizePropositionTextForLineageGroup(eu)).toBe(
      normalizePropositionTextForLineageGroup(uk)
    );
  });

  it("aligns shall→must for grouping", () => {
    expect(normalizePropositionTextForLineageGroup("Operators shall ensure")).toBe(
      normalizePropositionTextForLineageGroup("Operators must ensure")
    );
  });
});

describe("humanReadableArticleLocatorLineageStem", () => {
  it("maps frontier-style locators to structured list stems", () => {
    expect(humanReadableArticleLocatorLineageStem("Article 114(1)(a)")).toBe("article:114:list:1-a");
    expect(humanReadableArticleLocatorLineageStem("Article 114(2)")).toBe("article:114:para:2");
  });

  it("maps Article 109 §1(d)(i)-style triple parentheticals to the pipeline list key", () => {
    expect(humanReadableArticleLocatorLineageStem("Article 109(1)(d)(i)")).toBe(
      "article:109:list:1-d-i"
    );
  });
});

describe("canonicalLineageKeyForGrouping", () => {
  it("normalizes :list:, hyphen slug, underscore slug, and human forms to one key", () => {
    expect(canonicalLineageKeyForGrouping("article:109:list:1-d-i/foo")).toBe(
      "article:109:list:1-d-i"
    );
    expect(canonicalLineageKeyForGrouping("article-109-1-d-i")).toBe("article:109:list:1-d-i");
    expect(canonicalLineageKeyForGrouping("article_109_1_d_i")).toBe("article:109:list:1-d-i");
    expect(canonicalLineageKeyForGrouping("Article 109(1)(d)(i)")).toBe("article:109:list:1-d-i");
  });

  it("aligns colon article:N:para:P and underscores with human Article N(P) (e.g. 2015/262 Art 3)", () => {
    expect(canonicalLineageKeyForGrouping("article:3:para:1")).toBe("article:3:para:1");
    expect(canonicalLineageKeyForGrouping("Article 3(1)")).toBe("article:3:para:1");
    expect(canonicalLineageKeyForGrouping("article:3:para:1/excerpt")).toBe("article:3:para:1");
    expect(canonicalLineageKeyForGrouping("article_3_para_1")).toBe("article:3:para:1");
    expect(canonicalLineageKeyForGrouping("Article 3(1)")).not.toBe(
      canonicalLineageKeyForGrouping("Article 3(2)")
    );
    expect(canonicalLineageKeyForGrouping("Article 3(4)")).toBe("article:3:para:4");
    expect(canonicalLineageKeyForGrouping("article:3:para:2")).toBe(
      canonicalLineageKeyForGrouping("Article 3(2)")
    );
  });

  it("does not merge different nested list items", () => {
    expect(canonicalLineageKeyForGrouping("article:109:list:1-d-i")).not.toBe(
      canonicalLineageKeyForGrouping("article:109:list:1-d-ii")
    );
    expect(canonicalLineageKeyForGrouping("article:109:list:1-c-i")).not.toBe(
      canonicalLineageKeyForGrouping("article:109:list:1-d-i")
    );
  });
});

describe("groupKeyForPropositionRow — Article 114 equine", () => {
  const euUmbrella = effRow({
    id: "prop-eu-umb",
    proposition_key: "equine-law-eu-2016-429-art114-equine:article-114:p004",
    fragment_locator: "article:114",
    proposition_text:
      "Operators keeping kept animals shall ensure individually identified by: (a) a unique code.",
  });
  const ukUmbrella = effRow({
    id: "prop-uk-umb",
    proposition_key: "equine-law-uk-2016-429-art114-equine:article-114:p004",
    fragment_locator: "article:114",
    proposition_text:
      "Operators keeping kept animals shall ensure individually identified by: (a) a unique code.",
  });
  const euListA = effRow({
    id: "prop-eu-a",
    proposition_key: "equine-law-eu-2016-429-art114-equine:1-a:p001",
    fragment_locator: "article:114:list:1-a",
    proposition_text: "Article 114 … ensure … unique code.",
  });
  const ukListA = effRow({
    id: "prop-uk-a",
    proposition_key: "equine-law-uk-2016-429-art114-equine:1-a:p001",
    fragment_locator: "article:114:list:1-a",
    proposition_text: "Article 114 … ensure … unique code.",
  });
  const euTwo = effRow({
    id: "prop-eu-2",
    proposition_key: "equine-law-eu-2016-429-art114-equine:article-114:p005",
    fragment_locator: "article:114",
    proposition_text:
      "Operators shall ensure that the information on those animals is transmitted to the database.",
  });
  const ukTwo = effRow({
    id: "prop-uk-2",
    proposition_key: "equine-law-uk-2016-429-art114-equine:article-114:p005",
    fragment_locator: "article:114",
    proposition_text:
      "Operators shall ensure that information on those animals is transmitted to the database.",
  });

  it("merges coarse article:114 EU/UK rows that share normalized text", () => {
    expect(groupKeyForPropositionRow(euUmbrella)).toBe(groupKeyForPropositionRow(ukUmbrella));
  });

  it("merges coarse §2 EU/UK rows where only optional-article differs", () => {
    expect(groupKeyForPropositionRow(euTwo)).toBe(groupKeyForPropositionRow(ukTwo));
  });

  it("merges list rows by locator even when proposition_key differs by source prefix", () => {
    expect(groupKeyForPropositionRow(euListA)).toBe(groupKeyForPropositionRow(ukListA));
    expect(groupKeyForPropositionRow(euListA)).toBe("article:114:list:1-a");
  });

  it("aligns frontier Article 114(1)(a) with heuristic article:114:list:1-a group key", () => {
    const frontier = effRow({
      id: "p-frontier",
      proposition_key: "equine-law-eu-2016-429-art114-equine:article-114-1-a:p001",
      fragment_locator: "Article 114(1)(a)",
      proposition_text: "Operators must ensure unique code.",
    });
    expect(groupKeyForPropositionRow(frontier)).toBe("article:114:list:1-a");
    expect(groupKeyForPropositionRow(euListA)).toBe(groupKeyForPropositionRow(frontier));
  });
});

describe("groupKeyForPropositionRow — Article 109 equine EU/UK lineage", () => {
  it("merges EU :list:, UK slug, underscore slug, and human §1(d)(i) despite differing proposition_key", () => {
    const euList = effRow({
      id: "eu-109-di",
      source_record_id: "equine-law-eu-2016-429-art109",
      proposition_key: "equine-law-eu-2016-429-art109-equine:1-d-i:p004",
      fragment_locator: "article:109:list:1-d-i",
      proposition_text: "Member States shall record database — equine unique code.",
    });
    const ukHyphen = effRow({
      id: "uk-109-di-h",
      source_record_id: "equine-law-uk-2016-429-art109",
      proposition_key: "equine-law-uk-2016-429-art109-equine:article-109-1-d-i:p004",
      fragment_locator: "article-109-1-d-i",
      proposition_text: "Member States shall record equine database — unique code.",
    });
    const ukUnder = effRow({
      id: "uk-109-di-u",
      source_record_id: "equine-law-uk-2016-429-art109",
      proposition_key: "equine-law-uk:prop-underscore",
      fragment_locator: "article_109_1_d_i",
      proposition_text: "Member States shall record equine database — unique code.",
    });
    const ukHuman = effRow({
      id: "uk-109-di-human",
      source_record_id: "equine-law-uk-2016-429-art109",
      proposition_key: "equine-law-uk-frontier",
      fragment_locator: "Article 109(1)(d)(i)",
      proposition_text: "Member States shall record equine database — unique code.",
    });
    const want = "article:109:list:1-d-i";
    expect(groupKeyForPropositionRow(euList)).toBe(want);
    expect(groupKeyForPropositionRow(ukHyphen)).toBe(want);
    expect(groupKeyForPropositionRow(ukUnder)).toBe(want);
    expect(groupKeyForPropositionRow(ukHuman)).toBe(want);
  });

  it("same canonical locator and multiple sources: proposition text can still differ for diff wording chip", () => {
    const eu = effRow({
      id: "e1",
      source_record_id: "s-eu",
      proposition_key: "k-eu",
      fragment_locator: "article:109:list:1-d-i",
      proposition_text: "database — equine unique code",
    });
    const uk = effRow({
      id: "u1",
      source_record_id: "s-uk",
      proposition_key: "k-uk",
      fragment_locator: "article-109-1-d-i",
      proposition_text: "equine database — unique code",
    });
    expect(groupKeyForPropositionRow(eu)).toBe(groupKeyForPropositionRow(uk));
    const oeu = eu.original_artifact as UnknownRecord;
    const ouk = uk.original_artifact as UnknownRecord;
    expect(
      normalizePropositionText(String(oeu.proposition_text ?? "")) ===
        normalizePropositionText(String(ouk.proposition_text ?? ""))
    ).toBe(false);
  });

  it("leaves adjacent list items unmerged (1-d-i vs 1-d-ii)", () => {
    const di = effRow({
      id: "109-di",
      proposition_key: "a",
      fragment_locator: "article:109:list:1-d-i",
      proposition_text: "x",
    });
    const dii = effRow({
      id: "109-dii",
      proposition_key: "b",
      fragment_locator: "article:109:list:1-d-ii",
      proposition_text: "x",
    });
    expect(groupKeyForPropositionRow(di)).not.toBe(groupKeyForPropositionRow(dii));
  });
});

describe("shouldSuppressCoarseParentPropositionInDefaultView", () => {
  const listA = effRow({
    id: "c-a",
    proposition_key: "eq:1-a:p001",
    fragment_locator: "article:114:list:1-a",
    proposition_text: "a unique code is assigned to each animal.",
  });
  const umbrella = effRow({
    id: "p-umb",
    proposition_key: "eq:article-114:p004",
    fragment_locator: "article:114",
    proposition_text:
      "Operators shall ensure those animals are individually identified by: (a) a unique code …",
  });
  const para2 = effRow({
    id: "p-2",
    proposition_key: "eq:article-114:p005",
    fragment_locator: "article:114",
    proposition_text:
      "Operators shall ensure that the information on those animals is transmitted to the database.",
  });

  it("suppresses §1 umbrella when structured list children exist", () => {
    const u = [listA, umbrella];
    expect(shouldSuppressCoarseParentPropositionInDefaultView(umbrella, u)).toBe(true);
    expect(shouldSuppressCoarseParentPropositionInDefaultView(listA, u)).toBe(false);
  });

  it("does not suppress coarse §2 duty when list children are only §1", () => {
    const u = [listA, para2];
    expect(shouldSuppressCoarseParentPropositionInDefaultView(para2, u)).toBe(false);
  });

  it("suppresses repealed/omitted placeholders regardless of siblings", () => {
    const repealed = effRow({
      id: "rep-1",
      fragment_locator: "article:5",
      proposition_text: "Article 5. . . . . . . . . . . . . . .",
    });
    expect(shouldSuppressCoarseParentPropositionInDefaultView(repealed, [repealed])).toBe(true);
  });
});

describe("isRepealedOrEmptyFragment", () => {
  it("flags repealed dot runs, bare enumerators, and lone headings", () => {
    for (const t of ["", "Article 5. . . . .", "(2). . .", "5.", "ANNEX II", ". . . .", "(a)"]) {
      expect(isRepealedOrEmptyFragment(t)).toBe(true);
    }
  });

  it("keeps genuine short rules", () => {
    for (const t of [
      "Imports are prohibited.",
      "(1) This Regulation establishes a system to prevent IUU fishing.",
      "Article 5 establishes a control system.",
    ]) {
      expect(isRepealedOrEmptyFragment(t)).toBe(false);
    }
  });
});

describe("canonicalArticleFromFragmentLocator (Article 114 human locators)", () => {
  it("clusters Article 114(1)(a) under article:114", () => {
    expect(canonicalArticleFromFragmentLocator("Article 114(1)(a)")).toEqual({
      role: "article",
      num: "114",
      suffix: "",
    });
  });
});

describe("hiddenParentListSummaryExplorerNote", () => {
  it("returns null when nothing is hidden", () => {
    expect(hiddenParentListSummaryExplorerNote(0)).toBeNull();
  });

  it("uses singular and plural copy", () => {
    expect(hiddenParentListSummaryExplorerNote(1)).toBe(
      "1 parent/list-summary proposition hidden because child list items are shown."
    );
    expect(hiddenParentListSummaryExplorerNote(3)).toBe(
      "3 parent/list-summary propositions hidden because child list items are shown."
    );
  });
});

describe("suppressedParentListSummaryCountByArticleCluster", () => {
  const listA = effRow({
    id: "c-a",
    proposition_key: "eq:1-a:p001",
    fragment_locator: "article:114:list:1-a",
    proposition_text: "a unique code is assigned to each animal.",
  });
  const umbrellaEu = effRow({
    id: "u-eu",
    proposition_key: "eq:article-114:p004",
    fragment_locator: "article:114",
    proposition_text:
      "Operators shall ensure individually identified by: (a) a unique code …",
  });
  const umbrellaUk = effRow({
    id: "u-uk",
    proposition_key: "eq-uk:article-114:p004",
    fragment_locator: "article:114",
    proposition_text:
      "Operators shall ensure individually identified by: (a) a unique code …",
  });

  it("aggregates hidden umbrella rows by explorer section cluster (instrument + provision)", () => {
    const un = [listA, umbrellaEu, umbrellaUk];
    const map = suppressedParentListSummaryCountByArticleCluster(un);
    expect(map.get("__no_source__\u001farticle:114")).toBe(2);
    expect(map.size).toBe(1);
  });
});

describe("articleClusterKeyFromRow", () => {
  it("uses article 114 for frontier fragment locators", () => {
    const r = effRow({
      id: "x",
      fragment_locator: "Article 114(1)(a)",
      proposition_key: "k",
    });
    expect(articleClusterKeyFromRow(r)).toBe("article:114");
  });
});
