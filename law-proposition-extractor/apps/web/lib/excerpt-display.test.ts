import { describe, expect, it } from "vitest";

import {
  formatExcerptForDisplay,
  joinExcerptParts,
  normalizeExcerptDisplay,
} from "@/lib/excerpt-display";

describe("normalizeExcerptDisplay", () => {
  it("inserts a space after a subsection marker before a capital letter", () => {
    expect(normalizeExcerptDisplay("18(1)The occupier")).toBe("18(1) The occupier");
  });

  it("inserts a space after a schedule paragraph number before a capital letter", () => {
    expect(normalizeExcerptDisplay("Schedule 3.The record")).toBe("Schedule 3. The record");
  });

  it("inserts a space after a closing parenthesis before a lowercase verb", () => {
    expect(normalizeExcerptDisplay("sub-paragraph (1)must")).toBe("sub-paragraph (1) must");
  });

  it("does not alter already well-spaced legal text", () => {
    const text = "The occupier must make a record under regulation 4(1).";
    expect(normalizeExcerptDisplay(text)).toBe(text);
  });

  it("does not alter CLML-serialized schedule paragraph openings", () => {
    const text = "18(1) The occupier must— (a) make a record";
    expect(normalizeExcerptDisplay(text)).toBe(text);
  });

  it("does not insert a space in decimal numbers", () => {
    expect(normalizeExcerptDisplay("within 3.5 metres")).toBe("within 3.5 metres");
  });

  it("inserts a space after a schedule paragraph number and full stop before a capital letter", () => {
    expect(normalizeExcerptDisplay("3.The record")).toBe("3. The record");
  });
});

describe("joinExcerptParts", () => {
  it("joins a subsection label and following sentence", () => {
    expect(joinExcerptParts(["18(1)", "The occupier must"])).toBe("18(1) The occupier must");
  });

  it("joins an article marker and following verb phrase", () => {
    expect(joinExcerptParts(["a", "make a record"])).toBe("a make a record");
  });

  it("returns a single normalized part unchanged apart from boundary repair", () => {
    expect(joinExcerptParts(["18(1)The occupier must"])).toBe("18(1) The occupier must");
  });
});

describe("formatExcerptForDisplay", () => {
  it("passes through unavailable sentinel values", () => {
    expect(formatExcerptForDisplay("not available from current export", "not available from current export")).toBe(
      "not available from current export",
    );
  });
});
