import { describe, expect, it } from "vitest";

import {
  territoryBrowseLabel,
  territorialApplicationFromProposition,
  TERRITORIAL_APPLICATION_CHIP_TOOLTIP,
} from "./proposition-explorer-helpers";

describe("territorial application helpers", () => {
  it("reads territorial_application array from proposition artifact", () => {
    expect(
      territorialApplicationFromProposition({
        territorial_application: ["England", "Wales"],
      })
    ).toEqual(["England", "Wales"]);
  });

  it("territoryBrowseLabel prefers territorial_application", () => {
    expect(
      territoryBrowseLabel({
        jurisdiction: "UK",
        territorial_application: ["England"],
      })
    ).toBe("England");
  });

  it("exposes browse tooltip copy", () => {
    expect(TERRITORIAL_APPLICATION_CHIP_TOOLTIP).toMatch(/territorial application/i);
  });
});
