/**
 * Frontend/view-model acceptance for the Article 49a offline regression fixture.
 * Consumes serialized backend export output — not a hand-authored reinterpretation.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import {
  assessStatementQuality,
  type LawStatementRow,
  type PropositionRow,
  type SourceRow,
  type SourceSnapshotRow,
} from "@/lib/law-statements-index";
import {
  buildSourceLegalEffectsView,
  normalizeOutstandingEffectsStatus,
  outstandingEffectsStatusLabel,
  parseSourceLegalEffectsArtifact,
  type SourceLegalEffectsArtifactRow,
} from "@/lib/source-legal-effects";
import {
  buildDecisionExplanationIndex,
  heuristicByRuleId,
  parseDecisionExplanationsArtifact,
  parseHeuristicsResponse,
} from "@/lib/decision-explanations";
import { buildStatementExplanationViewModel } from "@/lib/statement-explanation";
import {
  buildSourceVersionProvenance,
  isLocalOrFileUri,
} from "@/lib/source-version-provenance";
import {
  buildTypedLegalContextSections,
  sectionHeadingForTypedRole,
} from "@/lib/typed-legal-context";

const here = path.dirname(fileURLToPath(import.meta.url));
const bundlePath = path.resolve(here, "fixtures/article-49a-acceptance/serialized-bundle.json");
const heuristicsPath = path.resolve(
  here,
  "fixtures/article-49a-acceptance/heuristics-referenced.json",
);

type Bundle = {
  propositions: PropositionRow[];
  effective_law_statements: LawStatementRow[];
  source_legal_effects: SourceLegalEffectsArtifactRow;
  source_snapshots: SourceSnapshotRow[];
  sources: SourceRow[];
  source_fragments: SourceFragmentRow[];
  legal_rule_groups?: { groups?: Array<{ id: string; member_proposition_ids?: string[] }> };
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

describe("Article 49a acceptance view models (serialized backend fixture)", () => {
  const bundle = loadBundle();
  const roles = identifyRoles(bundle.propositions);
  const propById = new Map(bundle.propositions.map((prop) => [prop.id, prop]));
  const fragmentById = new Map(
    bundle.source_fragments.map((fragment) => [String(fragment.id), fragment]),
  );
  const source = bundle.sources[0]!;
  const snapshot = bundle.source_snapshots[0]!;
  const effectsArtifact = parseSourceLegalEffectsArtifact(bundle.source_legal_effects);

  it("P1/P2: applicable exceptions, version labels, and Article 49a-relevant effects", () => {
    for (const role of ["P1", "P2"] as const) {
      const statement = statementFor(bundle, roles[role]);
      const sections = buildTypedLegalContextSections(statement, propById);
      expect(sections.applicableExceptions).toHaveLength(3);
      expect(sections.applicableExceptions.every((item) => item.inheritedViaGroup)).toBe(true);
      const heading = sectionHeadingForTypedRole("exception", sections.applicableExceptions.length);
      expect(heading.title).toMatch(/Applicable exceptions/);

      const assessment = assessStatementQuality(statement, propById);
      expect(assessment.flags).not.toContain("ambiguous_context");

      const props = [propById.get(roles[role])!];
      const version = buildSourceVersionProvenance({
        source,
        snapshot,
        propositions: props,
        fragmentById,
        sourceLegalEffectsKnowledge: {
          artifact: effectsArtifact,
          fragmentById,
        },
      });
      expect(version.manifestationTypeLabel).toBe("Revised text");
      expect(version.asOfDateLabel).toBe("Not recorded");
      expect(version.consumedSourceUrl).toContain("data.xml");
      expect(version.liveHtmlUrl).toBeTruthy();
      expect(version.liveHtmlUrl).not.toEqual(version.consumedSourceUrl);
      expect(isLocalOrFileUri(version.liveHtmlUrl)).toBe(false);
      expect(isLocalOrFileUri(version.consumedSourceUrl)).toBe(false);
      if (version.rawArtifactUri) {
        // raw cache URI may be file:// but must not be exposed as reviewer live action URL
        expect(version.liveHtmlUrl).not.toMatch(/^file:/);
      }

      const effectsView = buildSourceLegalEffectsView({
        sourceRecordId: source.id,
        sourceSnapshotId: snapshot.id ?? null,
        propositions: props,
        artifact: effectsArtifact,
        fragmentById,
      });
      const labels = effectsView.relevant.map((item) => item.effect.annotation_label);
      const ids = effectsView.relevant.map((item) => item.effect.annotation_id);
      expect(ids).toContain("c000004");
      if (role === "P1") {
        expect(ids).toContain("key-ae688d7efb8d525f494201f970bc3e75");
      }
      expect(ids).not.toContain("c000001");
      expect(labels.every((label) => label !== "F1" || ids.includes("c000001"))).toBe(true);
      // No Article 1 annotations in relevant set
      expect(
        effectsView.relevant.every((item) => item.effect.affected_locator !== "article:1"),
      ).toBe(true);
    }
  });

  it("E3: displaced rules, Article 14 ordinary context, paragraph-2 effect", () => {
    const statement = statementFor(bundle, roles.E3);
    const sections = buildTypedLegalContextSections(statement, propById);
    const displacedIds = sections.exceptionTargets.map((item) => item.propositionId);
    expect(displacedIds).toEqual(expect.arrayContaining([roles.P1, roles.P2]));

    const art14 = (statement.required_context ?? []).filter((entry) => {
      const locator = String(entry.locator ?? "").toLowerCase();
      return locator.includes("article 14") || locator.includes("article:14");
    });
    expect(art14.length).toBeGreaterThan(0);
    expect(art14.every((entry) => entry.kind === "referenced_locator")).toBe(true);
    expect(art14.every((entry) => entry.kind !== "exception_target")).toBe(true);

    const effectsView = buildSourceLegalEffectsView({
      sourceRecordId: source.id,
      sourceSnapshotId: snapshot.id ?? null,
      propositions: [propById.get(roles.E3)!],
      artifact: effectsArtifact,
      fragmentById,
    });
    expect(
      effectsView.relevant.some(
        (item) => item.effect.annotation_id === "key-cd016a627475b52260f225a4d4ac7ed7",
      ),
    ).toBe(true);
    expect(
      effectsView.relevant.every(
        (item) =>
          item.effect.independent_consumption_status === "not_matched" ||
          item.effect.independent_consumption_status ===
            "present_in_source_register_but_not_consumed",
      ),
    ).toBe(true);
  });

  it("P3: trigger conditions and paragraph-3 effect; no Article 1 leakage", () => {
    const statement = statementFor(bundle, roles.P3);
    const sections = buildTypedLegalContextSections(statement, propById);
    expect(sections.triggerConditions).toHaveLength(3);
    const heading = sectionHeadingForTypedRole("trigger", sections.triggerConditions.length);
    expect(heading.title).toMatch(/Triggered in these cases|Trigger/);

    const effectsView = buildSourceLegalEffectsView({
      sourceRecordId: source.id,
      sourceSnapshotId: snapshot.id ?? null,
      propositions: [propById.get(roles.P3)!],
      artifact: effectsArtifact,
      fragmentById,
    });
    expect(
      effectsView.relevant.some(
        (item) => item.effect.annotation_id === "key-c36fcfcb069fb8c51fce93fbce7ea03b",
      ),
    ).toBe(true);
    expect(
      effectsView.relevant.every((item) => item.effect.affected_locator !== "article:1"),
    ).toBe(true);
  });

  it("renders outstanding-effect status truthfully and keeps raw ids secondary", () => {
    const status = normalizeOutstandingEffectsStatus(
      effectsArtifact.outstanding_effects_status,
    );
    expect(status).toBe("source_reports_present");
    expect(outstandingEffectsStatusLabel(status)).toMatch(/outstanding/i);
    expect(status).not.toBe("none");

    const statement = statementFor(bundle, roles.P1);
    const sections = buildTypedLegalContextSections(statement, propById);
    // Group / relationship ids exist for provenance but are not the primary UI title.
    expect(sections.applicableExceptions[0]?.legalRuleGroupId).toMatch(/^rulegrp:/);
    expect(sectionHeadingForTypedRole("exception", 3).title).not.toMatch(/^rulegrp:/);
  });

  it("Workbench explanation projection for P2/E2/E3/P3 from serialized decisions", () => {
    const decisionIndex = buildDecisionExplanationIndex(
      parseDecisionExplanationsArtifact(bundle.decision_explanations),
      { artifactPresent: true },
    );
    expect(decisionIndex.decisions.length).toBe(43);
    const heuristics = heuristicByRuleId(
      parseHeuristicsResponse(JSON.parse(readFileSync(heuristicsPath, "utf8"))).heuristics,
    );
    const groups = Array.isArray(bundle.legal_rule_groups)
      ? bundle.legal_rule_groups
      : (bundle.legal_rule_groups?.groups ?? []);

    const project = (role: "P2" | "E2" | "E3" | "P3") =>
      buildStatementExplanationViewModel({
        statement: statementFor(bundle, roles[role]),
        proposition: propById.get(roles[role]) ?? null,
        propositionById: propById,
        fragmentById,
        legalRuleGroups: groups,
        decisionIndex,
        heuristics,
      });

    const p2 = project("P2");
    expect(p2.overview).toMatch(/prohibition/i);
    expect(p2.overview).not.toMatch(/derogation/i);
    expect(p2.contextGroups.find((g) => g.role === "applicable_exception")?.items).toHaveLength(3);
    expect(p2.stages.find((s) => s.stageId === "extraction")).toBeUndefined();

    const e2 = project("E2");
    expect(e2.overview).toMatch(/2-a-ii/);
    expect(e2.stages.find((s) => s.stageId === "extraction")?.explanation).toMatch(
      /Frontier model proposed/i,
    );
    expect(e2.stages.find((s) => s.stageId === "classification")?.explanation).toMatch(
      /derogation/i,
    );
    expect(e2.stages.find((s) => s.stageId === "relationship")?.explanation).toMatch(
      /exception to/i,
    );

    const e3 = project("E3");
    expect(e3.stages.find((s) => s.stageId === "relationship")?.explanation).toMatch(
      /article 14/i,
    );
    expect(e3.stages.find((s) => s.stageId === "effective_law")?.explanation).toMatch(
      /Generic context/i,
    );

    const p3 = project("P3");
    expect(p3.stages.find((s) => s.stageId === "relationship")?.explanation).toMatch(
      /triggered by/i,
    );
    expect(p3.contextGroups.find((g) => g.role === "trigger_condition")?.items).toHaveLength(3);
    expect(p3.stages.find((s) => s.stageId === "effective_law")?.explanation).toMatch(
      /source only|source-only/i,
    );

    for (const role of ["P2", "E2", "E3", "P3"] as const) {
      const vm = project(role);
      expect(vm.legislativeHeading?.display).toBe(
        "Article 49a — Separate stowage of catches below the minimum conservation reference sizes",
      );
      expect(vm.legislativeHeading?.note).toMatch(/not treated as a standalone legal proposition/i);
    }
  });
});
