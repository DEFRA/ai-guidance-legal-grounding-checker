import { describe, expect, it } from "vitest";

import {
  classifyWorkbenchPropositions,
  formatMainPropositionRoleSummary,
  groupMainPropositionsByRole,
} from "@/lib/review-workbench-proposition-classification";
import { buildPropositionReviewViews, buildWorkbenchComposition } from "@/lib/review-workbench-views";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";

describe("review-workbench-proposition-classification", () => {
  it("formats role summary chips for reviewer-facing statement header", () => {
    expect(
      formatMainPropositionRoleSummary({
        core: 1,
        constraint: 2,
        definition: 70,
        exception: 0,
        supporting: 0,
      }),
    ).toBe("1 core • 2 constraints • 70 definitions");
  });

  it("classifies propositions from composition trace roles", () => {
    const statement: LawStatementRow = {
      id: "stmt-roles",
      statement_text: "Core text with definitions.",
      presentation_role: "requirement",
      standalone_status: "standalone",
      confidence: "high",
      source_proposition_ids: ["p-core"],
      supporting_proposition_ids: ["p-support"],
      composition_trace: [
        {
          order: 0,
          text: "Core text",
          start: 0,
          end: 9,
          role: "core_proposition",
          proposition_ids: ["p-core"],
          context_locators: [],
          source_fragment_ids: ["frag-1"],
          source_locators: ["Reg 1"],
          support_status: "supported",
          incorporation: {
            included_in_text: true,
            external_context: false,
            should_inline: false,
            should_split: false,
            reviewer_required: false,
          },
        },
        {
          order: 1,
          text: "with definitions.",
          start: 10,
          end: 27,
          role: "definition",
          proposition_ids: ["p-def-1", "p-def-2"],
          context_locators: [],
          source_fragment_ids: [],
          source_locators: [],
          support_status: "supported",
          incorporation: {
            included_in_text: true,
            external_context: false,
            should_inline: false,
            should_split: false,
            reviewer_required: false,
          },
        },
        {
          order: 2,
          text: "",
          start: 27,
          end: 27,
          role: "constraint",
          proposition_ids: ["p-constraint"],
          context_locators: [],
          source_fragment_ids: [],
          source_locators: [],
          support_status: "supported",
          incorporation: {
            included_in_text: false,
            external_context: true,
            should_inline: false,
            should_split: false,
            reviewer_required: false,
          },
        },
        {
          order: 3,
          text: "",
          start: 27,
          end: 27,
          role: "supporting_proposition",
          proposition_ids: ["p-support"],
          context_locators: [],
          source_fragment_ids: [],
          source_locators: [],
          support_status: "supported",
          incorporation: {
            included_in_text: true,
            external_context: false,
            should_inline: false,
            should_split: false,
            reviewer_required: false,
          },
        },
      ],
    };

    const propositionById = new Map<string, PropositionRow>([
      ["p-core", { id: "p-core", proposition_text: "Core proposition." }],
      ["p-constraint", { id: "p-constraint", proposition_text: "Constraint proposition." }],
      ["p-def-1", { id: "p-def-1", proposition_text: "Definition one." }],
      ["p-def-2", { id: "p-def-2", proposition_text: "Definition two." }],
      ["p-support", { id: "p-support", proposition_text: "Supporting proposition." }],
    ]);

    const composition = buildWorkbenchComposition(statement, {
      propositionById,
      sourceById: new Map(),
      fragmentById: new Map(),
    });
    const propositions = buildPropositionReviewViews(
      statement,
      composition.recipe,
      propositionById,
      new Map(),
    );

    const result = classifyWorkbenchPropositions({
      statement,
      propositions,
      compositionSourcePropositionIds: composition.compositionSources.map(
        (source) => source.propositionId,
      ),
      context: {
        propositionById,
        sourceById: new Map(),
        fragmentById: new Map(),
      },
    });

    expect(result.main).toHaveLength(4);
    expect(result.supporting).toHaveLength(1);
    expect(formatMainPropositionRoleSummary(result.mainRoleCounts)).toBe(
      "1 core • 1 constraint • 2 definitions",
    );
    expect(groupMainPropositionsByRole(result.main).map((group) => group.role)).toEqual([
      "core",
      "constraint",
      "definition",
    ]);
  });

  it("prefers higher-priority trace roles when a proposition appears in multiple spans", () => {
    const statement: LawStatementRow = {
      id: "stmt-priority",
      statement_text: "Mixed.",
      presentation_role: "requirement",
      standalone_status: "standalone",
      confidence: "high",
      source_proposition_ids: ["p1"],
      composition_trace: [
        {
          order: 0,
          text: "Mixed.",
          start: 0,
          end: 5,
          role: "supporting_proposition",
          proposition_ids: ["p1"],
          context_locators: [],
          source_fragment_ids: [],
          source_locators: [],
          support_status: "supported",
          incorporation: {
            included_in_text: true,
            external_context: false,
            should_inline: false,
            should_split: false,
            reviewer_required: false,
          },
        },
        {
          order: 1,
          text: "Mixed.",
          start: 0,
          end: 5,
          role: "core_proposition",
          proposition_ids: ["p1"],
          context_locators: [],
          source_fragment_ids: [],
          source_locators: [],
          support_status: "supported",
          incorporation: {
            included_in_text: true,
            external_context: false,
            should_inline: false,
            should_split: false,
            reviewer_required: false,
          },
        },
      ],
    };

    const propositionById = new Map<string, PropositionRow>([
      ["p1", { id: "p1", proposition_text: "Primary proposition." }],
    ]);
    const composition = buildWorkbenchComposition(statement, {
      propositionById,
      sourceById: new Map(),
      fragmentById: new Map(),
    });

    const result = classifyWorkbenchPropositions({
      statement,
      propositions: composition.propositions,
      context: {
        propositionById,
        sourceById: new Map(),
        fragmentById: new Map(),
      },
    });

    expect(result.classified[0]?.role).toBe("core");
  });
});
