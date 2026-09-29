import { describe, expect, it } from "vitest";

import { buildPropositionsPathForJview } from "./proposition-explorer-jview";

describe("buildPropositionsPathForJview", () => {
  it("omits jview=all and preserves scope", () => {
    expect(buildPropositionsPathForJview("equine", "all")).toBe("/propositions?scope=equine");
    expect(buildPropositionsPathForJview("", "all")).toBe("/propositions");
  });

  it("adds jview for non-all modes", () => {
    expect(buildPropositionsPathForJview("", "eu")).toBe("/propositions?jview=eu");
    expect(buildPropositionsPathForJview("equine", "uk")).toBe(
      "/propositions?scope=equine&jview=uk"
    );
    expect(buildPropositionsPathForJview("", "grouped")).toBe("/propositions?jview=grouped");
    expect(buildPropositionsPathForJview("", "divergences")).toBe(
      "/propositions?jview=divergences"
    );
  });
});
