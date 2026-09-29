/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  SourceLegalEffectsPanel,
  SourceLegalEffectsSummary,
} from "@/components/source-legal-effects-panel";
import { SourceVersionSummary } from "@/components/source-version-summary";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import fixture from "@/lib/fixtures/article-49a-source-legal-effects.json";
import type { PropositionRow, SourceRow, SourceSnapshotRow } from "@/lib/law-statements-index";
import {
  buildSourceLegalEffectsView,
  type SourceLegalEffectsArtifactRow,
} from "@/lib/source-legal-effects";
import { buildSourceVersionProvenance } from "@/lib/source-version-provenance";

const artifact: SourceLegalEffectsArtifactRow = {
  schema_version: fixture.schema_version,
  run_id: fixture.run_id,
  effects: fixture.effects,
  effect_links: fixture.effect_links,
  outstanding_effects_status: fixture.outstanding_effects_status,
  diagnostics: fixture.diagnostics,
  metadata: fixture.metadata,
};

const fragments = fixture.source_fragments as SourceFragmentRow[];
const source = fixture.source_records[0] as SourceRow;
const snapshot = fixture.source_snapshots[0] as SourceSnapshotRow;
const p1 = fixture.propositions[0] as PropositionRow;

function fragmentMap(): Map<string, SourceFragmentRow> {
  return new Map(fragments.map((row) => [String(row.id), row]));
}

afterEach(() => {
  cleanup();
});

