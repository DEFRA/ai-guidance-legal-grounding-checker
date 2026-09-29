import { describe, expect, it } from "vitest";

import {
  assessStatementQuality,
  contextRoleForKind,
  isResolvedTypedContext,
  propositionRefsForStatement,
  type LawStatementRow,
  type PropositionRow,
  type RequiredContextEntry,
} from "@/lib/law-statements-index";
import {
  buildTypedLegalContextSections,
  formatCanonicalLocatorLabel,
  partitionRequiredContext,
  resolutionBasisLabel,
  statementWithGenericContextOnly,
} from "@/lib/typed-legal-context";
import { buildContextRequirementResolutions } from "@/lib/context-locator-resolution";
import { assessmentContextStatus, buildAssessmentContextViews } from "@/lib/review-workbench-views";
import article49aFixture from "@/lib/fixtures/article-49a-typed-effective-law.json";

const P1 = "prop-demo-49a-p1-separate";
const P2 = "prop-demo-49a-p1-no-mixing";
const E1 = "prop-demo-49a-p2-pelagic";
const E2 = "prop-demo-49a-p2-industrial";
const E3 = "prop-demo-49a-p2-small-vessels";
const P3 = "prop-demo-49a-p3-monitoring";
const ART14 = "prop-demo-article-14-p1";

function statementBySourceProp(propId: string): LawStatementRow {
  const row = (article49aFixture.statements as LawStatementRow[]).find((statement) =>
    (statement.source_proposition_ids ?? []).includes(propId),
  );
  if (!row) {
    throw new Error(`missing statement for ${propId}`);
  }
  return row;
}

function propositionById(): Map<string, PropositionRow> {
  return new Map(
    (article49aFixture.propositions as PropositionRow[]).map((proposition) => [
      proposition.id,
      proposition,
    ]),
  );
}

describe("typed context field plumbing", () => {
  it("preserves typed provenance fields from serialized effective-law", () => {
    const entry = statementBySourceProp(P1).required_context?.[0] as RequiredContextEntry;
    expect(entry.kind).toBe("applicable_exception");
    expect(entry.relationship_id).toMatch(/^legalrel:/);
    expect(entry.relationship_type).toBe("exception_to");
    expect(entry.relationship_direction).toBe("incoming");
    expect(entry.inherited_via_group).toBe(true);
    expect(entry.legal_rule_group_id).toMatch(/^rulegrp:/);
    expect(entry.resolution_basis).toBe("structural_relative");
    expect(entry.inference_basis).toBe("explicit_exception_cue");
    expect(entry.referenced_locator).toBe("article:49a:paragraph:1");
    expect(entry.reference_text).toBe("Paragraph 1");
    expect(entry.target_canonical_locator).toBe("article:49a:paragraph:1");
  });

  it("maps typed kinds to distinct UI roles", () => {
    expect(contextRoleForKind("applicable_exception")).toBe("exception");
    expect(contextRoleForKind("exception_target")).toBe("displaced_rule");
    expect(contextRoleForKind("trigger_condition")).toBe("trigger");
    expect(contextRoleForKind("referenced_locator")).toBe("required_context");
    expect(contextRoleForKind(undefined)).toBe("required_context");
  });

  it("maps older untyped context through the legacy path", () => {
    const statement: LawStatementRow = {
      id: "lawstmt:legacy",
      statement_text: "Legacy statement.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "context_dependent",
      confidence: "medium",
      source_proposition_ids: ["prop:host"],
      required_context: [
        {
          locator: "regulation 9",
          resolution_status: "resolved",
          proposition_ids: ["prop:ctx"],
        },
      ],
    };
    const refs = propositionRefsForStatement(statement);
    expect(refs.filter((ref) => ref.role === "required_context").map((ref) => ref.propositionId)).toEqual([
      "prop:ctx",
    ]);
    expect(refs.some((ref) => ref.role === "exception")).toBe(false);
  });

  it("dedupes typed context against overlapping generic context", () => {
    const statement: LawStatementRow = {
      id: "lawstmt:dedupe",
      statement_text: "Host.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "context_dependent",
      confidence: "high",
      source_proposition_ids: ["prop:host"],
      required_context: [
        {
          kind: "exception_target",
          locator: "article:49a:paragraph:1",
          resolution_status: "resolved",
          proposition_ids: [P1],
          relationship_id: "legalrel:x",
          relationship_type: "exception_to",
          relationship_direction: "outgoing",
          inherited_via_group: true,
          resolution_basis: "structural_relative",
          target_canonical_locator: "article:49a:paragraph:1",
        },
        {
          kind: "referenced_locator",
          locator: "paragraph 1",
          resolution_status: "resolved",
          proposition_ids: [P1],
        },
        {
          kind: "referenced_locator",
          locator: "article 14",
          resolution_status: "resolved",
          proposition_ids: [ART14],
        },
      ],
    };

    const refs = propositionRefsForStatement(statement);
    expect(refs.filter((ref) => ref.propositionId === P1).map((ref) => ref.role)).toEqual([
      "displaced_rule",
    ]);
    expect(refs.some((ref) => ref.propositionId === ART14 && ref.role === "required_context")).toBe(
      true,
    );

    const partitioned = partitionRequiredContext(statement);
    expect(partitioned.typed).toHaveLength(1);
    expect(partitioned.generic.map((entry) => entry.locator)).toEqual(["article 14"]);
  });
});

