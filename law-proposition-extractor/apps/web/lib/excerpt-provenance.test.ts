import { describe, expect, it } from "vitest";

import { normalizeExcerptDisplay } from "@/lib/excerpt-display";
import {
  INTERNAL_WORD_SPACE_EXAMPLE,
  SCHEDULE_1A_PARA_18_FIXTURE,
} from "@/lib/excerpt-provenance-fixture";
import {
  buildWorkbenchExcerptProvenance,
  detectExcerptCorruption,
  summarizeExcerptCorruption,
  tracePropositionExcerptProvenance,
} from "@/lib/excerpt-provenance";
import type { CompositionBuildContext } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";

function buildSchedule1aPara18Context(): CompositionBuildContext {
  const proposition: PropositionRow = {
    id: SCHEDULE_1A_PARA_18_FIXTURE.propositionId,
    proposition_text: SCHEDULE_1A_PARA_18_FIXTURE.propositionText,
    fragment_locator: SCHEDULE_1A_PARA_18_FIXTURE.fragmentLocator,
    source_record_id: SCHEDULE_1A_PARA_18_FIXTURE.sourceRecordId,
    source_fragment_id: SCHEDULE_1A_PARA_18_FIXTURE.fragmentId,
    extraction_debug_meta: {
      evidence_quote: SCHEDULE_1A_PARA_18_FIXTURE.corruptedEvidenceQuote,
    },
  };

  const fragment = {
    id: SCHEDULE_1A_PARA_18_FIXTURE.fragmentId,
    source_record_id: SCHEDULE_1A_PARA_18_FIXTURE.sourceRecordId,
    locator: SCHEDULE_1A_PARA_18_FIXTURE.fragmentLocator,
    fragment_text: SCHEDULE_1A_PARA_18_FIXTURE.corruptedFragmentText,
  };

  return {
    propositionById: new Map([[proposition.id, proposition]]),
    sourceById: new Map([
      [
        SCHEDULE_1A_PARA_18_FIXTURE.sourceRecordId,
        { id: SCHEDULE_1A_PARA_18_FIXTURE.sourceRecordId, title: "Wales WSI 2021" },
      ],
    ]),
    fragmentById: new Map([[fragment.id!, fragment]]),
  };
}

function buildSchedule1aPara18Statement(): LawStatementRow {
  return {
    id: SCHEDULE_1A_PARA_18_FIXTURE.statementId,
    statement_text: SCHEDULE_1A_PARA_18_FIXTURE.statementText,
    presentation_role: "guidance_matching_candidate",
    standalone_status: "standalone",
    confidence: "high",
    source_proposition_ids: [SCHEDULE_1A_PARA_18_FIXTURE.propositionId],
    statement_recipe: [
      {
        statement_fragment: SCHEDULE_1A_PARA_18_FIXTURE.statementText,
        supporting_proposition_ids: [SCHEDULE_1A_PARA_18_FIXTURE.propositionId],
        proposition_text: SCHEDULE_1A_PARA_18_FIXTURE.propositionText,
        source_locator: SCHEDULE_1A_PARA_18_FIXTURE.fragmentLocator,
        source_excerpt: SCHEDULE_1A_PARA_18_FIXTURE.corruptedRecipeExcerpt,
        support_status: "supported",
      },
    ],
  } as LawStatementRow & {
    statement_recipe: Array<{
      statement_fragment: string;
      supporting_proposition_ids: string[];
      proposition_text: string;
      source_locator: string;
      source_excerpt: string;
      support_status: "supported";
    }>;
  };
}

describe("detectExcerptCorruption", () => {
  it("flags locator bleed, glued list markers, and internal word spaces", () => {
    const findings = detectExcerptCorruption(SCHEDULE_1A_PARA_18_FIXTURE.corruptedFragmentText);
    const kinds = new Set(findings.map((finding) => finding.kind));

    expect(kinds.has("locator_label_bleed")).toBe(true);
    expect(kinds.has("glued_list_marker")).toBe(true);
    expect(findings.some((finding) => finding.match.includes("181"))).toBe(true);
    expect(findings.some((finding) => finding.match.toLowerCase().includes("amake"))).toBe(true);
    expect(findings.some((finding) => finding.match.toLowerCase().includes("andbassess"))).toBe(true);
  });

  it("flags internal word spaces from inline XML token splits", () => {
    const findings = detectExcerptCorruption(INTERNAL_WORD_SPACE_EXAMPLE);
    expect(findings.some((finding) => finding.kind === "internal_word_space")).toBe(true);
    expect(findings.some((finding) => finding.match.toLowerCase() === "m anure")).toBe(true);
  });
});

describe("tracePropositionExcerptProvenance", () => {
  it("identifies source_fragment_extraction as the earliest corruption stage", () => {
    const context = buildSchedule1aPara18Context();
    const proposition = context.propositionById.get(SCHEDULE_1A_PARA_18_FIXTURE.propositionId)!;
    const fragment = context.fragmentById.get(SCHEDULE_1A_PARA_18_FIXTURE.fragmentId)!;

    const record = tracePropositionExcerptProvenance({
      proposition,
      fragment,
      recipeSourceExcerpt: SCHEDULE_1A_PARA_18_FIXTURE.corruptedRecipeExcerpt,
    });

    expect(record.earliestCorruptionStage).toBe("source_fragment_extraction");
    expect(record.steps[0]?.findings.length).toBeGreaterThan(0);
    expect(record.steps[1]?.findings.some((finding) => finding.kind === "glued_list_marker")).toBe(
      true,
    );
    expect(record.finalDisplayText).toContain("181 The occupier");
    expect(record.finalDisplayText).toContain("a make a record");
    expect(record.displayStillCorrupt).toBe(true);
    expect(record.finalDisplayText).toContain("andbassess");
  });
});

describe("buildWorkbenchExcerptProvenance", () => {
  it("traces rendered workbench excerpts for the schedule 1A paragraph 18 statement", () => {
    const statement = buildSchedule1aPara18Statement();
    const context = buildSchedule1aPara18Context();
    const records = buildWorkbenchExcerptProvenance({
      statement,
      context,
      sourceFragments: Array.from(context.fragmentById.values()),
    });

    expect(records.length).toBeGreaterThan(0);

    const summary = summarizeExcerptCorruption(records);
    expect(summary.corruption_origin).toBe("source_fragment_extraction");
    expect(summary.affected_fields).toContain("fragment_text");
    expect(summary.records_with_residual_display_corruption).toBeGreaterThan(0);

    const propositionRecord = records.find((record) =>
      record.id.includes(SCHEDULE_1A_PARA_18_FIXTURE.propositionId),
    );
    expect(propositionRecord?.earliestCorruptionStage).toBe("source_fragment_extraction");

    const lawFragment = records.find((record) => record.surface === "lawFragment.sourceExcerpt");
    expect(lawFragment?.finalDisplayText).toBe(
      normalizeExcerptDisplay(SCHEDULE_1A_PARA_18_FIXTURE.corruptedRecipeExcerpt),
    );
    expect(lawFragment?.earliestCorruptionStage).toBe("statement_recipe_source_excerpt");
  });
});
