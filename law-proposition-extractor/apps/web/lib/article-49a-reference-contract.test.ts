/**
 * Frontend reference-resolution + trigger-card contract for Article 49a (20-BR10I).
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import {
  authorityHeadlineSummary,
} from "@/lib/legal-authority-display";
import {
  buildWorkbenchLegalReferences,
  type InlineLegalReference,
} from "@/lib/statement-inline-references";
import {
  buildTypedLegalContextSections,
  canonicalTerminalStructuredPath,
} from "@/lib/typed-legal-context";

const here = path.dirname(fileURLToPath(import.meta.url));
const bundlePath = path.resolve(here, "fixtures/article-49a-acceptance/serialized-bundle.json");

type Bundle = {
  propositions: PropositionRow[];
  effective_law_statements: LawStatementRow[] | { statements: LawStatementRow[] };
  source_fragments: SourceFragmentRow[];
};

function loadBundle(): Bundle {
  return JSON.parse(readFileSync(bundlePath, "utf8")) as Bundle;
}

function statementsOf(bundle: Bundle): LawStatementRow[] {
  const raw = bundle.effective_law_statements;
  return Array.isArray(raw) ? raw : (raw.statements ?? []);
}

function identifyRoles(props: PropositionRow[]): Record<string, string> {
  const p1 = props
    .filter((p) => String(p.fragment_locator ?? "").startsWith("article:49a:paragraph:1"))
    .sort((a, b) => Number(a.source_order ?? 0) - Number(b.source_order ?? 0));
  const separate =
    p1.find(
      (p) =>
        p.legal_effect_type === "obligation" ||
        String(p.proposition_text ?? "")
          .toLowerCase()
          .includes("placed in boxes"),
    ) ?? p1[0]!;
  const mixing = p1.find((p) => p.id !== separate.id) ?? p1[1]!;
  const byPath = new Map<string, PropositionRow>();
  for (const prop of props) {
    const pathKey = (prop.extraction_debug_meta as { structured_list_path?: string } | undefined)
      ?.structured_list_path;
    if (pathKey) {
      byPath.set(pathKey, prop);
    }
  }
  const p3 = props.find((p) => String(p.fragment_locator ?? "").startsWith("article:49a:paragraph:3"));
  if (!p3) {
    throw new Error("missing P3");
  }
  return {
    P1: separate.id,
    P2: mixing.id,
    E1: byPath.get("2-a-i")!.id,
    E2: byPath.get("2-a-ii")!.id,
    E3: byPath.get("2-b")!.id,
    P3: p3.id,
  };
}

function paragraphReference(references: InlineLegalReference[]): InlineLegalReference | undefined {
  return references.find((reference) => /paragraph\s*2|49a\(2\)/i.test(reference.label));
}

describe("Article 49a reference contract (frontend)", () => {
  const bundle = loadBundle();
  const roles = identifyRoles(bundle.propositions);
  const propById = new Map(bundle.propositions.map((prop) => [prop.id, prop]));
  const fragmentById = new Map(
    bundle.source_fragments.map((fragment) => [String(fragment.id), fragment]),
  );
  const p3Statement = statementsOf(bundle).find((statement) =>
    (statement.source_proposition_ids ?? []).includes(roles.P3),
  );
  if (!p3Statement) {
    throw new Error("missing P3 statement");
  }

  it("export run proposition count is six", () => {
    expect(bundle.propositions).toHaveLength(6);
  });

  it("P3 trigger section count is three with deterministic role order", () => {
    const sections = buildTypedLegalContextSections(p3Statement, propById);
    expect(sections.triggerConditions).toHaveLength(3);
    const paths = sections.triggerConditions.map((item) =>
      canonicalTerminalStructuredPath(
        item.sourceLocator,
        (propById.get(item.propositionId)?.extraction_debug_meta as
          | { structured_list_path?: string }
          | undefined)?.structured_list_path,
      ),
    );
    expect(paths).toEqual(["2-a-i", "2-a-ii", "2-b"]);
    expect(paths.filter((pathKey) => pathKey === "2-a-i")).toHaveLength(1);
    expect(paths.filter((pathKey) => pathKey === "2-a-ii")).toHaveLength(1);
    expect(paths.filter((pathKey) => pathKey === "2-b")).toHaveLength(1);
  });

  it("statement header and proposition card share the same resolved paragraph-2 target", () => {
    const bareStatement: LawStatementRow = {
      ...p3Statement,
      statement_text:
        "In the cases referred to in paragraph 2, a fisheries administration must monitor the catch composition by way of sampling.",
      // Avoid composition-trace surface forms ("Article 49a(2)") shadowing the bare relative.
      composition_trace: [],
    };
    const refs = buildWorkbenchLegalReferences({
      statement: bareStatement,
      assessmentContext: [],
      propositionById: propById,
      sourceFragments: bundle.source_fragments,
      fragmentById,
      classifiedPropositions: [
        {
          proposition: {
            propositionId: roles.P3,
            propositionText:
              "In the cases referred to in paragraph 2, a fisheries administration must monitor the catch composition by way of sampling.",
            sourceExcerpt:
              "In the cases referred to in paragraph 2, a fisheries administration must monitor the catch composition by way of sampling.",
          },
        },
      ],
      compositionLawFragments: [],
    });

    const header = paragraphReference(refs.referencesBySourceId.get("statement") ?? []);
    const card = paragraphReference(
      refs.referencesBySourceId.get(`proposition:${roles.P3}`) ?? [],
    );
    expect(header).toBeDefined();
    expect(card).toBeDefined();
    expect(header?.status).toBe("resolved");
    expect(card?.status).toBe("resolved");
    expect(header?.accent).toBe("resolved");
    expect(card?.accent).toBe("resolved");
    expect(header?.canonicalLocator ?? header?.resolvedLocator).toBe(
      "article:49a:paragraph:2",
    );
    expect(card?.canonicalLocator ?? card?.resolvedLocator).toBe("article:49a:paragraph:2");
    expect(header?.resolutionMethod).toBe("structural_relative");
    expect(card?.resolutionMethod).toBe("structural_relative");
    expect(header?.referenceKind).toBe("inline_structural");
    expect(card?.referenceKind).toBe("inline_structural");
  });

  it("authority panel for paragraph 2 prefers source provision, not trigger expansion", () => {
    const bareStatement: LawStatementRow = {
      ...p3Statement,
      statement_text:
        "In the cases referred to in paragraph 2, a fisheries administration must monitor the catch composition by way of sampling.",
      composition_trace: [],
    };
    const refs = buildWorkbenchLegalReferences({
      statement: bareStatement,
      assessmentContext: [],
      propositionById: propById,
      sourceFragments: bundle.source_fragments,
      fragmentById,
      classifiedPropositions: [
        {
          proposition: {
            propositionId: roles.P3,
            propositionText: bareStatement.statement_text ?? "",
            sourceExcerpt: bareStatement.statement_text ?? "",
          },
        },
      ],
      compositionLawFragments: [],
    });
    const header = paragraphReference(refs.referencesBySourceId.get("statement") ?? []);
    expect(header).toBeDefined();
    expect(header!.propositionIds.length).toBeLessThan(3);
    const headline = authorityHeadlineSummary(header!, propById);
    expect(headline.toLowerCase()).not.toMatch(/four trigger|triggered in these cases/i);
    expect(header!.canonicalLocator).toBe("article:49a:paragraph:2");
    expect(header!.resolutionMethod).toBe("structural_relative");
  });

  it("dedupes legacy intermediate + terminal locator trigger cards", () => {
    const staleLike: LawStatementRow = {
      ...p3Statement,
      required_context: [
        {
          kind: "trigger_condition",
          locator: "article:49a:paragraph:2:list:2-a-i",
          proposition_ids: [roles.E1],
          resolution_status: "resolved",
          referenced_locator: "article:49a:paragraph:2",
          target_canonical_locator: "article:49a:paragraph:2",
          inherited_via_group: true,
          reference_text: "paragraph 2",
          resolution_basis: "structural_relative",
        },
        {
          kind: "trigger_condition",
          locator: "article:49a:paragraph:2:(a)(i)",
          proposition_ids: ["prop:legacy-alias-2ai"],
          resolution_status: "resolved",
          referenced_locator: "article:49a:paragraph:2",
          target_canonical_locator: "article:49a:paragraph:2",
          inherited_via_group: true,
          reference_text: "paragraph 2",
          resolution_basis: "structural_relative",
        },
        {
          kind: "trigger_condition",
          locator: "article:49a:paragraph:2:list:2-a-ii",
          proposition_ids: [roles.E2],
          resolution_status: "resolved",
          referenced_locator: "article:49a:paragraph:2",
          target_canonical_locator: "article:49a:paragraph:2",
          inherited_via_group: true,
        },
        {
          kind: "trigger_condition",
          locator: "article:49a:paragraph:2:(b)",
          proposition_ids: [roles.E3],
          resolution_status: "resolved",
          referenced_locator: "article:49a:paragraph:2",
          target_canonical_locator: "article:49a:paragraph:2",
          inherited_via_group: true,
        },
      ],
    };
    const propByIdWithLegacy = new Map(propById);
    propByIdWithLegacy.set("prop:legacy-alias-2ai", {
      id: "prop:legacy-alias-2ai",
      fragment_locator: "article:49a:paragraph:2:(a)(i)",
      proposition_text: "Legacy alias small-pelagic derogation",
      extraction_debug_meta: { structured_list_path: "2-a-i" },
      source_order: 99,
    });
    const sections = buildTypedLegalContextSections(staleLike, propByIdWithLegacy);
    expect(sections.triggerConditions).toHaveLength(3);
    const pathKeys = sections.triggerConditions.map((item) =>
      canonicalTerminalStructuredPath(
        item.sourceLocator,
        (
          propByIdWithLegacy.get(item.propositionId)?.extraction_debug_meta as
            | { structured_list_path?: string }
            | undefined
        )?.structured_list_path,
      ),
    );
    expect(pathKeys).toEqual(["2-a-i", "2-a-ii", "2-b"]);
    expect(sections.triggerConditions.some((item) => item.sourceLocator.includes(":(a)(i)"))).toBe(
      false,
    );
  });

  it("keeps unresolved references on the warning accent (safe fallback)", () => {
    const orphan: LawStatementRow = {
      id: "lawstmt:orphan",
      statement_text: "See paragraph 99 for details.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "context_dependent",
      confidence: "low",
      source_proposition_ids: [],
      required_context: [],
    };
    const refs = buildWorkbenchLegalReferences({
      statement: orphan,
      assessmentContext: [],
      propositionById: new Map(),
      sourceFragments: [],
      fragmentById: new Map(),
      classifiedPropositions: [],
      compositionLawFragments: [],
    });
    const warning = (refs.referencesBySourceId.get("statement") ?? []).find((reference) =>
      /paragraph\s*99/i.test(reference.label),
    );
    expect(warning?.status).toBe("unresolved");
    expect(warning?.accent).toBe("warning");
  });

  it("Article 14 remains ordinary context on E3 only", () => {
    const e3 = statementsOf(bundle).find((statement) =>
      (statement.source_proposition_ids ?? []).includes(roles.E3),
    );
    expect(e3).toBeDefined();
    const art14 = (e3!.required_context ?? []).filter((entry) => {
      const locator = String(entry.locator ?? "").toLowerCase();
      return locator.includes("article:14") || locator.includes("article 14");
    });
    expect(art14.length).toBeGreaterThan(0);
    expect(art14.every((entry) => entry.kind === "referenced_locator")).toBe(true);
    const p3Art14 = (p3Statement.required_context ?? []).filter((entry) => {
      const locator = String(entry.locator ?? "").toLowerCase();
      return locator.includes("article:14") || locator.includes("article 14");
    });
    expect(p3Art14).toHaveLength(0);
  });
});
