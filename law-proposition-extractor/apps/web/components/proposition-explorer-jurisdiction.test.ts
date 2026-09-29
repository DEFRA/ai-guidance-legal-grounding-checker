import { describe, expect, it } from "vitest";

import {
  SOURCE_JURISDICTION_CHIP_TOOLTIP,
  jurisdictionDisplay,
} from "./proposition-explorer-helpers";

describe("jurisdictionDisplay", () => {
  it("EU includes flag emoji, label EU, EU-specific title", () => {
    expect(jurisdictionDisplay("EU")).toEqual({
      icon: "🇪🇺",
      label: "EU",
      title: "EU source version",
    });
    expect(jurisdictionDisplay("eu")).toEqual({
      icon: "🇪🇺",
      label: "EU",
      title: "EU source version",
    });
  });

  it("UK includes flag emoji, label UK, UK-specific title", () => {
    expect(jurisdictionDisplay("UK")).toEqual({
      icon: "🇬🇧",
      label: "UK",
      title: "UK source version",
    });
  });

  it("unknown uses text-only fallback label and generic source-version tooltip", () => {
    const sid = "abcdefgh-extra";
    expect(jurisdictionDisplay("—", sid)).toEqual({
      icon: "",
      label: "abcdefgh",
      title: SOURCE_JURISDICTION_CHIP_TOOLTIP,
    });
    expect(jurisdictionDisplay("Schweiz", sid)).toEqual({
      icon: "",
      label: "Schweiz",
      title: SOURCE_JURISDICTION_CHIP_TOOLTIP,
    });
  });
});
