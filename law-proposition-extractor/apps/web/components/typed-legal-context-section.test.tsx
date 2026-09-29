import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TypedLegalContextSection } from "@/components/typed-legal-context-section";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import {
  buildTypedLegalContextSections,
  hasTypedLegalContext,
} from "@/lib/typed-legal-context";
import article49aFixture from "@/lib/fixtures/article-49a-typed-effective-law.json";

const P1 = "prop-demo-49a-p1-separate";
const P2 = "prop-demo-49a-p1-no-mixing";
const E1 = "prop-demo-49a-p2-pelagic";
const E2 = "prop-demo-49a-p2-industrial";
const E3 = "prop-demo-49a-p2-small-vessels";
const P3 = "prop-demo-49a-p3-monitoring";

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

describe("TypedLegalContextSection rendering", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders Applicable exceptions for P1 with group inheritance and no raw IDs in primary UI", () => {
    const sections = buildTypedLegalContextSections(statementBySourceProp(P1), propositionById());
    render(<TypedLegalContextSection sections={sections} />);

    expect(screen.getByTestId("typed-legal-context-section-exception")).toBeTruthy();
    expect(screen.getByText(/Applicable exceptions/i)).toBeTruthy();
    expect(screen.getByText("(3)")).toBeTruthy();
    expect(screen.getByText(/Applies through rule group: Article 49a, paragraph 1/i)).toBeTruthy();

    const items = screen.getAllByTestId("typed-legal-context-item-exception");
    expect(items).toHaveLength(3);
    expect(screen.getByText(/small pelagic species/i)).toBeTruthy();
    expect(screen.getByText(/industrial purposes/i)).toBeTruthy();
    expect(screen.getByText(/less than 12 metres/i)).toBeTruthy();

    expect(screen.queryByText(/legalrel:/)).toBeNull();
    expect(screen.queryByText(/rulegrp:/)).toBeNull();
  });

  it("renders the same three applicable exceptions for P2", () => {
    const sections = buildTypedLegalContextSections(statementBySourceProp(P2), propositionById());
    render(<TypedLegalContextSection sections={sections} />);
    expect(screen.getAllByTestId("typed-legal-context-item-exception")).toHaveLength(3);
  });

  it("renders Rules displaced for E3 without Article 14 in typed section", () => {
    const sections = buildTypedLegalContextSections(statementBySourceProp(E3), propositionById());
    render(<TypedLegalContextSection sections={sections} />);

    expect(screen.getByText(/Rules displaced by this exception/i)).toBeTruthy();
    expect(screen.getAllByTestId("typed-legal-context-item-displaced_rule")).toHaveLength(2);
    expect(screen.getByText(/separately identifiable/i)).toBeTruthy();
    expect(screen.getByText(/shall not be mixed/i)).toBeTruthy();
    expect(screen.queryByText(/fishing logbook/i)).toBeNull();
    expect(screen.queryByTestId("typed-legal-context-section-exception")).toBeNull();
  });

  it("renders Triggered in these cases for P3", () => {
    const sections = buildTypedLegalContextSections(statementBySourceProp(P3), propositionById());
    render(<TypedLegalContextSection sections={sections} />);

    expect(screen.getByText(/Triggered in these cases/i)).toBeTruthy();
    expect(screen.getAllByTestId("typed-legal-context-item-trigger")).toHaveLength(3);
    expect(screen.getByText(/Applies through rule group: Article 49a, paragraph 2/i)).toBeTruthy();
  });

  it("does not invent incoming triggered_by on exception propositions", () => {
    for (const propId of [E1, E2, E3]) {
      const sections = buildTypedLegalContextSections(statementBySourceProp(propId), propositionById());
      expect(sections.triggerConditions).toEqual([]);
      const { unmount } = render(<TypedLegalContextSection sections={sections} />);
      expect(screen.queryByTestId("typed-legal-context-section-trigger")).toBeNull();
      unmount();
    }
  });

  it("shows Why linked provenance and confines raw IDs to developer details", () => {
    const sections = buildTypedLegalContextSections(statementBySourceProp(P1), propositionById());
    render(<TypedLegalContextSection sections={sections} showDeveloperFields />);

    const firstItem = screen.getAllByTestId("typed-legal-context-item-exception")[0]!;
    const whyButton = within(firstItem).getByRole("button", { name: /Why linked/i });
    fireEvent.click(whyButton);

    expect(within(firstItem).getAllByText(/exception_to/i).length).toBeGreaterThan(0);
    expect(within(firstItem).getByText(/Structural relative reference/i)).toBeTruthy();
    expect(within(firstItem).getByText(/relationship_id:/i)).toBeTruthy();
    expect(within(firstItem).getByText(/legal_rule_group_id:/i)).toBeTruthy();
  });

  it("does not render empty typed-context sections", () => {
    const empty = {
      applicableExceptions: [],
      exceptionTargets: [],
      triggerConditions: [],
    };
    expect(hasTypedLegalContext(empty)).toBe(false);
    const { container } = render(<TypedLegalContextSection sections={empty} />);
    expect(container.innerHTML).toBe("");
  });

  it("marks direct context without group inheritance claim", () => {
    const sections = buildTypedLegalContextSections(
      statementBySourceProp("prop-demo-art30-p1-only"),
      propositionById(),
    );
    render(<TypedLegalContextSection sections={sections} />);
    expect(screen.getByText(/Direct relationship/i)).toBeTruthy();
    expect(screen.queryByTestId("typed-context-group-inheritance")).toBeNull();
  });
});
