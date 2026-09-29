export type JurisdictionViewMode = "all" | "eu" | "uk" | "grouped" | "divergences";

export function parseJurisdictionViewMode(v: string | null): JurisdictionViewMode | null {
  return v === "all" || v === "eu" || v === "uk" || v === "grouped" || v === "divergences"
    ? v
    : null;
}

/** Client navigation target for `/propositions`; preserves `scope`, maps display mode to `jview`. */
export function buildPropositionsPathForJview(
  filterScopeSlugTrimmed: string,
  mode: JurisdictionViewMode
): string {
  const scopeTok = filterScopeSlugTrimmed.trim();
  const params = new URLSearchParams();
  if (scopeTok) {
    params.set("scope", scopeTok);
  }
  if (mode !== "all") {
    params.set("jview", mode);
  }
  const q = params.toString();
  return q ? `/propositions?${q}` : "/propositions";
}