describe("Article 49a typed legal context sections", () => {
  const props = propositionById();

  it("builds applicable exceptions for P1 and P2", () => {
    for (const propId of [P1, P2]) {
      const sections = buildTypedLegalContextSections(statementBySourceProp(propId), props);
      expect(sections.applicableExceptions.map((item) => item.propositionId)).toEqual([E1, E2, E3]);
      expect(sections.exceptionTargets).toEqual([]);
      expect(sections.triggerConditions).toEqual([]);
      expect(sections.applicableExceptions.every((item) => item.inheritedViaGroup)).toBe(true);
      expect(sections.applicableExceptions[0]?.groupInheritanceLabel).toContain(
        "Article 49a, paragraph 1",
      );
      expect(sections.applicableExceptions[0]?.resolutionBasisLabel).toBe(
        "Structural relative reference",
      );
    }
  });

  it("builds exception targets for E1/E2/E3 with Article 14 as ordinary context on E3", () => {
    for (const propId of [E1, E2, E3]) {
      const sections = buildTypedLegalContextSections(statementBySourceProp(propId), props);
      expect(sections.exceptionTargets.map((item) => item.propositionId)).toEqual([P1, P2]);
      expect(sections.applicableExceptions).toEqual([]);
      expect(sections.triggerConditions).toEqual([]);
      expect(sections.exceptionTargets.every((item) => item.inheritedViaGroup)).toBe(true);
    }

    const e3 = statementBySourceProp(E3);
    const generic = statementWithGenericContextOnly(e3);
    expect(generic.required_context?.map((entry) => entry.locator)).toEqual(["article 14"]);
    expect(
      (e3.required_context ?? []).some(
        (entry) =>
          entry.kind === "exception_target" &&
          (entry.proposition_ids ?? []).includes(ART14),
      ),
    ).toBe(false);
  });

  it("builds trigger conditions for P3 and does not invent incoming triggers on exceptions", () => {
    const sections = buildTypedLegalContextSections(statementBySourceProp(P3), props);
    expect(sections.triggerConditions.map((item) => item.propositionId)).toEqual([E1, E2, E3]);
    expect(sections.triggerConditions.every((item) => item.inheritedViaGroup)).toBe(true);
    expect(sections.triggerConditions[0]?.groupInheritanceLabel).toContain(
      "Article 49a, paragraph 2",
    );

    for (const propId of [E1, E2, E3]) {
      const exceptionSections = buildTypedLegalContextSections(statementBySourceProp(propId), props);
      expect(exceptionSections.triggerConditions).toEqual([]);
      expect(
        exceptionSections.exceptionTargets.some((item) => item.propositionId === P3),
      ).toBe(false);
    }
  });

  it("describes direct relationships without claiming group inheritance", () => {
    const host = statementBySourceProp("prop-demo-art30-p1-only");
    const sections = buildTypedLegalContextSections(host, props);
    expect(sections.applicableExceptions).toHaveLength(1);
    expect(sections.applicableExceptions[0]?.inheritedViaGroup).toBe(false);
    expect(sections.applicableExceptions[0]?.groupInheritanceLabel).toBeNull();
    expect(sections.applicableExceptions[0]?.conciseExplanation).toMatch(/Direct applicable exception/i);
  });

  it("formats readable resolution labels and canonical locators", () => {
    expect(formatCanonicalLocatorLabel("article:49a:paragraph:1")).toBe("Article 49a, paragraph 1");
    expect(resolutionBasisLabel("structural_relative")).toBe("Structural relative reference");
    expect(resolutionBasisLabel("explicit_exception_cue")).toBe("explicit exception cue");
  });

  it("why-linked details include relationship type, reference and readable resolution basis", () => {
    const item = buildTypedLegalContextSections(statementBySourceProp(P1), props).applicableExceptions[0]!;
    expect(item.whyLinkedSummary).toMatch(/exception_to/);
    expect(item.whyLinkedDetails.some((detail) => detail.startsWith("Reference:"))).toBe(true);
    expect(
      item.whyLinkedDetails.some((detail) => detail.includes("Structural relative reference")),
    ).toBe(true);
    expect(item.relationshipId).toMatch(/^legalrel:/);
    expect(item.legalRuleGroupId).toMatch(/^rulegrp:/);
  });
});

