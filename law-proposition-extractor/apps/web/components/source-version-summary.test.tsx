import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ConsumedSourceProvenance,
  SourceVersionSummary,
} from "@/components/source-version-summary";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type {
  PropositionRow,
  SourceRow,
  SourceSnapshotRow,
} from "@/lib/law-statements-index";
import fixture from "@/lib/fixtures/article-49a-source-version-provenance.json";
import { buildSourceVersionProvenance } from "@/lib/source-version-provenance";

const source = fixture.source_records[0] as SourceRow;
const snapshot = fixture.source_snapshots[0] as SourceSnapshotRow;
const fragment = fixture.source_fragments[0] as SourceFragmentRow;
const proposition = fixture.propositions[0] as PropositionRow;

const view = buildSourceVersionProvenance({
  source,
  snapshot,
  propositions: [proposition],
  fragmentById: new Map([[String(fragment.id), fragment]]),
});

describe("SourceVersionSummary Article 49a rendering", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders compact source version summary without mislabeling v1", () => {
    render(<SourceVersionSummary view={view} runId="run-demo" apiBaseUrl="http://127.0.0.1:8010" />);

    const summary = screen.getByTestId("source-version-summary");
    expect(within(summary).getByText(/Source version/i)).toBeTruthy();
    expect(within(summary).getByText(/legislation\.gov\.uk · consumed as data\.xml/i)).toBeTruthy();
    expect(within(summary).getByText("snap-demo-1224-v1")).toBeTruthy();
    expect(within(summary).getByText(/As-of date:/i).parentElement?.textContent).toMatch(
      /Not recorded/,
    );
    expect(within(summary).getByText(/Manifestation:/i).parentElement?.textContent).toMatch(
      /Not recorded/,
    );
    expect(summary.textContent).not.toMatch(/legislative manifestation version of v1/i);
    expect(summary.textContent).not.toMatch(/Current law as of/i);
    expect(summary.textContent).not.toMatch(/All amendments applied/i);
    expect(summary.textContent).not.toContain(
      "file:///private/var/folders/zg/example/T/law-proposition-extractor/source-snapshots/example.json",
    );
  });

  it("labels live legislation distinctly from consumed source", () => {
    render(<SourceVersionSummary view={view} runId="run-demo" apiBaseUrl="http://127.0.0.1:8010" />);

    const live = screen.getByTestId("open-live-legislation-page");
    expect(live.getAttribute("href")).toBe(
      "https://www.legislation.gov.uk/eur/2009/1224/article/49a/1",
    );
    expect(live.textContent).toMatch(/Open live legislation page/i);
    expect(screen.getByText(/may not exactly match the snapshot Law Proposition Extractor consumed/i)).toBeTruthy();
  });

  it("expands What Law Proposition Extractor consumed with truthfulness constraints", () => {
    render(<SourceVersionSummary view={view} runId="run-demo" apiBaseUrl="http://127.0.0.1:8010" />);

    fireEvent.click(screen.getByRole("button", { name: /What Law Proposition Extractor consumed/i }));

    expect(screen.getByText("https://www.legislation.gov.uk/eur/2009/1224/data.xml")).toBeTruthy();
    expect(screen.getAllByText("legislation_gov_uk_data_xml_v1").length).toBeGreaterThan(0);
    expect(screen.getByText(/Article 49a, paragraph 1/i)).toBeTruthy();
    expect(screen.getByText(/\(frag-demo-49a-p1\)/)).toBeTruthy();
    expect(screen.getByText(/Intake identifier only/i)).toBeTruthy();

    const status = screen.getByTestId("source-provenance-status-list");
    expect(within(status).getByText(/Exact source snapshot identity/i)).toBeTruthy();
    expect(within(status).getByText(/Resolved as-of date/i)).toBeTruthy();
    expect(within(status).getByText(/Consumed manifestation type/i)).toBeTruthy();
    expect(within(status).getByText(/Outstanding amendment effects/i)).toBeTruthy();
    expect(within(status).getByText(/Affecting instruments independently consumed/i)).toBeTruthy();
    expect(within(status).getByText(/Historical amendment lineage reconstructed/i)).toBeTruthy();
    expect(status.textContent).not.toMatch(/amendments were applied/i);
    expect(status.textContent).not.toContain("file:///private/var/folders");
  });

  it("shows consumed fragment when full snapshot is unavailable", () => {
    render(
      <ConsumedSourceProvenance view={view} runId="run-demo" apiBaseUrl="http://127.0.0.1:8010" />,
    );
    fireEvent.click(screen.getByRole("button", { name: /What Law Proposition Extractor consumed/i }));
    fireEvent.click(screen.getByRole("button", { name: /View consumed source fragment/i }));
    expect(screen.getByTestId("consumed-fragment-viewer").textContent).toContain(
      "minimum conservation reference size",
    );
    expect(screen.getByText(/full raw snapshot is unavailable/i)).toBeTruthy();
  });

  it("renders revised manifestation disclaimer without claiming amendments applied", () => {
    const revisedView = {
      ...view,
      manifestationType: "revised" as const,
      manifestationTypeLabel: "Revised text",
      manifestationBasis: "source_metadata" as const,
      manifestationBasisLabel: "legislation.gov.uk source metadata",
      revisedManifestationDisclaimer:
        "This records the manifestation supplied by legislation.gov.uk. Law Proposition Extractor has not independently verified or applied the amendment history.",
      asOfDate: null,
      asOfDateLabel: "Not recorded",
      knowledgeRecorded: [
        ...view.knowledgeRecorded,
        {
          id: "manifestation_type",
          label: "Consumed manifestation type",
          status: "recorded" as const,
          legislationSpecific: true,
        },
      ],
      knowledgeAbsent: view.knowledgeAbsent.filter((item) => item.id !== "manifestation_type"),
    };
    render(
      <SourceVersionSummary view={revisedView} runId="run-demo" apiBaseUrl="http://127.0.0.1:8010" />,
    );
    expect(screen.getByTestId("revised-manifestation-disclaimer-summary").textContent).toMatch(
      /has not independently verified or applied the amendment history/i,
    );
    expect(screen.getByText(/Manifestation:/i).parentElement?.textContent).toMatch(/Revised text/);
    expect(screen.getByText(/As-of date:/i).parentElement?.textContent).toMatch(/Not recorded/);
    expect(screen.getByText(/Basis:/i).parentElement?.textContent).toMatch(/source metadata/i);
    fireEvent.click(screen.getByRole("button", { name: /What Law Proposition Extractor consumed/i }));
    const status = screen.getByTestId("source-provenance-status-list");
    expect(within(status).getByText(/Outstanding amendment effects/i)).toBeTruthy();
    expect(status.textContent).not.toMatch(/All amendments applied/i);
  });

  it("loads persisted snapshot text through the safe API route when available", async () => {
    const availableView = {
      ...view,
      hasPersistedSnapshotText: true,
      snapshotInspection: "api_available" as const,
      fragmentText: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          available: true,
          content: "<article>49a</article>",
          content_type: "application/xml",
        }),
      })),
    );

    render(
      <ConsumedSourceProvenance
        view={availableView}
        runId="run-demo"
        apiBaseUrl="http://127.0.0.1:8010"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /What Law Proposition Extractor consumed/i }));
    fireEvent.click(screen.getByRole("button", { name: /Inspect consumed snapshot/i }));

    expect(await screen.findByTestId("consumed-snapshot-viewer")).toBeTruthy();
    expect(screen.getByText("<article>49a</article>")).toBeTruthy();
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/ops/source-snapshots/snap-demo-1224-v1/content?run_id=run-demo",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });
});
