import { describe, expect, it } from "vitest";

import {
  articleClusterKeyFromRow,
  buildArticleSectionsGrouped,
  partitionPropositionGroupsByArticleCluster,
  type UnknownRecord,
} from "./proposition-explorer-helpers";

function rowForArticle(articleRef: string, id: string, pk: string): UnknownRecord {
  return {
    effective_status: "generated",
    original_artifact: {
      id,
      proposition_key: pk,
      source_record_id: "src-1",
      article_reference: articleRef,
      fragment_locator: "full",
    },
  };
}

describe("partitionPropositionGroupsByArticleCluster", () => {
  it("keeps a single subgroup when all rows share one article cluster", () => {
    const groups = [
      {
        key: "same-lineage",
        rows: [
          rowForArticle("Article 4", "eu", "same-lineage"),
          rowForArticle("Article 4", "uk", "same-lineage"),
        ],
      },
    ];
    const out = partitionPropositionGroupsByArticleCluster(groups);
    expect(out).toHaveLength(1);
    expect(out[0]!.key).toBe("same-lineage");
    expect(out[0]!.rows).toHaveLength(2);
  });

  it("splits mixed-article lineage into one subgroup per cluster (stable subgroup keys)", () => {
    const groups = [
      {
        key: "same-lineage",
        rows: [
          rowForArticle("Article 4", "a", "same-lineage"),
          rowForArticle("Article 5", "b", "same-lineage"),
        ],
      },
    ];
    const out = partitionPropositionGroupsByArticleCluster(groups);
    expect(out).toHaveLength(2);
    expect(out.every((g) => g.rows.length === 1)).toBe(true);
    const clusters = out.map((g) => articleClusterKeyFromRow(g.rows[0]!)).sort();
    expect(clusters).toEqual(["article:4", "article:5"]);
    expect(out[0]!.key).not.toBe(out[1]!.key);
  });

  it("skips empty lineage groups", () => {
    expect(partitionPropositionGroupsByArticleCluster([{ key: "x", rows: [] }])).toEqual([]);
  });
});

describe("buildArticleSectionsGrouped", () => {
  it("drops sections that would contain only empty groups", () => {
    const sorted = [{ key: "only-empty", rows: [] as UnknownRecord[] }];
    expect(buildArticleSectionsGrouped(sorted, [])).toEqual([]);
  });

  it("after filtering removes all rows in article 4, no article:4 section is emitted", () => {
    const mixedLineageKey = "shared-pk";
    const fullGroup = partitionPropositionGroupsByArticleCluster([
      {
        key: mixedLineageKey,
        rows: [
          rowForArticle("Article 4", "p4", mixedLineageKey),
          rowForArticle("Article 5", "p5", mixedLineageKey),
        ],
      },
    ]);
    const art5Only = fullGroup.filter(
      (g) => articleClusterKeyFromRow(g.rows[0]!) === "article:5"
    );
    const sorted = [...art5Only].sort((a, b) =>
      articleClusterKeyFromRow(a.rows[0]!).localeCompare(articleClusterKeyFromRow(b.rows[0]!))
    );
    const sections = buildArticleSectionsGrouped(sorted, []);
    const clusterKeys = sections.map((s) => s.clusterKey);
    expect(clusterKeys).not.toContain("article:4");
    const art5Section = "__src:src-1\u001farticle:5";
    expect(clusterKeys).toContain(art5Section);
    expect(
      sections.find((s) => s.clusterKey === art5Section)?.groups.every((g) => g.rows.length > 0)
    ).toBe(true);
  });
});
