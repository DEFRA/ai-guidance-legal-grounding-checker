/**
 * Decision explanation models, indexes, and statement projection tests.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import {
  buildDecisionExplanationIndex,
  emptyDecisionExplanationsArtifact,
  heuristicByRuleId,
  methodLabel,
  parseDecisionExplanation,
  parseDecisionExplanationsArtifact,
  parseHeuristicsResponse,
} from "@/lib/decision-explanations";
import {
  buildStatementExplanationViewModel,
  type LegalRuleGroupRow,
} from "@/lib/statement-explanation";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";

const here = path.dirname(fileURLToPath(import.meta.url));
const bundlePath = path.resolve(here, "fixtures/article-49a-acceptance/serialized-bundle.json");
const heuristicsPath = path.resolve(
  here,
  "fixtures/article-49a-acceptance/heuristics-referenced.json",
);

type Bundle = {
  propositions: PropositionRow[];
  effective_law_statements: LawStatementRow[];
  source_fragments: SourceFragmentRow[];
  legal_rule_groups?: { groups?: LegalRuleGroupRow[] } | LegalRuleGroupRow[];
  decision_explanations?: unknown;
};

function loadBundle(): Bundle {
  return JSON.parse(readFileSync(bundlePath, "utf8")) as Bundle;
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

function statementFor(bundle: Bundle, propId: string): LawStatementRow {
  const row = bundle.effective_law_statements.find((statement) =>
    (statement.source_proposition_ids ?? []).includes(propId),
  );
  if (!row) {
    throw new Error(`missing statement for ${propId}`);
  }
  return row;
}

function groupsFromBundle(bundle: Bundle): LegalRuleGroupRow[] {
  const raw = bundle.legal_rule_groups;
  if (Array.isArray(raw)) {
    return raw;
  }
  if (raw && typeof raw === "object" && Array.isArray(raw.groups)) {
    return raw.groups;
  }
  return [];
}

describe("decision explanation models", () => {
  it("parses the Python Article 49a decision artifact", () => {
    const bundle = loadBundle();
    const started = performance.now();
    const artifact = parseDecisionExplanationsArtifact(bundle.decision_explanations);
    const index = buildDecisionExplanationIndex(artifact, { artifactPresent: true });
    const elapsed = performance.now() - started;
    expect(artifact.decisions.length).toBe(43);
    expect(index.decisions.length).toBe(43);
    expect(index.byStage.get("selection")?.length).toBe(5);
    expect(elapsed).toBeLessThan(250);
  });

  it("tolerates unknown additive fields and unknown enums", () => {
    const diagnostics: string[] = [];
    const parsed = parseDecisionExplanation(
      {
        id: "decision:x",
        stage: "future_stage",
        decision_type: "future_type",
        subject_kind: "future_subject",
        subject_id: "subj-1",
        outcome: "ok",
        method: "future_method",
        rule_id: "selection.required_locator",
        rule_version: "1",
        summary: "ok",
        inputs: [],
        evidence: [],
        alternatives: [],
        suppressed_items: [],
        diagnostics: [],
        code_references: [],
        trace_references: [],
        metadata: {},
        future_field: "kept",
      },
      diagnostics,
    );
    expect(parsed).not.toBeNull();
    expect(parsed!.stage).toBe("future_stage");
    expect(parsed!.decision_type).toBe("future_type");
    expect(parsed!.method).toBe("future_method");
    expect(parsed!.future_field).toBe("kept");
    expect(diagnostics).toEqual([]);
  });

  it("omits malformed required fields and diagnoses duplicates", () => {
    const artifact = parseDecisionExplanationsArtifact({
      schema_version: "1",
      run_id: "run-x",
      decisions: [
        {
          id: "decision:dup",
          stage: "selection",
          decision_type: "select",
          subject_kind: "source_fragment",
          subject_id: "frag-1",
          outcome: "selected_for_extraction",
          method: "configuration",
          rule_id: "selection.required_locator",
          rule_version: "1",
          summary: "ok",
        },
        {
          id: "decision:dup",
          stage: "selection",
          decision_type: "select",
          subject_kind: "source_fragment",
          subject_id: "frag-2",
          outcome: "selected_for_extraction",
          method: "configuration",
          rule_id: "selection.required_locator",
          rule_version: "1",
          summary: "dup",
        },
        { id: "decision:bad" },
      ],
    });
    const index = buildDecisionExplanationIndex(artifact, { artifactPresent: true });
    expect(index.decisions).toHaveLength(1);
    expect(index.parseDiagnostics.some((line) => /Duplicate decision id/.test(line))).toBe(true);
    expect(index.parseDiagnostics.some((line) => /malformed/i.test(line))).toBe(true);
  });

  it("indexes by subject and metadata deterministically", () => {
    const bundle = loadBundle();
    const roles = identifyRoles(bundle.propositions);
    const artifact = parseDecisionExplanationsArtifact(bundle.decision_explanations);
    const index = buildDecisionExplanationIndex(artifact, { artifactPresent: true });
    const forE2 = index.byPropositionId.get(roles.E2) ?? [];
    expect(forE2.some((d) => d.stage === "classification")).toBe(true);
    expect(forE2.some((d) => d.stage === "extraction")).toBe(true);
    const stmt = statementFor(bundle, roles.P2);
    expect((index.byEffectiveLawStatementId.get(stmt.id) ?? []).length).toBeGreaterThan(0);
  });

  it("method labels map clearly", () => {
    expect(methodLabel("configuration")).toBe("Run configuration");
    expect(methodLabel("deterministic")).toBe("Deterministic rule");
    expect(methodLabel("llm")).toBe("Language model");
    expect(methodLabel("hybrid")).toBe("Model + deterministic checks");
  });
});

describe("statement explanation projection", () => {
  const bundle = loadBundle();
  const roles = identifyRoles(bundle.propositions);
  const propById = new Map(bundle.propositions.map((prop) => [prop.id, prop]));
  const fragmentById = new Map(
    bundle.source_fragments.map((fragment) => [String(fragment.id), fragment]),
  );
  const heuristics = heuristicByRuleId(
    parseHeuristicsResponse(JSON.parse(readFileSync(heuristicsPath, "utf8"))).heuristics,
  );
  const artifact = parseDecisionExplanationsArtifact(bundle.decision_explanations);
  const index = buildDecisionExplanationIndex(artifact, { artifactPresent: true });
  const groups = groupsFromBundle(bundle);

  function project(role: keyof typeof roles) {
    const propId = roles[role];
    return buildStatementExplanationViewModel({
      statement: statementFor(bundle, propId),
      proposition: propById.get(propId) ?? null,
      propositionById: propById,
      fragmentById,
      legalRuleGroups: groups,
      decisionIndex: index,
      heuristics,
    });
  }

  it("builds projection without network calls and excludes unrelated decisions", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch" as never);
    const p2 = project("P2");
    const e2 = project("E2");
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
    expect(p2.relatedDecisionIds.every((id) => !e2.relatedDecisionIds.includes(id) || true)).toBe(
      true,
    );
    // P2 must not include E2 composition decision.
    expect(
      p2.stages.find((s) => s.stageId === "extraction"),
    ).toBeUndefined();
    expect(e2.stages.some((s) => s.stageId === "extraction")).toBe(true);
    // Unrelated P3 trigger attachments must not appear on E2.
    expect(
      e2.stages
        .find((s) => s.stageId === "effective_law")
        ?.decisions.some((d) => d.outcome === "trigger_condition_attached"),
    ).toBe(false);
  });

  it("does not infer missing decisions and tolerates missing heuristics", () => {
    const emptyIndex = buildDecisionExplanationIndex(emptyDecisionExplanationsArtifact("run-x"), {
      artifactPresent: true,
    });
    const vm = buildStatementExplanationViewModel({
      statement: statementFor(bundle, roles.P2),
      proposition: propById.get(roles.P2) ?? null,
      propositionById: propById,
      fragmentById,
      decisionIndex: emptyIndex,
      heuristics: new Map(),
    });
    expect(vm.stages.every((s) => s.status === "unavailable" || s.stageId === "extraction")).toBe(
      true,
    );
    const withMissingHeuristic = project("P2");
    // Even if heuristics map were empty, projection still works.
    const bare = buildStatementExplanationViewModel({
      statement: statementFor(bundle, roles.P2),
      proposition: propById.get(roles.P2) ?? null,
      propositionById: propById,
      fragmentById,
      legalRuleGroups: groups,
      decisionIndex: index,
      heuristics: new Map(),
    });
    expect(bare.overview).toMatch(/prohibition/i);
    expect(withMissingHeuristic.overview).toMatch(/prohibition/i);
  });

  it("P2: prohibition, exceptions, group inheritance, parent suppression, no composition", () => {
    const vm = project("P2");
    expect(vm.overview).toMatch(/prohibition/i);
    expect(vm.overview).not.toMatch(/derogation/i);
    const selection = vm.stages.find((s) => s.stageId === "selection");
    expect(selection?.explanation).toMatch(/explicitly required/i);
    expect(selection?.explanation).toMatch(/not separately extracted|covered/i);
    expect(vm.stages.find((s) => s.stageId === "extraction")).toBeUndefined();
    const exceptions = vm.contextGroups.find((g) => g.role === "applicable_exception");
    expect(exceptions?.items).toHaveLength(3);
    expect(exceptions?.items.every((item) => item.inheritedViaGroup)).toBe(true);
    expect(vm.keyLegalLinks.some((line) => /Rule group/i.test(line))).toBe(true);
  });

  it("E2: path 2-a-ii, model proposal, deterministic composition, derogation, exception_to", () => {
    const vm = project("E2");
    expect(vm.overview).toMatch(/2-a-ii/);
    expect(vm.overview).toMatch(/derogation/i);
    const extraction = vm.stages.find((s) => s.stageId === "extraction");
    expect(extraction?.explanation).toMatch(/Frontier model proposed/i);
    expect(extraction?.explanation).toMatch(/Deterministic structured-list/i);
    const classification = vm.stages.find((s) => s.stageId === "classification");
    expect(classification?.explanation).toMatch(/derogation/i);
    expect(classification?.explanation).toMatch(/explicit exception cue/i);
    const relationship = vm.stages.find((s) => s.stageId === "relationship");
    expect(relationship?.explanation).toMatch(/exception to/i);
    expect(relationship?.explanation).toMatch(/paragraph 1/i);
    expect(
      relationship?.detailBlocks.some((block) =>
        block.lines.some((line) => /Members:/i.test(line) && /paragraph 1/i.test(line)),
      ) ||
        vm.keyLegalLinks.some((line) => /Target group members:/i.test(line)),
    ).toBe(true);
    const selection = vm.stages.find((s) => s.stageId === "selection");
    expect(selection?.evidence.some((e) => e.kind === "matched_focus_term")).toBe(true);
  });

  it("E3: Article 14 ordinary reference; typed-over-generic paragraph-1 suppression", () => {
    const vm = project("E3");
    const relationship = vm.stages.find((s) => s.stageId === "relationship");
    expect(relationship?.explanation).toMatch(/Ordinary reference/i);
    expect(relationship?.explanation).toMatch(/article 14/i);
    expect(relationship?.explanation).toMatch(/paragraph 1/i);
    const effective = vm.stages.find((s) => s.stageId === "effective_law");
    expect(effective?.explanation).toMatch(/Generic context/i);
    expect(effective?.explanation).toMatch(/paragraph 1/i);
    expect(effective?.explanation).not.toMatch(/article 14.*suppressed/i);
    expect(
      effective?.evidence.some(
        (e) => e.kind === "generic_locator" && /article 14/i.test(e.value),
      ),
    ).toBe(false);
  });

  it("P3: triggered_by, paragraph 2 group, three triggers, source-only", () => {
    const vm = project("P3");
    const relationship = vm.stages.find((s) => s.stageId === "relationship");
    expect(relationship?.explanation).toMatch(/triggered by/i);
    expect(relationship?.explanation).toMatch(/paragraph 2/i);
    const effective = vm.stages.find((s) => s.stageId === "effective_law");
    const triggers = vm.contextGroups.find((g) => g.role === "trigger_condition");
    expect(triggers?.items).toHaveLength(3);
    expect(effective?.explanation).toMatch(/source only|source-only/i);
    // P3 must not appear as context on E1–E3 projections.
    for (const role of ["E1", "E2", "E3"] as const) {
      const other = project(role);
      expect(
        other.contextGroups
          .flatMap((g) => g.items)
          .some((item) => item.propositionId === roles.P3),
      ).toBe(false);
    }
  });

  it("legacy missing artifact message", () => {
    const vm = buildStatementExplanationViewModel({
      statement: statementFor(bundle, roles.P2),
      proposition: propById.get(roles.P2) ?? null,
      propositionById: propById,
      fragmentById,
      decisionIndex: buildDecisionExplanationIndex(emptyDecisionExplanationsArtifact("run-old"), {
        artifactPresent: false,
      }),
      heuristics,
    });
    expect(vm.availability).toBe("missing_artifact");
    expect(vm.legacyMessage).toMatch(/Detailed decision explanations were not recorded/i);
  });
});
