import { describe, expect, it } from "vitest";

import {
  buildContextRequirementResolutions,
} from "@/lib/context-locator-resolution";
import {
  buildAssessmentContextViews,
} from "@/lib/review-workbench-views";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import {
  buildInlineLegalReferences,
  buildLegalTextReferences,
  buildStatementTextParts,
  findLocatorTextSpan,
} from "@/lib/statement-inline-references";

const regulationFragments: SourceFragmentRow[] = [
  {
    id: "frag-reg-36",
    source_record_id: "lex-test",
    locator: "regulation:36",
    fragment_text: "Regulation 36.",
  },
  {
    id: "frag-reg-36-p4",
    source_record_id: "lex-test",
    locator: "regulation:36:paragraph:4",
    fragment_text: "Regulation 36(4) nitrogen calculation.",
  },
];

const scheduleThreeFragments: SourceFragmentRow[] = [
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

const hostPropositionById = new Map<string, PropositionRow>([
  [
    "prop:host",
    {
      id: "prop:host",
      source_record_id: "lex-test",
      fragment_locator: "regulation:36",
    },
  ],
]);

function assessmentContextFor(
  statement: LawStatementRow,
  sourceFragments: SourceFragmentRow[],
  propositionById: Map<string, PropositionRow> = hostPropositionById,
) {
  const fragmentById = new Map(sourceFragments.map((fragment) => [String(fragment.id), fragment]));
  return buildAssessmentContextViews(
    buildContextRequirementResolutions(statement, {
      sourceFragments,
      propositionById,
      fragmentById,
    }),
  );
}

describe("statement-inline-references", () => {
  it("finds regulation 36(4) and Schedule 3 spans in statement text", () => {
    const statementText =
      "The occupier must assess nitrogen in accordance with regulation 36(4) and Schedule 3.";
    expect(findLocatorTextSpan(statementText, "regulation 36(4)")?.label).toBe("regulation 36(4)");
    expect(findLocatorTextSpan(statementText, "Schedule 3")?.label).toBe("Schedule 3");
  });

  it("renders Schedule 3 as a resolved container reference", () => {
    const statement: LawStatementRow = {
      id: "stmt-schedule-3",
      statement_text:
        "Records must be kept in accordance with regulation 36 and Schedule 3 where applicable.",
      presentation_role: "requirement",
      standalone_status: "partially_resolved",
      confidence: "medium",
      source_proposition_ids: ["prop:host"],
      required_context: [
        { locator: "regulation 36", resolution_status: "unresolved", proposition_ids: [] },
        { locator: "Schedule 3", resolution_status: "unresolved", proposition_ids: [] },
      ],
    };
    const assessmentContext = assessmentContextFor(statement, [
      ...regulationFragments,
      ...scheduleThreeFragments,
    ]);
    const references = buildInlineLegalReferences({
      statement,
      assessmentContext,
      propositionById: new Map(),
    });
    const scheduleReference = references.find((reference) => reference.locator === "Schedule 3");
    expect(scheduleReference).toBeDefined();
    expect(scheduleReference?.accent).toBe("resolved_container");
    expect(scheduleReference?.status).toBe("resolved_container");
    expect(scheduleReference?.summary).toContain("2 source fragments");

    const parts = buildStatementTextParts(statement.statement_text, references);
    expect(parts.some((part) => part.kind === "reference" && part.text === "Schedule 3")).toBe(
      true,
    );
  });

  it("links regulation 36(4) to its exact proposition", () => {
    const statement: LawStatementRow = {
      id: "stmt-reg36-4",
      statement_text:
        "The occupier must assess nitrogen in accordance with regulation 36(4) and Schedule 3.",
      presentation_role: "requirement",
      standalone_status: "partially_resolved",
      confidence: "medium",
      source_proposition_ids: ["prop:host"],
      required_context: [
        {
          locator: "regulation 36(4)",
          resolution_status: "resolved",
          proposition_ids: ["prop:reg36-4"],
        },
        { locator: "Schedule 3", resolution_status: "unresolved", proposition_ids: [] },
      ],
    };
    const propositionById = new Map<string, PropositionRow>([
      ...hostPropositionById,
      [
        "prop:reg36-4",
        {
          id: "prop:reg36-4",
          proposition_text: "The occupier must make a record of the nitrogen assessment.",
          source_fragment_id: "frag-reg-36-p4",
        },
      ],
    ]);
    const assessmentContext = assessmentContextFor(
      statement,
      [...regulationFragments, ...scheduleThreeFragments],
      propositionById,
    );
    const references = buildInlineLegalReferences({
      statement,
      assessmentContext,
      propositionById,
    });
    const exactReference = references.find((reference) => reference.locator === "regulation 36(4)");
    expect(exactReference?.accent).toBe("resolved");
    expect(exactReference?.propositionIds).toContain("prop:reg36-4");
    expect(exactReference?.resolutionMode).toBe("exact");
  });

  it("prefers longer overlapping locator spans such as regulation 36(4) over regulation 36", () => {
    const statement: LawStatementRow = {
      id: "stmt-overlap",
      statement_text: "Apply regulation 36(4) before regulation 36 defaults.",
      presentation_role: "requirement",
      standalone_status: "standalone",
      confidence: "high",
      source_proposition_ids: ["prop:host"],
      required_context: [
        { locator: "regulation 36(4)", resolution_status: "unresolved", proposition_ids: [] },
        { locator: "regulation 36", resolution_status: "unresolved", proposition_ids: [] },
      ],
    };
    const references = buildInlineLegalReferences({
      statement,
      assessmentContext: assessmentContextFor(statement, regulationFragments),
      propositionById: new Map(),
    });
    const parts = buildStatementTextParts(statement.statement_text, references);
    const referenceTexts = parts
      .filter((part) => part.kind === "reference")
      .map((part) => part.text);
    expect(referenceTexts).toContain("regulation 36(4)");
    expect(referenceTexts).toContain("regulation 36");
    expect(referenceTexts).not.toContain("regulation 36(4) before regulation 36");
  });

  it("detects paragraph 10 inside a constraint proposition and resolves within regulation context", () => {
    const statement: LawStatementRow = {
      id: "stmt-paragraph-10",
      statement_text: "Example statement.",
      presentation_role: "requirement",
      standalone_status: "partially_resolved",
      confidence: "medium",
      source_proposition_ids: ["prop:host"],
      required_context: [],
    };
    const propositionById = new Map<string, PropositionRow>([
      [
        "prop:constraint",
        {
          id: "prop:constraint",
          proposition_text: "Storage must comply with paragraph 10 requirements.",
          fragment_locator: "regulation:10:paragraph:2",
          source_record_id: "lex-test",
        },
      ],
    ]);
    const sourceFragments: SourceFragmentRow[] = [
      {
        id: "frag-reg-10",
        source_record_id: "lex-test",
        locator: "regulation:10",
        fragment_text: "Regulation 10.",
      },
      {
        id: "frag-reg-10-p10",
        source_record_id: "lex-test",
        locator: "regulation:10:paragraph:10",
        fragment_text: "Regulation 10(10) storage requirements.",
      },
    ];
    const fragmentById = new Map(sourceFragments.map((fragment) => [String(fragment.id), fragment]));
    const references = buildLegalTextReferences({
      source: {
        id: "proposition:prop:constraint",
        text: "Storage must comply with paragraph 10 requirements.",
        structuralContextLocator: "regulation:10:paragraph:2",
      },
      statement,
      assessmentContext: [],
      propositionById,
      sourceFragments,
      fragmentById,
      sourceRecordId: "lex-test",
    });
    const paragraphReference = references.find((reference) =>
      reference.label.toLowerCase().includes("paragraph 10"),
    );
    expect(paragraphReference).toBeDefined();
    expect(paragraphReference?.status).toBe("resolved");
    expect(paragraphReference?.resolvedLocator ?? paragraphReference?.locator).toMatch(
      /regulation.*10/i,
    );
    expect(paragraphReference?.sourceFragmentIds).toContain("frag-reg-10-p10");
  });
});
