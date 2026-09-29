import { describe, expect, it } from "vitest";

import {
  applyStructuralContextToReference,
  buildContextRequirementResolutions,
  buildLocatorResolutionReport,
  locatorMatchesTarget,
  normalizeCrossReferenceLocator,
  parseContainerLocatorTargets,
  parseLocatorReference,
  parseLocatorStructuralContext,
  resolveContextRequirement,
  resolveLocatorTargets,
} from "@/lib/context-locator-resolution";
import { assessmentContextStatus } from "@/lib/review-workbench-views";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import {
  WSI_2021_77_SOURCE_RECORD_ID,
  wsi202177Regulation36Fragments,
} from "@/lib/wsi-2021-77-regulation-36-fragments";

const scheduleOneFragments: SourceFragmentRow[] = [
  {
    id: "frag-schedule-1-p2",
    source_record_id: "lex-test",
    locator: "schedule:1:paragraph:2",
    fragment_text: "Schedule 1 paragraph 2.",
  },
  {
    id: "frag-schedule-1-p3",
    source_record_id: "lex-test",
    locator: "schedule:1:paragraph:3",
    fragment_text: "Schedule 1 paragraph 3.",
  },
  {
    id: "frag-schedule-1-p4",
    source_record_id: "lex-test",
    locator: "schedule:1:paragraph:4",
    fragment_text: "Schedule 1 paragraph 4.",
  },
  {
    id: "frag-schedule-1-p5",
    source_record_id: "lex-test",
    locator: "schedule:1:paragraph:5",
    fragment_text: "Schedule 1 paragraph 5.",
  },
  {
    id: "frag-schedule-1-p7a",
    source_record_id: "lex-test",
    locator: "schedule:1:paragraph:7(a)",
    fragment_text: "Schedule 1 paragraph 7(a).",
  },
  {
    id: "frag-schedule-1-p8",
    source_record_id: "lex-test",
    locator: "schedule:1:paragraph:8",
    fragment_text: "Schedule 1 paragraph 8.",
  },
  {
    id: "frag-schedule-1-p9",
    source_record_id: "lex-test",
    locator: "schedule:1:paragraph:9",
    fragment_text: "Schedule 1 paragraph 9.",
  },
  {
    id: "frag-schedule-2-p9",
    source_record_id: "lex-test",
    locator: "schedule:2:paragraph:9",
    fragment_text: "Schedule 2 paragraph 9.",
  },
];

const regulationFragments: SourceFragmentRow[] = [
  {
    id: "frag-reg-36",
    source_record_id: "lex-test",
    locator: "regulation:36",
    fragment_text: "Regulation 36.",
  },
  {
    id: "frag-reg-36-p1",
    source_record_id: "lex-test",
    locator: "regulation:36:paragraph:1",
    fragment_text: "Regulation 36(1).",
  },
];

function scheduleOneContext() {
  return parseLocatorStructuralContext("schedule:1:paragraph:8");
}

function regulationContext() {
  return parseLocatorStructuralContext("regulation:36");
}