describe("typed context ambiguity assessment", () => {
  it("does not flag resolved structural_relative typed context as ambiguous", () => {
    const statement = statementBySourceProp(P1);
    const assessment = assessStatementQuality(statement);
    expect(assessment.flags).not.toContain("ambiguous_context");
    expect(assessment.issueLabels).toContain("Resolved through local structure");
    expect(isResolvedTypedContext(statement.required_context![0]!)).toBe(true);

    const resolutions = buildContextRequirementResolutions(statement, {
      sourceFragments: article49aFixture.source_fragments as never[],
      propositionById: propositionById(),
      fragmentById: new Map(),
    });
    const views = buildAssessmentContextViews(resolutions);
    expect(views.every((view) => view.status === "resolved")).toBe(true);
    expect(views.every((view) => view.status !== "ambiguous")).toBe(true);
  });

  it("still flags genuinely ambiguous locator context", () => {
    const statement: LawStatementRow = {
      id: "lawstmt:ambiguous",
      statement_text: "Ambiguous.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "context_dependent",
      confidence: "medium",
      source_proposition_ids: ["prop:host"],
      required_context: [
        {
          locator: "paragraph 1",
          resolution_status: "ambiguous",
          proposition_ids: [],
        },
      ],
    };
    const assessment = assessStatementQuality(statement);
    expect(assessment.flags).toContain("ambiguous_context");
  });

  it("marks missing typed targets as unresolved rather than resolved", () => {
    const entry: RequiredContextEntry = {
      kind: "exception_target",
      locator: "paragraph 1",
      resolution_status: "resolved",
      proposition_ids: [],
      relationship_id: "legalrel:missing-target",
      relationship_type: "exception_to",
      relationship_direction: "outgoing",
      resolution_basis: "structural_relative",
      inherited_via_group: true,
      target_canonical_locator: "article:49a:paragraph:1",
    };
    expect(isResolvedTypedContext(entry)).toBe(false);

    const statement: LawStatementRow = {
      id: "lawstmt:missing-target",
      statement_text: "Missing target.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "context_dependent",
      confidence: "medium",
      source_proposition_ids: [E1],
      required_context: [entry],
    };
    const resolution = buildContextRequirementResolutions(statement, {
      sourceFragments: [],
      propositionById: propositionById(),
      fragmentById: new Map(),
    })[0]!;
    expect(resolution.resolved).toBe(false);
    expect(assessmentContextStatus(resolution)).toBe("unresolved");
    expect(resolution.inheritedContextLabel).toMatch(/missing/i);
  });
});

describe("deterministic ordering", () => {
  it("renders typed items in stable proposition order regardless of input shuffle", () => {
    const base = statementBySourceProp(P1);
    const shuffled: LawStatementRow = {
      ...base,
      required_context: [...(base.required_context ?? [])].reverse(),
    };
    const left = buildTypedLegalContextSections(base, propositionById()).applicableExceptions.map(
      (item) => item.propositionId,
    );
    const right = buildTypedLegalContextSections(shuffled, propositionById()).applicableExceptions.map(
      (item) => item.propositionId,
    );
    expect(left).toEqual(right);
    expect(left).toEqual([E1, E2, E3]);
  });
});
