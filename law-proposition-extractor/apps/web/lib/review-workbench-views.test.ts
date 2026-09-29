import { describe, expect, it } from "vitest";

import { buildContextRequirementResolutions } from "@/lib/context-locator-resolution";
import { normalizeExcerptDisplay } from "@/lib/excerpt-display";
import {
  assessmentContextStatus,
  buildAssessmentContextViews,
  buildCompositionSourceViews,
  buildLawFragmentViews,
  buildPropositionReviewViews,
  buildWorkbenchComposition,
  collectWorkbenchDisplayExcerpts,
} from "@/lib/review-workbench-views";
import type { ContextRequirementResolution } from "@/lib/context-locator-resolution";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";

describe("review-workbench-views", () => {
  it("groups law fragments by locator and excerpt", () => {
    const views = buildLawFragmentViews([
      {
        rowId: "r1",
        statement_fragment: "A",
        supporting_proposition_ids: ["p1"],
        proposition_text: "prop one",
        source_locator: "Art 1",
        source_excerpt: "source text",
        support_status: "supported",
      },
      {
        rowId: "r2",
        statement_fragment: "B",
        supporting_proposition_ids: ["p2"],
        proposition_text: "prop two",
        source_locator: "Art 1",
        source_excerpt: "source text",
        support_status: "supported",
      },
    ]);
    expect(views).toHaveLength(1);
    expect(views[0]?.propositionIds).toEqual(["p1", "p2"]);
  });

  it("builds workbench composition from statement refs", () => {
    const statement: LawStatementRow = {
      id: "stmt-1",
      statement_text: "Operators must notify the authority.",
      presentation_role: "requirement",
      standalone_status: "standalone",
      confidence: "high",
      source_proposition_ids: ["p1"],
    };
    const propositionById = new Map<string, PropositionRow>([
      [
        "p1",
        {
          id: "p1",
          proposition_text: "Operators must notify the authority.",
          fragment_locator: "Reg 4(1)",
          source_record_id: "src-1",
          source_fragment_id: "frag-1",
        },
      ],
    ]);
    const composition = buildWorkbenchComposition(statement, {
      propositionById,
      sourceById: new Map([
        [
          "src-1",
          {
            id: "src-1",
            title: "Example Reg",
            source_url: "https://www.legislation.gov.uk/uksi/2015/668/data.xml",
          },
        ],
      ]),
      fragmentById: new Map([
        [
          "frag-1",
          {
            id: "frag-1",
            locator: "regulation:4:paragraph:1",
            fragment_text: "Operators must notify the authority.",
          },
        ],
      ]),
    });
    expect(composition.propositions).toHaveLength(1);
    expect(composition.fragments[0]?.text).toContain("Operators");
    expect(composition.compositionLawFragments[0]?.legislationUrl).toBe(
      "https://www.legislation.gov.uk/uksi/2015/668/regulation/4/1",
    );
    expect(composition.propositions[0]?.sourceLocator).toBe("regulation:4:paragraph:1");
  });

  it("repairs corrupted spacing in law fragment and proposition excerpts", () => {
    const views = buildLawFragmentViews([
      {
        rowId: "r1",
        statement_fragment: "A",
        supporting_proposition_ids: ["p1"],
        proposition_text: "prop one",
        source_locator: "Reg 18(1)",
        source_excerpt: "18(1)The occupier must",
        support_status: "supported",
      },
    ]);
    expect(views[0]?.sourceExcerpt).toBe("18(1) The occupier must");

    const statement: LawStatementRow = {
      id: "stmt-2",
      statement_text: "Schedule text.",
      presentation_role: "requirement",
      standalone_status: "standalone",
      confidence: "high",
      source_proposition_ids: ["p1"],
    };
    const composition = buildWorkbenchComposition(statement, {
      propositionById: new Map([
        [
          "p1",
          {
            id: "p1",
            proposition_text: "Schedule text.",
            fragment_locator: "Schedule 3",
            source_record_id: "src-1",
            source_fragment_id: "frag-1",
          },
        ],
      ]),
      sourceById: new Map([["src-1", { id: "src-1", title: "Example Reg" }]]),
      fragmentById: new Map([
        [
          "frag-1",
          {
            id: "frag-1",
            fragment_text: "Schedule 3.The record must be kept.",
          },
        ],
      ]),
    });
    expect(composition.lawFragments[0]?.sourceExcerpt).toBe("Schedule 3. The record must be kept.");
    expect(composition.propositions[0]?.sourceExcerpt).toBe("Schedule 3. The record must be kept.");
  });

  it("separates composition sources from assessment context propositions", () => {
    const statement: LawStatementRow = {
      id: "stmt-ctx",
      statement_text: "Operators must comply.",
      presentation_role: "requirement",
      standalone_status: "standalone",
      confidence: "high",
      source_proposition_ids: ["p-source"],
      required_context: [
        {
          locator: "Reg 2(3)",
          resolution_status: "resolved",
          proposition_ids: ["p-context"],
        },
      ],
    };
    const propositionById = new Map<string, PropositionRow>([
      [
        "p-source",
        {
          id: "p-source",
          proposition_text: "Operators must comply.",
          fragment_locator: "Reg 4(1)",
          source_record_id: "src-1",
        },
      ],
      [
        "p-context",
        {
          id: "p-context",
          proposition_text: "For the purposes of this regulation.",
          fragment_locator: "Reg 2(3)",
          source_record_id: "src-1",
        },
      ],
    ]);
    const composition = buildWorkbenchComposition(statement, {
      propositionById,
      sourceById: new Map([["src-1", { id: "src-1", title: "Example Reg" }]]),
      fragmentById: new Map(),
    });
    const propositions = buildPropositionReviewViews(
      statement,
      composition.recipe,
      propositionById,
      new Map(),
    );

    expect(buildCompositionSourceViews(propositions).map((source) => source.propositionId)).toEqual([
      "p-source",
    ]);
    expect(composition.compositionSources).toHaveLength(1);
    expect(composition.propositions.some((proposition) => proposition.role === "required_context")).toBe(
      true,
    );
  });

  it("normalises every workbench display excerpt field from corrupted source material", () => {
    const corruptedRecipeExcerpt = "181The occupier must";
    const corruptedFragmentText = "3.The record must be kept.";
    const corruptedEvidenceQuote = "amake a record";
    const corruptedContextFragment = "18(1)amake a record";

    const statement: LawStatementRow = {
      id: "stmt-excerpt-audit",
      statement_text: "The occupier must make a record.",
      presentation_role: "requirement",
      standalone_status: "standalone",
      confidence: "high",
      source_proposition_ids: ["p-source"],
      required_context: [
        {
          locator: "paragraph 1",
          resolution_status: "unresolved",
          proposition_ids: [],
        },
      ],
      statement_recipe: [
        {
          statement_fragment: "The occupier must make a record.",
          supporting_proposition_ids: ["p-source"],
          proposition_text: "The occupier must make a record.",
          source_locator: "Reg 18(8)",
          source_excerpt: corruptedRecipeExcerpt,
          support_status: "supported",
        },
      ],
    };

    const propositionById = new Map<string, PropositionRow>([
      [
        "p-source",
        {
          id: "p-source",
          proposition_text: "The occupier must make a record.",
          fragment_locator: "regulation:18:paragraph:8",
          source_record_id: "src-1",
          source_fragment_id: "frag-source",
          extraction_debug_meta: {
            evidence_quote: corruptedEvidenceQuote,
          },
        },
      ],
    ]);

    const fragmentById = new Map<string, SourceFragmentRow>([
      [
        "frag-source",
        {
          id: "frag-source",
          source_record_id: "src-1",
          locator: "regulation:18:paragraph:8",
          fragment_text: corruptedFragmentText,
        },
      ],
      [
        "frag-context",
        {
          id: "frag-context",
          source_record_id: "src-1",
          locator: "regulation:18:paragraph:1",
          fragment_text: corruptedContextFragment,
        },
      ],
    ]);

    const sourceFragments: SourceFragmentRow[] = Array.from(fragmentById.values());

    const composition = buildWorkbenchComposition(statement, {
      propositionById,
      sourceById: new Map([["src-1", { id: "src-1", title: "Example Reg" }]]),
      fragmentById,
    });

    const assessmentContext = buildAssessmentContextViews(
      buildContextRequirementResolutions(statement, {
        sourceFragments,
        propositionById,
        fragmentById,
      }),
    );

    const excerpts = collectWorkbenchDisplayExcerpts({ composition, assessmentContext });
    expect(excerpts.length).toBeGreaterThan(0);

    const expected = new Set([
      normalizeExcerptDisplay(corruptedRecipeExcerpt),
      normalizeExcerptDisplay(corruptedFragmentText),
      normalizeExcerptDisplay(corruptedEvidenceQuote),
      normalizeExcerptDisplay(corruptedContextFragment),
    ]);

    for (const excerpt of excerpts) {
      expect(expected.has(excerpt)).toBe(true);
      expect(excerpt).not.toBe(corruptedRecipeExcerpt);
      expect(excerpt).not.toBe(corruptedFragmentText);
      expect(excerpt).not.toBe(corruptedEvidenceQuote);
      expect(excerpt).not.toBe(corruptedContextFragment);
    }

    expect(composition.lawFragments[0]?.sourceExcerpt).toBe("181 The occupier must");
    expect(composition.propositions[0]?.sourceExcerpt).toBe("3. The record must be kept.");
    expect(composition.compositionSources[0]?.evidenceExcerpt).toBe("3. The record must be kept.");
    expect(assessmentContext[0]?.fragments[0]?.excerpt).toBe("18(1) a make a record");
  });

  it("maps assessment context resolution status labels", () => {
    const resolved: ContextRequirementResolution = {
      locator: "Reg 2",
      exportResolutionStatus: "resolved",
      resolved: true,
      fragments: [],
    };
    const ambiguous: ContextRequirementResolution = {
      locator: "Reg 3",
      exportResolutionStatus: "ambiguous",
      resolved: false,
      reason: "ambiguous",
      fragments: [],
    };
    const resolvedContainer: ContextRequirementResolution = {
      locator: "Schedule 3",
      exportResolutionStatus: "unresolved",
      resolved: true,
      resolutionMode: "container",
      fragments: [],
      children: [],
    };
    const external: ContextRequirementResolution = {
      locator: "Other Act",
      exportResolutionStatus: "external_reference",
      resolved: false,
      reason: "external reference",
      fragments: [],
    };

    expect(assessmentContextStatus(resolved)).toBe("resolved");
    expect(assessmentContextStatus(resolvedContainer)).toBe("resolved_container");
    expect(assessmentContextStatus(ambiguous)).toBe("ambiguous");
    expect(assessmentContextStatus(external)).toBe("external");
    expect(
      buildAssessmentContextViews([resolved, ambiguous])[1]?.status,
    ).toBe("ambiguous");
  });
});