describe("SourceLegalEffects rendering", () => {
  const effectsView = buildSourceLegalEffectsView({
    sourceRecordId: "src-demo-1224",
    sourceSnapshotId: "snap-demo-1224-revised",
    propositions: [p1],
    artifact,
    fragmentById: fragmentMap(),
  });

  it("renders compact summary with relevant count and unknown outstanding status", () => {
    render(<SourceLegalEffectsSummary view={effectsView} />);
    const summary = screen.getByTestId("source-legal-effects-summary");
    expect(within(summary).getByText(/4 change annotations recorded/i)).toBeTruthy();
    expect(within(summary).getByText(/2 relevant to this provision/i)).toBeTruthy();
    expect(summary.textContent).toMatch(/Relevant annotations:\s*F1, F2/);
    const outstanding = screen.getByTestId("outstanding-effects-status");
    expect(
      within(outstanding).getByText(/Not established from the consumed source metadata/i),
    ).toBeTruthy();
    expect(outstanding.textContent?.toLowerCase().includes("no outstanding effects")).toBe(false);
  });

  it("lists relevant effects and distinguishes direct vs structural", () => {
    render(<SourceLegalEffectsPanel view={effectsView} />);
    fireEvent.click(screen.getByRole("button", { name: /Changes recorded in consumed source/i }));
    const banner = screen.getByTestId("source-legal-effects-truthfulness");
    expect(banner.textContent).toMatch(/present in the legislation\.gov\.uk XML consumed by Law Proposition Extractor/i);
    expect(banner.textContent).toMatch(/do not show that Law Proposition Extractor independently applied the changes/i);

    const cards = screen.getAllByTestId("source-legal-effect-card");
    expect(cards[0]?.getAttribute("data-annotation-label")).toBe("F1");
    expect(cards[0]?.getAttribute("data-relevance")).toBe("structural");
    expect(cards[0]?.textContent).toMatch(/Linked through source structure/i);
    expect(cards[1]?.getAttribute("data-annotation-label")).toBe("F2");
    expect(cards[1]?.getAttribute("data-relevance")).toBe("direct");
    expect(cards[1]?.textContent).toMatch(/Directly linked to Article 49a, paragraph 1/i);
    expect(cards[1]?.textContent).toMatch(/Substitution/);
    expect(cards[1]?.textContent).toMatch(/UKSI 2019\/739/);
    expect(cards[1]?.textContent).toMatch(/Not stated by consumed source/);
    expect(cards[1]?.textContent).toMatch(
      /No matching independently consumed source was found in this run/,
    );
    expect(cards[1]?.textContent).not.toMatch(/(^|\n)Applied(\n|$)/);

    const affecting = within(cards[1]!).getByTestId("open-affecting-instrument");
    expect(affecting.textContent).toMatch(/Open affecting instrument on legislation\.gov\.uk/i);
    expect(affecting.textContent).not.toMatch(/Law Proposition Extractor applied/i);
  });

  it("keeps other snapshot effects in the collapsed source-wide subsection", () => {
    render(<SourceLegalEffectsPanel view={effectsView} />);
    fireEvent.click(screen.getByRole("button", { name: /Changes recorded in consumed source/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /Other changes recorded for this source snapshot/i }),
    );
    const otherLabels = screen
      .getAllByTestId("source-legal-effect-card")
      .map((node) => node.getAttribute("data-annotation-label"));
    expect(otherLabels).toEqual(expect.arrayContaining(["F1", "F2", "F3", "F4"]));
  });

  it("integrates beneath source-version summary without claiming applied amendments", () => {
    const provenance = buildSourceVersionProvenance({
      source,
      snapshot,
      propositions: [p1],
      fragmentById: fragmentMap(),
      sourceLegalEffectsKnowledge: {
        hasEffects: true,
        hasFragmentLinks: true,
        hasAffectingInstrumentIds: true,
        outstandingEffectsStatus: "source_status_unknown",
        anyAffectingInstrumentConsumed: false,
      },
    });
    render(
      <SourceVersionSummary
        view={provenance}
        runId="run-demo-49a-effects"
        apiBaseUrl="http://127.0.0.1:8010"
        sourceLegalEffectsView={effectsView}
      />,
    );
    expect(screen.getByTestId("source-version-summary")).toBeTruthy();
    expect(screen.getByTestId("revised-manifestation-disclaimer-summary").textContent).toMatch(
      /has not independently verified or applied the amendment history/i,
    );
    expect(screen.getByTestId("source-legal-effects-summary")).toBeTruthy();
    expect(screen.getByTestId("open-live-legislation-page").textContent).toMatch(
      /Open live legislation page/i,
    );
  });

  it("renders consumed match details without claiming the amendment was applied", () => {
    const consumedArtifact: SourceLegalEffectsArtifactRow = {
      ...artifact,
      effects: artifact.effects.map((effect) =>
        effect.annotation_label === "F2"
          ? {
              ...effect,
              independent_consumption_status: "consumed_in_current_run",
              matched_source_record_id: "src-uksi-2019-739",
              matched_source_snapshot_ids: ["snap-uksi-2019-739"],
              consumption_match_basis: "canonical_authority_uri",
              matched_instrument_identity: "uksi/2019/739",
              consumption_match_evidence: [
                {
                  basis: "canonical_authority_uri",
                  effect_value: String(effect.affecting_instrument_uri ?? ""),
                  normalized_identity: "uksi/2019/739",
                  matched_source_record_id: "src-uksi-2019-739",
                  matched_source_title:
                    "The Common Fisheries Policy (Amendment etc.) (EU Exit) Regulations 2019",
                  matched_source_citation: "UKSI 2019/739",
                  matched_source_snapshot_ids: ["snap-uksi-2019-739"],
                },
              ],
            }
          : effect,
      ),
    };
    const consumedView = buildSourceLegalEffectsView({
      sourceRecordId: "src-demo-1224",
      sourceSnapshotId: "snap-demo-1224-revised",
      propositions: [p1],
      artifact: consumedArtifact,
      fragmentById: fragmentMap(),
    });
    render(<SourceLegalEffectsPanel view={consumedView} />);
    fireEvent.click(screen.getByRole("button", { name: /Changes recorded in consumed source/i }));
    const f2 = screen
      .getAllByTestId("source-legal-effect-card")
      .find((node) => node.getAttribute("data-annotation-label") === "F2");
    expect(f2).toBeTruthy();
    expect(within(f2!).getByTestId("independent-consumption-status").textContent).toMatch(
      /independently consumed in this run/i,
    );
    expect(within(f2!).getByTestId("matched-consumed-source").textContent).toMatch(/UKSI 2019\/739/);
    expect(within(f2!).getByTestId("matched-snapshot-count").textContent).toBe("1");
    expect(within(f2!).getByTestId("consumption-not-application-note").textContent).toMatch(
      /does not mean Law Proposition Extractor applied or verified/i,
    );
    expect(f2!.textContent).not.toMatch(/(^|\n)Applied(\n|$)/);
  });
});