describe("context-locator-resolution", () => {
  it("normalises colon and spaced locators consistently", () => {
    expect(normalizeCrossReferenceLocator("schedule:1")).toBe("schedule 1");
    expect(normalizeCrossReferenceLocator("Schedule 1")).toBe("schedule 1");
    expect(normalizeCrossReferenceLocator("regulation:19")).toBe("regulation 19");
    expect(normalizeCrossReferenceLocator("schedule:2:paragraph:1")).toBe("schedule 2(1)");
    expect(normalizeCrossReferenceLocator("schedule:1:paragraph:7")).toBe("schedule 1(7)");
    expect(normalizeCrossReferenceLocator("Schedule 1, paragraph 7")).toBe("schedule 1(7)");
    expect(normalizeCrossReferenceLocator("schedule 1 paragraph 7")).toBe("schedule 1(7)");
    expect(normalizeCrossReferenceLocator("para 7(a)")).toBe("paragraph 7(a)");
  });

  it("parses locator references including ranges and sub-paragraphs", () => {
    expect(parseLocatorReference("paragraph 9")?.kind).toBe("single");
    expect(parseLocatorReference("paragraph 7(a)")?.kind).toBe("single");
    expect(parseLocatorReference("paragraphs 2 to 5")?.kind).toBe("range");
    expect(parseLocatorReference("paragraphs 2–5")?.kind).toBe("range");
    expect(parseLocatorReference("sub-paragraph (1)")?.kind).toBe("single");
    expect(parseLocatorReference("regulation 36(1)")?.kind).toBe("single");
    expect(parseLocatorReference("Schedule 1, paragraph 7(a)")?.kind).toBe("single");
    expect(parseLocatorReference("1999")).toBeNull();
  });

  it("matches fragment locators to human-readable targets", () => {
    expect(locatorMatchesTarget("schedule:1", "schedule 1")).toBe(true);
    expect(locatorMatchesTarget("regulation:19", "regulation 19")).toBe(true);
    expect(locatorMatchesTarget("schedule:2:paragraph:1", "schedule 2")).toBe(true);
    expect(locatorMatchesTarget("schedule:2:paragraph:1", "schedule 2(1)")).toBe(true);
    expect(locatorMatchesTarget("schedule:1:paragraph:9", "schedule 1(9)")).toBe(true);
    expect(locatorMatchesTarget("schedule:1:paragraph:7(a)", "schedule 1(7(a))")).toBe(true);
    expect(locatorMatchesTarget("schedule:3", "schedule 1")).toBe(false);
  });

  it("resolves paragraph 9 relative to Schedule 1, paragraph 8", () => {
    const resolution = resolveContextRequirement(
      {
        kind: "referenced_locator",
        locator: "paragraph 9",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: scheduleOneContext(),
        sourceFragments: scheduleOneFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.inheritedContextLabel).toBe("resolved within Schedule 1");
    expect(resolution.fragments).toHaveLength(1);
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-schedule-1-p9");
  });

  it("resolves paragraph 7(a) relative to Schedule 1, paragraph 8", () => {
    const resolution = resolveContextRequirement(
      {
        locator: "paragraph 7(a)",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: scheduleOneContext(),
        sourceFragments: scheduleOneFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-schedule-1-p7a");
  });

  it("expands paragraphs 2 to 5 relative to Schedule 1, paragraph 8", () => {
    const resolution = resolveContextRequirement(
      {
        locator: "paragraphs 2 to 5",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: scheduleOneContext(),
        sourceFragments: scheduleOneFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.children).toHaveLength(4);
    expect(resolution.children?.map((child) => child.locator)).toEqual([
      "schedule 1(2)",
      "schedule 1(3)",
      "schedule 1(4)",
      "schedule 1(5)",
    ]);
    expect(resolution.children?.every((child) => child.resolved)).toBe(true);
    expect(resolution.fragments).toHaveLength(4);
  });

  it("resolves sub-paragraph (1) relative to regulation 36", () => {
    const resolution = resolveContextRequirement(
      {
        locator: "sub-paragraph (1)",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: regulationContext(),
        sourceFragments: regulationFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-reg-36-p1");
  });

  it("resolves paragraph (1) relative to regulation 36", () => {
    const resolution = resolveContextRequirement(
      {
        locator: "paragraph (1)",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: regulationContext(),
        sourceFragments: regulationFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-reg-36-p1");
  });

  it("marks bare paragraph 9 as ambiguous when no schedule context exists", () => {
    const resolution = resolveContextRequirement(
      {
        locator: "paragraph 9",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: { segments: [] },
        sourceFragments: scheduleOneFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(false);
    expect(resolution.reason).toBe("ambiguous");
    expect(resolution.fragments).toHaveLength(2);
  });

  it("returns external reference without attempting internal resolution", () => {
    const resolution = resolveContextRequirement(
      {
        kind: "external_standard_reference",
        locator: "BS 5502: Part 50:1993, paragraph 7.",
        resolution_status: "external_reference",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: scheduleOneContext(),
        sourceFragments: scheduleOneFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(false);
    expect(resolution.reason).toBe("external reference");
    expect(resolution.fragments).toHaveLength(0);
  });

  it("resolves same-instrument locators from source fragments", () => {
    const sourceFragments: SourceFragmentRow[] = [
      {
        id: "frag-schedule-1",
        source_record_id: "lex-test",
        locator: "schedule:1",
        fragment_text: "Schedule 1 content.",
      },
      {
        id: "frag-schedule-2-p1",
        source_record_id: "lex-test",
        locator: "schedule:2:paragraph:1",
        fragment_text: "Schedule 2 paragraph 1.",
      },
    ];
    const resolution = resolveContextRequirement(
      {
        kind: "referenced_locator",
        locator: "schedule 1",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: scheduleOneContext(),
        sourceFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.fragments).toHaveLength(1);
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-schedule-1");
  });

  it("resolves schedule 3 as a container when child part fragments match", () => {
    const sourceFragments: SourceFragmentRow[] = [
      {
        id: "frag-schedule-3-part-1",
        source_record_id: "lex-test",
        locator: "schedule:3:part:1",
        fragment_text: "Schedule 3, Part 1.",
      },
      {
        id: "frag-schedule-3-part-2",
        source_record_id: "lex-test",
        locator: "schedule:3:part:2",
        fragment_text: "Schedule 3, Part 2.",
      },
    ];
    const resolution = resolveContextRequirement(
      {
        locator: "Schedule 3",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: scheduleOneContext(),
        sourceFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.resolutionMode).toBe("container");
    expect(assessmentContextStatus(resolution)).toBe("resolved_container");
    expect(resolution.children).toHaveLength(2);
    expect(resolution.children?.map((child) => child.locator)).toEqual([
      "Schedule 3, Part 1",
      "Schedule 3, Part 2",
    ]);
    expect(resolution.fragments).toHaveLength(2);
  });

  it("expands Parts 1 and 2 of Schedule 3 into grouped container children", () => {
    const sourceFragments: SourceFragmentRow[] = [
      {
        id: "frag-schedule-3-part-1",
        source_record_id: "lex-test",
        locator: "schedule:3:part:1",
        fragment_text: "Schedule 3, Part 1.",
      },
      {
        id: "frag-schedule-3-part-2",
        source_record_id: "lex-test",
        locator: "schedule:3:part:2",
        fragment_text: "Schedule 3, Part 2.",
      },
    ];
    expect(parseContainerLocatorTargets("Parts 1 and 2 of Schedule 3")?.map((target) => target.display)).toEqual([
      "Schedule 3, Part 1",
      "Schedule 3, Part 2",
    ]);
    const resolution = resolveContextRequirement(
      {
        locator: "Parts 1 and 2 of Schedule 3",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: scheduleOneContext(),
        sourceFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.resolutionMode).toBe("container");
    expect(assessmentContextStatus(resolution)).toBe("resolved_container");
    expect(resolution.children).toHaveLength(2);
    expect(resolution.children?.every((child) => child.resolved)).toBe(true);
    expect(resolution.children?.map((child) => child.locator)).toEqual([
      "Schedule 3, Part 1",
      "Schedule 3, Part 2",
    ]);
  });

  it("groups multiple descendant fragments under a container locator", () => {
    const sourceFragments: SourceFragmentRow[] = [
      {
        id: "frag-schedule-2",
        source_record_id: "lex-test",
        locator: "schedule:2",
        fragment_text: "Whole schedule 2.",
      },
      {
        id: "frag-schedule-2-p1",
        source_record_id: "lex-test",
        locator: "schedule:2:paragraph:1",
        fragment_text: "Schedule 2 paragraph 1.",
      },
    ];
    const resolution = resolveContextRequirement(
      {
        locator: "schedule 2",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: scheduleOneContext(),
        sourceFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.resolutionMode).toBe("container");
    expect(assessmentContextStatus(resolution)).toBe("resolved_container");
    expect(resolution.children).toHaveLength(2);
    expect(resolution.fragments).toHaveLength(2);
  });

  it("builds resolutions for all required context entries on a statement", () => {
    const statement: LawStatementRow = {
      id: "lawstmt:test",
      statement_text: "Example statement.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "partially_resolved",
      confidence: "medium",
      source_proposition_ids: ["prop:host"],
      required_context: [
        {
          locator: "paragraph 9",
          resolution_status: "unresolved",
          proposition_ids: [],
        },
        {
          kind: "external_standard_reference",
          locator: "BS 5502",
          resolution_status: "external_reference",
          proposition_ids: [],
        },
      ],
    };
    const propositionById = new Map<string, PropositionRow>([
      [
        "prop:host",
        {
          id: "prop:host",
          source_record_id: "lex-test",
          fragment_locator: "schedule:1:paragraph:8",
        },
      ],
    ]);
    const resolutions = buildContextRequirementResolutions(statement, {
      sourceFragments: scheduleOneFragments,
      propositionById,
      fragmentById: new Map(),
    });
    expect(resolutions).toHaveLength(2);
    expect(resolutions[0]?.resolved).toBe(true);
    expect(resolutions[0]?.inheritedContextLabel).toBe("resolved within Schedule 1");
    expect(resolutions[1]?.reason).toBe("external reference");
  });

  it("prefers paragraph child over parent when both regulation fragments exist", () => {
    const sourceFragments: SourceFragmentRow[] = [
      ...regulationFragments,
      {
        id: "frag-reg-36-p4",
        source_record_id: "lex-test",
        locator: "regulation:36:paragraph:4",
        fragment_text: "Regulation 36(4) nitrogen calculation.",
      },
    ];
    const resolution = resolveContextRequirement(
      {
        locator: "regulation 36(4)",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: regulationContext(),
        sourceFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.resolutionMode).toBe("exact");
    expect(resolution.exportResolutionStatus).not.toBe("partially_resolved");
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-reg-36-p4");
    expect(resolution.fragments[0]?.locator).toBe("regulation:36:paragraph:4");
  });

  it("resolves regulation 36(4) exactly against refreshed WSI 2021/77 fragments", () => {
    const resolution = resolveContextRequirement(
      {
        locator: "regulation 36(4)",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: WSI_2021_77_SOURCE_RECORD_ID,
        structuralContext: regulationContext(),
        sourceFragments: wsi202177Regulation36Fragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.resolutionMode).toBe("exact");
    expect(resolution.exportResolutionStatus).not.toBe("partially_resolved");
    expect(resolution.fragments[0]?.locator).toBe("regulation:36:paragraph:4");
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-wsi77-reg-36-p4");
  });

  it("resolves regulation 36(4) exactly when a paragraph-level fragment exists", () => {
    const sourceFragments: SourceFragmentRow[] = [
      {
        id: "frag-reg-36-p4",
        source_record_id: "lex-test",
        locator: "regulation:36:paragraph:4",
        fragment_text: "Regulation 36(4) nitrogen calculation.",
      },
    ];
    const resolution = resolveContextRequirement(
      {
        locator: "regulation 36(4)",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: regulationContext(),
        sourceFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.resolutionMode).toBe("exact");
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-reg-36-p4");
    expect(locatorMatchesTarget("regulation:36:paragraph:4", "regulation 36(4)")).toBe(true);
  });

  it("partially resolves regulation 36(4) to regulation 36 when only parent fragment exists", () => {
    const resolution = resolveContextRequirement(
      {
        locator: "regulation 36(4)",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: regulationContext(),
        sourceFragments: regulationFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.exportResolutionStatus).toBe("partially_resolved");
    expect(resolution.resolutionMode).toBe("partial");
    expect(resolution.resolvedLocator).toBe("regulation 36");
    expect(resolution.unresolvedChild).toBe("paragraph (4)");
    expect(resolution.fragments[0]?.fragmentId).toBe("frag-reg-36");
    expect(assessmentContextStatus(resolution)).toBe("partially_resolved");
  });

  it("treats cross-instrument regulation references as external", () => {
    const resolution = resolveContextRequirement(
      {
        locator: "regulation 4 of the Environmental Permitting (England and Wales) Regulations 2010",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: regulationContext(),
        sourceFragments: regulationFragments,
        propositionById: new Map(),
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(false);
    expect(resolution.reason).toBe("external reference");
    expect(resolution.fragments).toHaveLength(0);
  });

  it("builds a locator resolution report for regulation 36(4)", () => {
    const statement: LawStatementRow = {
      id: "lawstmt:reg36",
      statement_text:
        "The occupier must assess nitrogen in accordance with regulation 36(4) and Schedule 3.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "partially_resolved",
      confidence: "medium",
      source_proposition_ids: ["prop:host"],
      required_context: [
        {
          locator: "regulation 36(4)",
          resolution_status: "unresolved",
          proposition_ids: [],
        },
      ],
    };
    const propositionById = new Map<string, PropositionRow>([
      [
        "prop:host",
        {
          id: "prop:host",
          source_record_id: "lex-test",
          fragment_locator: "schedule:1a:paragraph:18",
        },
      ],
    ]);
    const report = buildLocatorResolutionReport({
      locator: "regulation 36(4)",
      statement,
      sourceFragments: regulationFragments,
      propositionById,
      fragmentById: new Map(),
    });
    expect(report.primarySourceRecordId).toBe("lex-test");
    expect(report.parsedLocator?.kind).toBe("single");
    expect(report.structuralContext?.segments[0]).toEqual({ kind: "schedule", num: "1a" });
    expect(report.candidateFragmentLocators).toContain("regulation:36");
    expect(report.outcome.exportResolutionStatus).toBe("partially_resolved");
    expect(report.outcome.resolvedLocator).toBe("regulation 36");
    expect(report.outcome.unresolvedChild).toBe("paragraph (4)");
    expect(report.outcome.matchedFragmentIds).toContain("frag-reg-36");
  });

  it("inherits schedule context when applying bare paragraph references", () => {
    const contextualised = applyStructuralContextToReference(
      scheduleOneContext()!,
      parseLocatorReference("paragraph 9")!,
    );
    expect(resolveLocatorTargets("paragraph 9", scheduleOneContext())).toEqual(["schedule 1(9)"]);
    expect(contextualised.kind).toBe("single");
    if (contextualised.kind === "single") {
      expect(contextualised.segments).toEqual([
        { kind: "schedule", num: "1" },
        { kind: "paragraph", num: "9", sub: null },
      ]);
    }
  });

  it("resolves nested schedule 1A paragraph 18(1) as a container from paragraph 18(1)(b) context", () => {
    const context = parseLocatorStructuralContext("schedule:1a:paragraph:18(1)(b)");
    expect(context?.segments).toEqual([
      { kind: "schedule", num: "1a" },
      { kind: "paragraph", num: "18", sub: "1)(b" },
    ]);
    expect(normalizeCrossReferenceLocator("schedule:1a:paragraph:18(1)(b)")).toBe("schedule 1a(18(1)(b))");
    expect(locatorMatchesTarget("schedule:1a:paragraph:18(1)(a)", "schedule 1a(18(1))")).toBe(true);
    expect(resolveLocatorTargets("paragraph 18(1)", context)).toEqual(["schedule 1a(18(1))"]);

    const sourceFragments: SourceFragmentRow[] = [
      {
        id: "frag-schedule-1a-p18",
        source_record_id: "lex-test",
        locator: "schedule:1a:paragraph:18",
        fragment_text: "Schedule 1A paragraph 18.",
      },
    ];
    const propositionById = new Map<string, PropositionRow>([
      [
        "prop:18-1a",
        {
          id: "prop:18-1a",
          source_record_id: "lex-test",
          fragment_locator: "schedule:1a:paragraph:18(1)(a)",
        },
      ],
      [
        "prop:18-1b",
        {
          id: "prop:18-1b",
          source_record_id: "lex-test",
          fragment_locator: "schedule:1a:paragraph:18(1)(b)",
        },
      ],
    ]);

    const resolution = resolveContextRequirement(
      {
        locator: "paragraph 18(1)",
        resolution_status: "unresolved",
        proposition_ids: [],
      },
      {
        sourceRecordId: "lex-test",
        structuralContext: context,
        sourceFragments,
        propositionById,
        fragmentById: new Map(),
      },
    );
    expect(resolution.resolved).toBe(true);
    expect(resolution.resolutionMode).toBe("container");
    expect(resolution.fragments.map((fragment) => fragment.locator)).toEqual(
      expect.arrayContaining([
        "schedule:1a:paragraph:18(1)(a)",
        "schedule:1a:paragraph:18(1)(b)",
      ]),
    );
  });
});
