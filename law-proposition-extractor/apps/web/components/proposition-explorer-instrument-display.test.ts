import { describe, expect, it } from "vitest";

import {
  explorerSectionClusterKeyFromRow,
  formatExplorerSectionHeading,
  shortInstrumentLabel,
  type UnknownRecord,
} from "./proposition-explorer-helpers";

function effRow(oa: UnknownRecord): UnknownRecord {
  return { original_artifact: oa, effective_status: "generated" };
}

describe("shortInstrumentLabel / explorer section headings (multi-source polish)", () => {
  const src262: UnknownRecord = {
    id: "sr-262",
    jurisdiction: "EU",
    title:
      "Commission Implementing Regulation (EU) 2015/262 of 17 February 2015 laying down rules pursuant to Council Directive …",
    citation: "(EU) 2015/262",
    metadata: { instrument_id: "EU 2015/262" },
  };

  const catalog = [src262];

  it("2015/262 source renders curated short label", () => {
    expect(shortInstrumentLabel(src262)).toBe("2015/262 — Equine Passport Regulation");
  });

  it("unknown source falls back safely to stable id-based label", () => {
    expect(shortInstrumentLabel(undefined)).toBe("");
    expect(shortInstrumentLabel({ id: "orphan-record-uuid" } as UnknownRecord)).toBe(
      "orphan-record-uuid",
    );
  });

  it("section heading exposes short instrument line + Article 1 while keeping rich official strings", () => {
    const row = effRow({
      id: "p1",
      source_record_id: "sr-262",
      fragment_locator: "article:1",
      proposition_text: "x",
    });
    const clusterKey = explorerSectionClusterKeyFromRow(row, catalog);
    const h = formatExplorerSectionHeading(clusterKey, catalog, [row]);
    expect(h.primaryInstrumentLine).toBe("2015/262 — Equine Passport Regulation");
    expect(h.provisionLine).toMatch(/^Article\s+1\b/);
    expect(h.headlineCompact).toContain("2015/262 — Equine Passport Regulation · Article");
    expect(h.metadataLine.toLowerCase()).toContain("jurisdiction:");
    expect(h.metadataLine.toLowerCase()).toContain("source rows:");
    expect(h.fullOfficialInstrumentTitle.length).toBeGreaterThan(30);
    expect(h.fullOfficialInstrumentTitle.toLowerCase()).toContain("2015/262");
    expect(h.fullTitleTooltip.toLowerCase()).toContain("2015/262");
  });
});
