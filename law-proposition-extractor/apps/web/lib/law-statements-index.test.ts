import { describe, expect, it } from "vitest";

import {
  assessStatementQuality,
  buildStatementIndexes,
  groupPropositionRefsByInstrument,
  matchesQualityPreset,
  matchesStatementFilters,
  propositionRefsForStatement,
  sortStatements,
  uniqueInstrumentKeysForStatement,
  type LawStatementRow,
} from "@/lib/law-statements-index";

const sampleStatement: LawStatementRow = {
  id: "lawstmt:test",
  statement_text: "Example obligation text.",
  presentation_role: "guidance_matching_candidate",
  standalone_status: "partially_resolved",
  confidence: "medium",
  source_proposition_ids: ["prop:host"],
  supporting_proposition_ids: ["prop:xref"],
  required_context: [
    {
      locator: "regulation 9",
      resolution_status: "ambiguous",
      proposition_ids: ["prop:host", "prop:other"],
    },
  ],
  connector_context: [
    {
      kind: "incorporates_context_from",
      locator: "regulation 4(2)",
      proposition_ids: ["prop:imported"],
      via_proposition_ids: ["prop:xref"],
    },
  ],
};

describe("groupPropositionRefsByInstrument", () => {
  it("groups refs by instrument key while preserving first-seen instrument order", () => {
    const refs = propositionRefsForStatement(sampleStatement);
    const instrumentKeyByPropositionId = new Map<string, string>([
      ["prop:host", "2021/77"],
      ["prop:xref", "2021/77"],
      ["prop:other", "2016/429"],
      ["prop:imported", "2016/429"],
    ]);
    const groups = groupPropositionRefsByInstrument(refs, instrumentKeyByPropositionId);
    expect(groups.map((group) => group.instrumentKey)).toEqual(["2021/77", "2016/429"]);
    expect(groups[0]?.refs.map((ref) => ref.propositionId)).toEqual([
      "prop:host",
      "prop:xref",
      "prop:host",
      "prop:xref",
    ]);
    expect(groups[1]?.refs.map((ref) => ref.propositionId)).toEqual(["prop:other", "prop:imported"]);
  });
});

describe("uniqueInstrumentKeysForStatement", () => {
  it("returns sorted unique instrument keys for a statement", () => {
    const instrumentKeyByPropositionId = new Map<string, string>([
      ["prop:host", "2021/77"],
      ["prop:xref", "2021/77"],
      ["prop:other", "2016/429"],
      ["prop:imported", "2016/429"],
    ]);
    expect(
      uniqueInstrumentKeysForStatement(sampleStatement, instrumentKeyByPropositionId),
    ).toEqual(["2016/429", "2021/77"]);
  });
});

describe("propositionRefsForStatement", () => {
  it("collects proposition ids across composition roles", () => {
    const refs = propositionRefsForStatement(sampleStatement);
    expect(refs.map((ref) => `${ref.role}:${ref.propositionId}`)).toEqual([
      "source:prop:host",
      "supporting:prop:xref",
      "required_context:prop:host",
      "required_context:prop:other",
      "connector:prop:imported",
      "via:prop:xref",
    ]);
  });
});

describe("buildStatementIndexes", () => {
  it("indexes statements by proposition id", () => {
    const { statementsByPropositionId } = buildStatementIndexes([sampleStatement]);
    expect(statementsByPropositionId.get("prop:host")?.map((row) => row.id)).toEqual(["lawstmt:test"]);
    expect(statementsByPropositionId.get("prop:imported")?.map((row) => row.id)).toEqual([
      "lawstmt:test",
    ]);
  });
});

describe("assessStatementQuality", () => {
  it("flags incomplete, context, and high-composition statements", () => {
    const assessment = assessStatementQuality(sampleStatement, { minHighCompositionCount: 3 });
    expect(assessment.uniquePropositionCount).toBe(4);
    expect(assessment.flags).toContain("incomplete_standalone");
    expect(assessment.flags).toContain("ambiguous_context");
    expect(assessment.flags).toContain("high_composition");
    expect(assessment.reviewScore).toBeGreaterThan(0);
  });
});

describe("matchesQualityPreset", () => {
  it("separates needs-review issues from high-composition-only rows", () => {
    const assessment = assessStatementQuality(sampleStatement, { minHighCompositionCount: 3 });
    expect(matchesQualityPreset(assessment, "needs_review")).toBe(true);
    expect(matchesQualityPreset(assessment, "high_composition")).toBe(true);
    expect(matchesQualityPreset(assessment, "unresolved_context")).toBe(true);

    const standaloneOnly: LawStatementRow = {
      ...sampleStatement,
      standalone_status: "standalone",
      warnings: [],
      required_context: [],
      connector_context: [],
      supporting_proposition_ids: [],
      source_proposition_ids: ["prop:only"],
    };
    const compact = assessStatementQuality(standaloneOnly, { minHighCompositionCount: 3 });
    expect(matchesQualityPreset(compact, "needs_review")).toBe(false);
    expect(matchesQualityPreset(compact, "high_composition")).toBe(false);
  });
});

describe("sortStatements", () => {
  it("orders by review score when requested", () => {
    const low: LawStatementRow = {
      ...sampleStatement,
      id: "lawstmt:low",
      standalone_status: "standalone",
      warnings: [],
      required_context: [],
      connector_context: [],
      supporting_proposition_ids: [],
      source_proposition_ids: ["prop:a"],
    };
    const high: LawStatementRow = {
      ...sampleStatement,
      id: "lawstmt:high",
    };
    const qualityById = new Map([
      [low.id, assessStatementQuality(low)],
      [high.id, assessStatementQuality(high)],
    ]);
    const sorted = sortStatements([low, high], "review_priority", qualityById);
    expect(sorted.map((row) => row.id)).toEqual(["lawstmt:high", "lawstmt:low"]);
  });
});

describe("matchesStatementFilters", () => {
  it("filters by proposition-matcher candidate membership and search", () => {
    const propositionMatcherStatementIds = new Set(["lawstmt:test"]);
    const qualityById = new Map([[sampleStatement.id, assessStatementQuality(sampleStatement)]]);
    expect(
      matchesStatementFilters(sampleStatement, {
        search: "",
        presentationRole: "",
        standaloneStatus: "",
        propositionMatcherOnly: true,
        propositionMatcherStatementIds,
        qualityPreset: "",
        minPropositionCount: 1,
        qualityById,
      }),
    ).toBe(true);
    expect(
      matchesStatementFilters(sampleStatement, {
        search: "obligation",
        presentationRole: "guidance_matching_candidate",
        standaloneStatus: "partially_resolved",
        propositionMatcherOnly: false,
        propositionMatcherStatementIds,
        qualityPreset: "",
        minPropositionCount: 1,
        qualityById,
      }),
    ).toBe(true);
    expect(
      matchesStatementFilters(sampleStatement, {
        search: "",
        presentationRole: "",
        standaloneStatus: "",
        propositionMatcherOnly: true,
        propositionMatcherStatementIds: new Set(),
        qualityPreset: "",
        minPropositionCount: 1,
        qualityById,
      }),
    ).toBe(false);
  });
});
