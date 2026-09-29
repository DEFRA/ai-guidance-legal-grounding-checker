/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";

import { StatementWhyPanel } from "@/components/statement-why-panel";
import {
  buildDecisionExplanationIndex,
  emptyDecisionExplanationsArtifact,
  heuristicByRuleId,
  parseDecisionExplanationsArtifact,
  parseHeuristicsResponse,
} from "@/lib/decision-explanations";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";

const here = path.dirname(fileURLToPath(import.meta.url));
const bundlePath = path.resolve(
  here,
  "../lib/fixtures/article-49a-acceptance/serialized-bundle.json",
);
const heuristicsPath = path.resolve(
  here,
  "../lib/fixtures/article-49a-acceptance/heuristics-referenced.json",
);

type Bundle = {
  propositions: PropositionRow[];
  effective_law_statements: LawStatementRow[];
  source_fragments: SourceFragmentRow[];
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
  const p3 = props.find((p) =>
    String(p.fragment_locator ?? "").startsWith("article:49a:paragraph:3"),
  )!;
  return {
    P1: separate.id,
    P2: mixing.id,
    E1: byPath.get("2-a-i")!.id,
    E2: byPath.get("2-a-ii")!.id,
    E3: byPath.get("2-b")!.id,
    P3: p3.id,
  };
}

afterEach(() => {
  cleanup();
});

describe("StatementWhyPanel", () => {
  const bundle = loadBundle();
  const roles = identifyRoles(bundle.propositions);
  const propById = new Map(bundle.propositions.map((prop) => [prop.id, prop]));
  const fragmentById = new Map(
    bundle.source_fragments.map((fragment) => [String(fragment.id), fragment]),
  );
  const heuristics = heuristicByRuleId(
    parseHeuristicsResponse(JSON.parse(readFileSync(heuristicsPath, "utf8"))).heuristics,
  );
  const index = buildDecisionExplanationIndex(
    parseDecisionExplanationsArtifact(bundle.decision_explanations),
    { artifactPresent: true },
  );
  const e2Statement = bundle.effective_law_statements.find((statement) =>
    (statement.source_proposition_ids ?? []).includes(roles.E2),
  )!;
  const e2Prop = propById.get(roles.E2)!;

  it("renders entry point and opens with keyboard-friendly disclosure", () => {
    render(
      <StatementWhyPanel
        statement={e2Statement}
        primaryProposition={e2Prop}
        propositionById={propById}
        fragmentById={fragmentById}
        decisionExplanationIndex={index}
        heuristics={heuristics}
      />,
    );
    const toggle = screen.getByRole("button", { name: /Why did Law Proposition Extractor produce this/i });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const content = screen.getByTestId("statement-why-content");
    expect(within(content).getByText(/Overview/i)).toBeTruthy();
    expect(screen.getByText(/do not replace legal review/i)).toBeTruthy();
  });

  it("default view omits raw IDs; technical details reveal rule IDs", () => {
    render(
      <StatementWhyPanel
        statement={e2Statement}
        primaryProposition={e2Prop}
        propositionById={propById}
        fragmentById={fragmentById}
        decisionExplanationIndex={index}
        heuristics={heuristics}
        defaultOpen
      />,
    );
    const content = screen.getByTestId("statement-why-content");
    const overview = within(content).getByText(/Overview/i).parentElement!;
    const timeline = within(content).getByText(/Stage timeline/i).parentElement!;
    expect(overview.textContent).not.toMatch(/decision:[a-f0-9]{8}/i);
    expect(timeline.textContent).not.toMatch(/decision:[a-f0-9]{8}/i);
    expect(within(content).getByText(/Legal classification/i)).toBeTruthy();
    const tech = screen.getByTestId("statement-why-technical");
    fireEvent.click(within(tech).getByText(/Technical details/i));
    expect(tech.textContent).toMatch(/rule:/i);
    expect(tech.textContent).toMatch(
      /classification\.derive_legal_effect@1|structured_list\.compose_terminal_leaf@1/,
    );
    expect(document.body.innerHTML).not.toMatch(/file:\/\//i);
  });

  it("shows legacy message when explanations are missing", () => {
    render(
      <StatementWhyPanel
        statement={e2Statement}
        primaryProposition={e2Prop}
        propositionById={propById}
        fragmentById={fragmentById}
        decisionExplanationIndex={buildDecisionExplanationIndex(
          emptyDecisionExplanationsArtifact("run-old"),
          { artifactPresent: false },
        )}
        heuristics={heuristics}
        defaultOpen
      />,
    );
    expect(
      screen.getByText(/Detailed decision explanations were not recorded for this run/i),
    ).toBeTruthy();
  });

  it("partial explanations render available stages only", () => {
    const partialArtifact = parseDecisionExplanationsArtifact(bundle.decision_explanations);
    const kept = partialArtifact.decisions.filter(
      (d) => d.stage === "classification" && d.subject_id === roles.E2,
    );
    const rebuilt = parseDecisionExplanationsArtifact({
      ...partialArtifact,
      decisions: kept,
      metadata: { ...(partialArtifact.metadata ?? {}), missing_artifact: false },
    });
    const partialIndex = buildDecisionExplanationIndex(rebuilt, {
      artifactPresent: true,
    });
    expect(partialIndex.decisions.length).toBeGreaterThan(0);
    render(
      <StatementWhyPanel
        statement={e2Statement}
        primaryProposition={e2Prop}
        propositionById={propById}
        fragmentById={fragmentById}
        decisionExplanationIndex={partialIndex}
        heuristics={heuristics}
        defaultOpen
      />,
    );
    const content = screen.getByTestId("statement-why-content");
    expect(within(content).getByText(/Legal classification/i)).toBeTruthy();
    expect(within(content).queryByText(/Extraction and composition/i)).toBeNull();
    expect(within(content).getAllByText(/Not recorded/i).length).toBeGreaterThan(0);
  });
});
