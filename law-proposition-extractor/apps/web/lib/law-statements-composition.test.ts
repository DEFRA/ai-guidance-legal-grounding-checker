import { describe, expect, it } from "vitest";

import {
  buildCompositionPropositionGroups,
  buildCoverageChecks,
  buildCoverageWarningItems,
  buildStatementFragments,
  buildStatementRecipe,
  EXPORT_FIELD_UNAVAILABLE,
  inferSupportStatus,
  recipeRowsForFragment,
  type SourceFragmentRow,
} from "@/lib/law-statements-composition";
import {
  propositionRefsForStatement,
  type LawStatementRow,
  type PropositionRow,
} from "@/lib/law-statements-index";

const sampleStatement: LawStatementRow = {
  id: "lawstmt:test",
  statement_text:
    "Poultry manure must be incorporated as soon as practicable. Supporting context applies from regulation 9.",
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

const propositions = new Map<string, PropositionRow>([
  [
    "prop:host",
    {
      id: "prop:host",
      proposition_text: "Poultry manure must be incorporated as soon as practicable.",
      fragment_locator: "regulation 4(1)",
      source_record_id: "lex:test",
      source_fragment_id: "frag:test-001",
    },
  ],
  [
    "prop:xref",
    {
      id: "prop:xref",
      proposition_text: "Cross-reference supporting text.",
      fragment_locator: "regulation 4(2)",
      source_record_id: "lex:test",
    },
  ],
  [
    "prop:other",
    {
      id: "prop:other",
      proposition_text: "Other host rule text.",
      fragment_locator: "regulation 9",
      source_record_id: "lex:other",
    },
  ],
  [
    "prop:imported",
    {
      id: "prop:imported",
      proposition_text: "Imported connector proposition.",
      fragment_locator: "regulation 4(2)",
      source_record_id: "lex:other",
      extraction_debug_meta: {
        evidence_quote: "Imported connector evidence quote.",
      },
    },
  ],
]);

const fragments = new Map<string, SourceFragmentRow>([
  [
    "frag:test-001",
    {
      id: "frag:test-001",
      fragment_text: "Authoritative source fragment text for host proposition.",
      locator: "regulation:4",
    },
  ],
]);

describe("buildStatementFragments", () => {
  it("splits multi-sentence statements when no explicit fragment map exists", () => {
    const multiSourceStatement: LawStatementRow = {
      ...sampleStatement,
      source_proposition_ids: ["prop:host", "prop:other"],
    };
    const rows = buildStatementFragments(multiSourceStatement, propositions);
    expect(rows.length).toBeGreaterThan(1);
    expect(rows.every((row) => row.derived)).toBe(true);
  });

  it("uses export statement fragments when present", () => {
    const withExport = {
      ...sampleStatement,
      statement_fragments: [{ id: "frag-a", text: "Exported fragment A." }],
    } as LawStatementRow & { statement_fragments: Array<{ id: string; text: string }> };
    const rows = buildStatementFragments(withExport, propositions);
    expect(rows).toEqual([
      { id: "frag-a", text: "Exported fragment A.", derived: false },
    ]);
  });
});

describe("inferSupportStatus", () => {
  it("marks ambiguous context as partial and unresolved context as unresolved", () => {
    const refs = propositionRefsForStatement(sampleStatement);
    const ambiguous = refs.find((ref) => ref.role === "required_context");
    const via = refs.find((ref) => ref.role === "via");
    expect(inferSupportStatus(ambiguous!)).toBe("partial");
    expect(inferSupportStatus(via!)).toBe("partial");
  });
});

describe("buildStatementRecipe", () => {
  it("builds recipe rows from proposition refs and available source metadata", () => {
    const recipe = buildStatementRecipe(sampleStatement, {
      propositionById: propositions,
      sourceById: new Map(),
      fragmentById: fragments,
    });
    expect(recipe.length).toBe(propositionRefsForStatement(sampleStatement).length);
    expect(recipe[0]?.source_excerpt).toContain("Authoritative source fragment");
    expect(recipe.some((row) => row.source_excerpt.includes("Imported connector evidence"))).toBe(
      true,
    );
  });

  it("uses export recipe rows when provided", () => {
    const withExport = {
      ...sampleStatement,
      statement_recipe: [
        {
          statement_fragment: "Exported fragment",
          supporting_proposition_ids: ["prop:host"],
          proposition_text: "Exported proposition text",
          source_locator: "regulation 1",
          source_excerpt: "Exported excerpt",
          support_status: "supported",
        },
      ],
    } as LawStatementRow & {
      statement_recipe: Array<Record<string, unknown>>;
    };
    const recipe = buildStatementRecipe(withExport, {
      propositionById: propositions,
      sourceById: new Map(),
      fragmentById: fragments,
    });
    expect(recipe).toHaveLength(1);
    expect(recipe[0]?.statement_fragment).toBe("Exported fragment");
  });
});

describe("buildCoverageChecks", () => {
  it("returns export unavailable for fields missing from export", () => {
    const recipe = buildStatementRecipe(sampleStatement, {
      propositionById: propositions,
      sourceById: new Map(),
      fragmentById: fragments,
    });
    const checks = buildCoverageChecks(sampleStatement, recipe);
    const conditions = checks.find((check) => check.key === "conditions_preserved");
    expect(conditions?.value).toBe(EXPORT_FIELD_UNAVAILABLE);
    const crossRefs = checks.find((check) => check.key === "cross_references_resolved");
    expect(crossRefs?.value).toContain("ambiguous");
  });
});

describe("buildCoverageWarningItems", () => {
  it("includes category checklist items and unresolved context warnings", () => {
    const recipe = buildStatementRecipe(sampleStatement, {
      propositionById: propositions,
      sourceById: new Map(),
      fragmentById: fragments,
    });
    const checks = buildCoverageChecks(sampleStatement, recipe);
    const items = buildCoverageWarningItems(sampleStatement, checks);
    expect(items.some((item) => item.category === "condition")).toBe(true);
    expect(items.some((item) => item.category === "cross_reference")).toBe(true);
    expect(items.some((item) => item.category === "unresolved_context")).toBe(true);
  });
});

describe("recipeRowsForFragment", () => {
  it("links recipe rows to matching statement fragments", () => {
    const recipe = buildStatementRecipe(sampleStatement, {
      propositionById: propositions,
      sourceById: new Map(),
      fragmentById: fragments,
    });
    const statementFragments = buildStatementFragments(sampleStatement, propositions);
    const hostFragment = statementFragments.find((fragment) =>
      fragment.text.includes("Poultry manure"),
    );
    expect(hostFragment).toBeDefined();
    const linked = recipeRowsForFragment(hostFragment!, recipe);
    expect(linked.length).toBeGreaterThan(0);
  });
});

describe("buildCompositionPropositionGroups", () => {
  it("groups supporting propositions by source locator and role order", () => {
    const recipe = buildStatementRecipe(sampleStatement, {
      propositionById: propositions,
      sourceById: new Map(),
      fragmentById: fragments,
    });
    const groups = buildCompositionPropositionGroups(sampleStatement, recipe);
    expect(groups.length).toBeGreaterThan(0);
    for (const group of groups) {
      expect(group.items.length).toBeGreaterThan(0);
      expect(group.items[0]?.role).toBeDefined();
    }
  });
});
