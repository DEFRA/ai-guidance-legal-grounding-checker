import { describe, expect, it } from "vitest";

import {
  extractionMetaFromProposition,
  humanReviewNotesForDisplay,
  parseJuditExtractionMetaFromNotes,
} from "@/components/proposition-explorer-helpers";

describe("proposition notes display helpers", () => {
  it("does not surface judit_extraction_meta blob as human review notes", () => {
    const meta = { extraction_mode: "frontier", evidence_quote: "x" };
    const oa = {
      notes: `judit_extraction_meta:${JSON.stringify(meta)}`,
      review_notes: null,
    };
    expect(humanReviewNotesForDisplay(oa)).toBeNull();
    expect(extractionMetaFromProposition(oa)?.extraction_mode).toBe("frontier");
  });

  it("shows genuine review_notes", () => {
    const oa = {
      notes: "",
      review_notes: "Check with legal.",
    };
    expect(humanReviewNotesForDisplay(oa)).toBe("Check with legal.");
  });

  it("falls back to legacy human notes line when not meta", () => {
    const oa = { notes: "Legacy human note only.", review_notes: null };
    expect(humanReviewNotesForDisplay(oa)).toBe("Legacy human note only.");
  });

  it("parseJuditExtractionMetaFromNotes still works for legacy bundles", () => {
    const notes = 'judit_extraction_meta:{"extraction_mode":"local"}\n';
    expect(parseJuditExtractionMetaFromNotes(notes)?.extraction_mode).toBe("local");
  });
});
