import { describe, expect, it } from "vitest";

import {
  corpusCoverageCountsFromPayload,
  corpusReadinessHighlightIndex,
  corpusRowDisplayStatus,
  corpusRowsByEquineLawFamily,
  corpusSourceBucket,
  corpusSourceTitleLine,
  currentEuEquineIdentificationDownstreamCandidates,
  equineLawGroupFromRow,
  equinePortfolioStatusLabel,
  groupCorpusSourcesByBucket,
  isDeveloperFixtureSourceId,
  sourceUniverseClusterEntries,
} from "@/lib/equine-corpus-coverage-utils";

describe("equine corpus coverage utils", () => {
  it("groups fixture rows under developer_fixture only", () => {
    const rows: Record<string, unknown>[] = [
      {
        source_id: "fixture-equine-direct",
        included_in_corpus: true,
        extraction_status: "extracted",
        inclusion_reason: "Ingested as pipeline source for this run.",
      },
      {
        source_id: "sfc-2016-429-base",
        title: "Regulation (EU) 2016/429 on animal health (Animal Health Law)",
        included_in_corpus: false,
        extraction_status: "not_started",
        inclusion_reason: "Discovery candidate only — register and ingest to analyse.",
      },
    ];
    const g = groupCorpusSourcesByBucket(rows);
    expect(g.developer_fixture).toHaveLength(1);
    expect(g.pending_legal).toHaveLength(1);
    expect(corpusSourceBucket(rows[0])).toBe("developer_fixture");
    expect(corpusSourceBucket(rows[1])).toBe("pending_legal");
  });

  it("does not count fixtures as included legal in fallback counts", () => {
    const rows: Record<string, unknown>[] = [
      {
        source_id: "fixture-equine-direct",
        included_in_corpus: true,
        extraction_status: "extracted",
        inclusion_reason: "ingested",
      },
    ];
    const counts = corpusCoverageCountsFromPayload({
      summary: {},
      sourceRows: rows,
      propositionRows: [],
    });
    expect(counts.includedLegalSources).toBe(0);
    expect(counts.developerFixtures).toBe(1);
  });

  it("uses human title for sfc-2016-429-base when metadata exists", () => {
    const row = {
      source_id: "sfc-2016-429-base",
      title: "Regulation (EU) 2016/429 on animal health (Animal Health Law)",
      citation: "EUR 2016/429",
      inclusion_reason: "Discovery candidate only — register and ingest to analyse.",
    };
    const title = corpusSourceTitleLine(row);
    expect(title).toContain("2016/429");
    expect(title).not.toMatch(/^sfc-2016-429-base$/);
  });

  it("labels discovery rows as candidate status", () => {
    const row = {
      source_id: "sfc-2016-429-base",
      extraction_status: "not_started",
      inclusion_reason: "Discovery candidate only — register and ingest to analyse.",
    };
    expect(corpusRowDisplayStatus(row)).toBe("candidate");
  });

  it("readiness highlights guidance-ready only when count positive", () => {
    expect(
      corpusReadinessHighlightIndex({
        pendingLegalCandidates: 3,
        includedLegalSources: 0,
        propositionsTotal: 0,
        propositionsUnreviewed: 0,
        guidanceReadyPropositions: 0,
      })
    ).toBe(1);

    expect(
      corpusReadinessHighlightIndex({
        pendingLegalCandidates: 0,
        includedLegalSources: 2,
        propositionsTotal: 0,
        propositionsUnreviewed: 0,
        guidanceReadyPropositions: 0,
      })
    ).toBe(3);

    expect(
      corpusReadinessHighlightIndex({
        pendingLegalCandidates: 0,
        includedLegalSources: 1,
        propositionsTotal: 4,
        propositionsUnreviewed: 4,
        guidanceReadyPropositions: 0,
      })
    ).toBe(4);

    expect(
      corpusReadinessHighlightIndex({
        pendingLegalCandidates: 0,
        includedLegalSources: 1,
        propositionsTotal: 4,
        propositionsUnreviewed: 0,
        guidanceReadyPropositions: 2,
      })
    ).toBe(5);
  });

  it("isDeveloperFixtureSourceId matches fixture prefix", () => {
    expect(isDeveloperFixtureSourceId("fixture-equidae-synonym")).toBe(true);
    expect(isDeveloperFixtureSourceId("sfc-2016-429-base")).toBe(false);
  });

  it("isolates equine passport grouping helpers", () => {
    const rows: Record<string, unknown>[] = [
      {
        source_id: "sfc-2015-262-eu-implementing",
        equine_law_group: "equine_passport_identification",
      },
      { source_id: "sfc-2019-2035-delegated", equine_law_group: "equine_passport_identification" },
      { source_id: "fixture-equine-direct", equine_law_group: "ahl_core" },
    ];
    const passport = corpusRowsByEquineLawFamily(rows, "equine_passport_identification");
    expect(passport).toHaveLength(2);
    const downstream = currentEuEquineIdentificationDownstreamCandidates(rows);
    expect(downstream.map((r) => r.source_id)).toEqual(["sfc-2019-2035-delegated"]);
  });

  it("labels portfolio posture chips for lineage states", () => {
    expect(equinePortfolioStatusLabel("retained_historical_baseline")).toContain("baseline");
    expect(equinePortfolioStatusLabel("related_fragment:corrigendum_only")).toContain("Corrigendum");
  });

  it("accepts eu_exit_amendments and official_controls discovery families", () => {
    expect(equineLawGroupFromRow({ equine_law_group: "eu_exit_amendments" })).toBe("eu_exit_amendments");
    expect(equineLawGroupFromRow({ equine_law_group: "official_controls" })).toBe("official_controls");
  });

  it("parses source_universe cluster_counts for readiness UI", () => {
    const entries = sourceUniverseClusterEntries({
      cluster_counts: {
        equine_identification_passport: { count: 9, label: "Equine identification / passport" },
        movement_import_trade: { count: 8, label: "Movement / import / trade" },
      },
    });
    expect(entries[0].key).toBe("equine_identification_passport");
    expect(entries[0].count).toBe(9);
  });
});
