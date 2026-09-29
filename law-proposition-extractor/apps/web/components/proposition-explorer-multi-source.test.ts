import { describe, expect, it } from "vitest";

import {
  buildArticleSectionsGrouped,
  compactPropositionSourceSummaryLines,
  explorerSectionClusterKeyFromRow,
  groupKeyForPropositionRow,
  sourceDocumentFilterLabel,
  sourceDocumentFilterOptionTitle,
  type UnknownRecord,
} from "./proposition-explorer-helpers";

function effRow(oa: UnknownRecord): UnknownRecord {
  return { original_artifact: oa, effective_status: "generated" };
}

const src2016eu: UnknownRecord = {
  id: "sr-eu-429",
  jurisdiction: "EU",
  title: "Regulation (EU) 2016/429 — Article 1",
  citation: "32016R0429",
  metadata: { instrument_id: "EU 2016/429" },
};
const src2016uk: UnknownRecord = {
  id: "sr-uk-429",
  jurisdiction: "UK",
  title: "Regulation (EU) 2016/429 (retained on legislation.gov.uk) — Article 1",
  citation: "Retained EU Reg 2016/429 (UK) Art 1",
  metadata: { instrument_id: "EU 2016/429" },
};
const src2015eu: UnknownRecord = {
  id: "sr-eu-262",
  jurisdiction: "EU",
  title: "Commission Implementing Regulation (EU) 2015/262 — Article 1",
  citation: "(EU) 2015/262",
  metadata: { instrument_id: "EU 2015/262" },
};

const catalog: UnknownRecord[] = [src2016eu, src2016uk, src2015eu];

describe("multi-source corpus navigation helpers", () => {
  it("separates Article 1 sections by instrument family", () => {
    const r429 = effRow({
      id: "p-429-1",
      source_record_id: "sr-eu-429",
      proposition_key: "k1",
      fragment_locator: "article:1",
      proposition_text: "foo",
    });
    const r262 = effRow({
      id: "p-262-1",
      source_record_id: "sr-eu-262",
      proposition_key: "k2",
      fragment_locator: "article:1",
      proposition_text: "bar",
    });
    expect(explorerSectionClusterKeyFromRow(r429, catalog)).not.toBe(
      explorerSectionClusterKeyFromRow(r262, catalog)
    );
  });

  it("keeps EU/UK parallels in the same section for one instrument + provision", () => {
    const eu = effRow({
      id: "e109",
      source_record_id: "sr-eu-429",
      fragment_locator: "article:109:list:1-d-i",
      proposition_text: "Member States shall record …",
    });
    const uk = effRow({
      id: "u109",
      source_record_id: "sr-uk-429",
      fragment_locator: "article-109-1-d-i",
      proposition_text: "Member States shall record …",
    });
    expect(groupKeyForPropositionRow(eu, catalog)).toBe(groupKeyForPropositionRow(uk, catalog));
    expect(explorerSectionClusterKeyFromRow(eu, catalog)).toBe(
      explorerSectionClusterKeyFromRow(uk, catalog)
    );
  });

  it("EU/UK rows with identical proposition text still produce two distinct source summary lines", () => {
    const eu = effRow({
      id: "e-same",
      source_record_id: "sr-eu-429",
      fragment_locator: "article:10",
      proposition_text: "Member States shall record …",
    });
    const uk = effRow({
      id: "u-same",
      source_record_id: "sr-uk-429",
      fragment_locator: "article:10",
      proposition_text: "Member States shall record …",
    });
    const lines = compactPropositionSourceSummaryLines([eu, uk], catalog);
    expect(lines).toHaveLength(2);
    expect(lines.some((l) => l.includes("🇪🇺"))).toBe(true);
    expect(lines.some((l) => l.includes("🇬🇧"))).toBe(true);
  });

  it("source-document group filter keeps all rows in touching lineage groups", () => {
    const eu = effRow({
      id: "e109",
      source_record_id: "sr-eu-429",
      fragment_locator: "article:109:list:1-d-i",
      proposition_text: "x",
    });
    const uk = effRow({
      id: "u109",
      source_record_id: "sr-uk-429",
      fragment_locator: "article-109-1-d-i",
      proposition_text: "x",
    });
    const rows = [eu, uk];
    const sel = "sr-eu-429";
    const touch = new Set<string>();
    for (const row of rows) {
      const oa = row.original_artifact as UnknownRecord;
      if (String(oa.source_record_id ?? "").trim() === sel) {
        touch.add(groupKeyForPropositionRow(row, catalog));
      }
    }
    const filtered = rows.filter((row) => touch.has(groupKeyForPropositionRow(row, catalog)));
    expect(filtered).toHaveLength(2);
  });

  it("collapsed card source summary includes instrument-facing title", () => {
    const eu = effRow({
      id: "e1",
      source_record_id: "sr-eu-429",
      fragment_locator: "article:1",
      proposition_text: "x",
    });
    const lines = compactPropositionSourceSummaryLines([eu], catalog);
    expect(lines.length).toBeGreaterThan(0);
    expect(lines.some((l) => /2016|429|Regulation/i.test(l))).toBe(true);
  });

  it("falls back to muted source_record_id when catalog misses the source", () => {
    const row = effRow({
      id: "lonely",
      source_record_id: "not-in-catalog-xyz",
      fragment_locator: "article:2",
      proposition_text: "z",
    });
    const lines = compactPropositionSourceSummaryLines([row], catalog);
    expect(lines.join("\n")).toContain("not-in-catalog-xyz");
  });

  it("source document filter label uses short instrument text and EU flag (full title in option title only)", () => {
    const titleById = new Map([
      ["sr-eu-429", "Regulation (EU) 2016/429 — Article 1"],
    ]);
    const label = sourceDocumentFilterLabel("sr-eu-429", catalog, titleById);
    expect(label).toContain("🇪🇺");
    expect(label).not.toMatch(/laying down/i);
    expect(label).toMatch(/2016\/429/);
    expect(sourceDocumentFilterOptionTitle("sr-eu-429", catalog, titleById)).toContain(
      "Regulation (EU) 2016/429"
    );
  });

  it("buildArticleSectionsGrouped buckets by instrument+provision", () => {
    const g1 = {
      key: "gk1",
      rows: [
        effRow({
          id: "a",
          source_record_id: "sr-eu-429",
          fragment_locator: "article:1",
          proposition_text: "p",
        }),
      ],
    };
    const g2 = {
      key: "gk2",
      rows: [
        effRow({
          id: "b",
          source_record_id: "sr-eu-262",
          fragment_locator: "article:1",
          proposition_text: "q",
        }),
      ],
    };
    const sections = buildArticleSectionsGrouped([g1, g2], catalog);
    expect(sections).toHaveLength(2);
  });
});
