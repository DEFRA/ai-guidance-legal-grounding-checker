/**
 * Pure helpers for registry source-family candidate classification and duplicate hints.
 */

export type FamilyCandidateFields = {
  id: string;
  title: string;
  candidate_source_id?: string;
  citation?: string;
  celex?: string;
  eli?: string;
  source_role?: string;
  relationship_to_target?: string;
  inclusion_status?: string;
  confidence?: string;
  reason?: string;
  evidence?: unknown[];
  url?: string;
  metadata?: Record<string, unknown>;
  authority?: string;
};

export type FamilyRegistryEntryLite = {
  registry_id: string;
  reference?: Record<string, unknown>;
  current_state?: Record<string, unknown> | null;
};

export type SourceFamilyDecisionKind =
  | "register"
  | "attach_context"
  | "covered_by_existing"
  | "ignored"
  | "needs_source_selection";

export type SourceFamilyCandidateDecision = {
  candidate_id: string;
  decision: SourceFamilyDecisionKind;
  existing_registry_id?: string;
  reason?: string;
  reviewed_at?: string;
};

export type FamilyCandidatePrimary =
  | "ready_to_register"
  | "already_registered"
  | "needs_source_selection"
  | "possible_duplicate"
  | "context_only"
  | "ignored";

export type FamilyBlockReason =
  | "missing_fetchable_url"
  | "conceptual_grouping_only"
  | "ambiguous_authority_source"
  | "insufficient_citation_celex_eli"
  | "possible_duplicate_of_existing"
  | "missing_title"
  | "unknown_source_role_or_relationship";

export type DuplicateMatch = {
  registry_id: string;
  title?: string;
  citation?: string;
  matched_by: Array<"celex" | "citation" | "authority_source_id" | "url" | "title_similarity">;
};

const LEGIS_PREFIXES = [
  "eur/",
  "ukpga/",
  "uksi/",
  "asc/",
  "wsi/",
  "ssi/",
  "nia/",
  "nisr/",
  "asp/",
  "anaw/",
] as const;

function toText(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function normalizeLower(value: unknown): string {
  return toText(value, "").toLowerCase();
}

export function normalizeAuthoritySourceId(value: unknown): string {
  return toText(value, "").trim().toLowerCase();
}

export function sourceMembershipKey(authority: unknown, authoritySourceId: unknown): string {
  return `${normalizeLower(authority)}:${normalizeAuthoritySourceId(authoritySourceId)}`;
}

export function normalizeCelex(value: unknown): string {
  return toText(value, "").replace(/[\s/._-]+/g, "").toUpperCase();
}

export function normalizeCitationKey(value: unknown): string {
  return toText(value, "")
    .toLowerCase()
    .replace(/\u00a0/g, " ")
    .replace(/[–—]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

function refAuthoritySourceNormalized(ref: Record<string, unknown>): string {
  return normalizeAuthoritySourceId(ref.authority_source_id);
}

export function normalizeLegislationUrl(value: unknown): string {
  const raw = toText(value, "").trim();
  if (!raw) {
    return "";
  }
  try {
    const u = new URL(raw);
    const path = u.pathname.replace(/\/data\.xml$/i, "").replace(/\/+$/g, "");
    return `${u.hostname.toLowerCase()}${path.toLowerCase()}`;
  } catch {
    return raw.toLowerCase();
  }
}

function tokenizeTitle(s: string): Set<string> {
  const stop = new Set([
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "for",
    "to",
    "in",
    "on",
    "no",
    "eu",
    "uk",
  ]);
  const parts = s
    .toLowerCase()
    .replace(/[^a-z0-9]+/gi, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 && !stop.has(w));
  return new Set(parts);
}

/** Dice coefficient on word sets (0–1). */
export function titleWordSimilarity(a: string, b: string): number {
  const ta = tokenizeTitle(a);
  const tb = tokenizeTitle(b);
  if (ta.size === 0 && tb.size === 0) {
    return 0;
  }
  let inter = 0;
  for (const w of ta) {
    if (tb.has(w)) {
      inter += 1;
    }
  }
  return (2 * inter) / (ta.size + tb.size);
}

export function candidateResolveAuthority(row: FamilyCandidateFields): string | null {
  const mdAuth =
    typeof row.metadata?.authority === "string" ? row.metadata.authority.trim() : "";
  const explicit = (typeof row.authority === "string" ? row.authority : "").trim() || mdAuth;
  if (explicit) {
    return explicit;
  }
  const url = toText(row.url, "").toLowerCase();
  if (url.includes("legislation.gov.uk")) {
    return "legislation_gov_uk";
  }
  const asid = normalizeAuthoritySourceId(row.candidate_source_id).toLowerCase();
  for (const prefix of LEGIS_PREFIXES) {
    if (asid.startsWith(prefix)) {
      return "legislation_gov_uk";
    }
  }
  return null;
}

export function legislationAuthoritySourceIdFromCandidate(row: FamilyCandidateFields): string | null {
  const url = toText(row.url, "").trim();
  if (url.toLowerCase().includes("legislation.gov.uk")) {
    try {
      const parsed = new URL(url);
      const segments = parsed.pathname
        .split("/")
        .filter((segment) => segment && segment.toLowerCase() !== "data.xml");
      if (segments.length >= 3) {
        return segments.join("/").toLowerCase();
      }
    } catch {
      return null;
    }
  }
  const csid = toText(row.candidate_source_id, "").trim();
  if (!csid) {
    return null;
  }
  const parts = csid.split("/").filter(Boolean);
  if (parts.length >= 3) {
    return csid.replace(/^\/+|\/+$/g, "").toLowerCase();
  }
  return null;
}

export function familyCandidateLocatorFieldsPresent(row: FamilyCandidateFields): boolean {
  if (toText(row.url, "").trim()) {
    return true;
  }
  const auth = candidateResolveAuthority(row);
  if (!auth) {
    return false;
  }
  return Boolean(
    toText(row.citation, "").trim() ||
      toText(row.celex, "").trim() ||
      toText(row.eli, "").trim()
  );
}

export function familyCandidateCanAutoRegister(row: FamilyCandidateFields): boolean {
  const title = toText(row.title, "").trim();
  if (!title) {
    return false;
  }
  const sr = normalizeLower(row.source_role);
  if (!sr || sr === "unknown") {
    return false;
  }
  const rel = normalizeLower(row.relationship_to_target);
  if (!rel || rel === "unknown") {
    return false;
  }
  if (!familyCandidateLocatorFieldsPresent(row)) {
    return false;
  }
  return legislationAuthoritySourceIdFromCandidate(row) !== null;
}

export function candidateLegislationMembershipKey(row: FamilyCandidateFields): string | null {
  const asid = legislationAuthoritySourceIdFromCandidate(row);
  if (!asid) {
    return null;
  }
  return sourceMembershipKey("legislation_gov_uk", asid);
}

const CONCEPTUAL_HINTS =
  /\b(source family|instrument family|conceptual grouping|legal framework|regulatory family|parent act|umbrella (regulation|directive))\b/i;

export function isConceptualGroupingCandidate(row: FamilyCandidateFields): boolean {
  const md = row.metadata ?? {};
  if (md.conceptual_grouping === true) {
    return true;
  }
  if (md.source_family_group === true) {
    return true;
  }
  if (typeof md.grouping_kind === "string" && md.grouping_kind.toLowerCase().includes("concept")) {
    return true;
  }
  return CONCEPTUAL_HINTS.test(toText(row.title, ""));
}

export function registryReferenceSourceUrl(ref: Record<string, unknown>): string {
  return toText(ref.source_url, "").trim();
}

export function registryEntryCitation(ref: Record<string, unknown>, currentSource: Record<string, unknown>): string {
  return (
    toText(ref.citation, "") ||
    toText(currentSource.citation, "") ||
    toText(ref.celex, "") ||
    ""
  );
}

export function registryEntryTitle(ref: Record<string, unknown>, currentSource: Record<string, unknown>): string {
  return toText(ref.title, "") || toText(currentSource.title, "") || "";
}

export function registryEntryCelexFromRef(
  ref: Record<string, unknown>,
  currentSource: Record<string, unknown>
): string {
  const direct = toText(ref.celex, "");
  if (direct) {
    return direct;
  }
  const meta = ref.metadata;
  if (typeof meta === "object" && meta !== null) {
    const m = meta as Record<string, unknown>;
    const c = toText(m.celex, "");
    if (c) {
      return c;
    }
  }
  return toText(currentSource.celex, "");
}

/**
 * Find a registry entry that likely matches this candidate (excluding exact membership key if given).
 */
export function findDuplicateRegistryMatch(
  row: FamilyCandidateFields,
  entries: FamilyRegistryEntryLite[],
  options?: { exclude_membership_key?: string | null }
): DuplicateMatch | null {
  const candCelex = normalizeCelex(row.celex);
  const candCit = normalizeCitationKey(row.citation);
  const candAsid = legislationAuthoritySourceIdFromCandidate(row);
  const candUrl = normalizeLegislationUrl(row.url);
  const candTitle = toText(row.title, "");

  let best: DuplicateMatch | null = null;
  let bestScore = 0;

  for (const entry of entries) {
    const ref = (entry.reference ?? {}) as Record<string, unknown>;
    const current = (entry.current_state?.source_record ?? {}) as Record<string, unknown>;
    const refAsid = refAuthoritySourceNormalized(ref);
    const mk = sourceMembershipKey(ref.authority, ref.authority_source_id);
    if (options?.exclude_membership_key && mk === options.exclude_membership_key) {
      continue;
    }
    const regCelex = normalizeCelex(registryEntryCelexFromRef(ref, current));
    const regCit = normalizeCitationKey(registryEntryCitation(ref, current));
    const regTitle = registryEntryTitle(ref, current);
    const regUrl = normalizeLegislationUrl(registryReferenceSourceUrl(ref));

    const matched_by: DuplicateMatch["matched_by"] = [];

    let score = 0;
    if (candCelex && regCelex && candCelex === regCelex) {
      score += 50;
      matched_by.push("celex");
    }
    if (candCit && regCit && candCit === regCit && candCit.length > 6) {
      score += 40;
      matched_by.push("citation");
    }
    if (candAsid && refAsid && candAsid === refAsid) {
      score += 60;
      matched_by.push("authority_source_id");
    }
    if (candUrl && regUrl && candUrl === regUrl) {
      score += 45;
      matched_by.push("url");
    }
    const ts = titleWordSimilarity(candTitle, regTitle || candTitle);
    const titleStrongEnough = candTitle.length > 14 && regTitle.length > 14;
    if (ts >= 0.72 && titleStrongEnough) {
      score += Math.round(ts * 20);
      matched_by.push("title_similarity");
    }

    if (score > bestScore && matched_by.length > 0) {
      bestScore = score;
      best = {
        registry_id: entry.registry_id,
        title: regTitle || undefined,
        citation: registryEntryCitation(ref, current) || undefined,
        matched_by: [...new Set(matched_by)],
      };
    }
  }

  const strongEnough = Boolean(
    best &&
      ((bestScore >= 40 && best.matched_by.some((m) => m !== "title_similarity")) ||
        (best.matched_by.includes("title_similarity") && bestScore >= 18))
  );

  return strongEnough ? best : null;
}

export type ClassifyFamilyCandidateInput = {
  row: FamilyCandidateFields;
  registryEntries: FamilyRegistryEntryLite[];
  registryByMembershipKey: Map<string, FamilyRegistryEntryLite>;
  registeredThisSession: Record<string, string>;
  /** User-reviewed decisions (persist later if desired). */
  decisions?: Record<string, SourceFamilyCandidateDecision | undefined>;
};

export type ClassifiedFamilyCandidate = {
  primary: FamilyCandidatePrimary;
  block_reasons: FamilyBlockReason[];
  duplicate_match: DuplicateMatch | null;
  /** Registry id when already in registry / session. */
  existing_registry_id: string | null;
  membership_key: string | null;
  /** When user marked candidate as covered by an existing registry source. */
  coverage_registry_id: string | null;
};

function collectBlockReasons(row: FamilyCandidateFields, conceptual: boolean): FamilyBlockReason[] {
  const reasons: FamilyBlockReason[] = [];
  if (conceptual) {
    reasons.push("conceptual_grouping_only");
  }
  if (!toText(row.title, "").trim()) {
    reasons.push("missing_title");
  }
  const sr = normalizeLower(row.source_role);
  const rel = normalizeLower(row.relationship_to_target);
  if (!sr || sr === "unknown" || !rel || rel === "unknown") {
    reasons.push("unknown_source_role_or_relationship");
  }
  if (!familyCandidateLocatorFieldsPresent(row)) {
    reasons.push("insufficient_citation_celex_eli");
  } else if (!candidateResolveAuthority(row)) {
    reasons.push("ambiguous_authority_source");
  }
  const hasUrl = Boolean(toText(row.url, "").trim());
  const hasAsidPath = legislationAuthoritySourceIdFromCandidate(row);
  if (!hasUrl && !hasAsidPath) {
    reasons.push("missing_fetchable_url");
  }
  return reasons;
}

export function classifyFamilyCandidate(input: ClassifyFamilyCandidateInput): ClassifiedFamilyCandidate {
  const { row, registryEntries, registryByMembershipKey, registeredThisSession, decisions } = input;
  const decision = decisions?.[row.id];
  const membership_key = candidateLegislationMembershipKey(row);
  const conceptual = isConceptualGroupingCandidate(row);
  const canRegister = familyCandidateCanAutoRegister(row);

  const compose = (
    primary: FamilyCandidatePrimary,
    partial?: Partial<Omit<ClassifiedFamilyCandidate, "primary" | "membership_key">>
  ): ClassifiedFamilyCandidate => ({
    primary,
    membership_key,
    block_reasons: partial?.block_reasons ?? [],
    duplicate_match:
      partial?.duplicate_match !== undefined ? partial.duplicate_match : null,
    existing_registry_id:
      partial?.existing_registry_id !== undefined ? partial.existing_registry_id : null,
    coverage_registry_id:
      partial?.coverage_registry_id !== undefined ? partial.coverage_registry_id : null,
  });

  if (decision?.decision === "ignored") {
    return compose("ignored");
  }

  const rawSession = registeredThisSession[row.id];
  const sessionRegistryHit =
    typeof rawSession === "string" ? rawSession.trim() : "";

  const persistedRegistryHit =
    membership_key !== null
      ? registryByMembershipKey.get(membership_key)?.registry_id
      : undefined;

  const existingHitId =
    (sessionRegistryHit.length > 0 ? sessionRegistryHit : undefined) ?? persistedRegistryHit ?? null;

  const alreadyInRegistry = Boolean(sessionRegistryHit || persistedRegistryHit);

  const coverage_rid =
    decision?.decision === "covered_by_existing" &&
    typeof decision.existing_registry_id === "string" &&
    decision.existing_registry_id.trim().length > 0
      ? decision.existing_registry_id.trim()
      : null;

  if (alreadyInRegistry && existingHitId) {
    return compose("already_registered", { existing_registry_id: existingHitId });
  }

  let duplicate_match: DuplicateMatch | null = findDuplicateRegistryMatch(row, registryEntries);
  if (duplicate_match?.registry_id === coverage_rid) {
    duplicate_match = null;
  }

  if (conceptual) {
    return compose("needs_source_selection", {
      block_reasons: collectBlockReasons(row, true),
      duplicate_match: null,
      coverage_registry_id: coverage_rid,
    });
  }

  if (coverage_rid) {
    return compose("needs_source_selection", {
      duplicate_match,
      existing_registry_id: coverage_rid,
      coverage_registry_id: coverage_rid,
    });
  }

  if (duplicate_match) {
    return compose("possible_duplicate", {
      block_reasons: ["possible_duplicate_of_existing"],
      duplicate_match,
    });
  }

  if (row.inclusion_status === "optional_context" && !canRegister && !conceptual) {
    return compose("context_only", {
      block_reasons: collectBlockReasons(row, false),
    });
  }

  if (!canRegister) {
    return compose("needs_source_selection", {
      block_reasons: collectBlockReasons(row, false),
    });
  }

  return compose("ready_to_register");
}

export function describeBlockReasons(reasons: FamilyBlockReason[]): string[] {
  const lines: string[] = [];
  const seen = new Set<FamilyBlockReason>();
  for (const r of reasons) {
    if (seen.has(r)) {
      continue;
    }
    seen.add(r);
    switch (r) {
      case "missing_fetchable_url":
        lines.push("No fetchable legislation.gov.uk locator (need URL or ukpga/uksi/eur path).");
        break;
      case "conceptual_grouping_only":
        lines.push("Conceptual grouping only — pick a concrete instrument before registering.");
        break;
      case "ambiguous_authority_source":
        lines.push("Authority or source locator is ambiguous.");
        break;
      case "insufficient_citation_celex_eli":
        lines.push("Insufficient citation / CELEX / ELI without a usable URL.");
        break;
      case "possible_duplicate_of_existing":
        lines.push("May duplicate an existing registry entry.");
        break;
      case "missing_title":
        lines.push("Missing title.");
        break;
      case "unknown_source_role_or_relationship":
        lines.push("Source role or relationship to target is unknown.");
        break;
      default:
        break;
    }
  }
  return lines;
}

export const CONCEPTUAL_FAMILY_HELP =
  "This describes a source family, not a concrete source. Choose a concrete source before registering.";

export function classificationRegisterEligible(primary: FamilyCandidatePrimary): boolean {
  return primary === "ready_to_register";
}

export function primaryBadgeLabel(primary: FamilyCandidatePrimary): string {
  switch (primary) {
    case "ready_to_register":
      return "Ready to register";
    case "already_registered":
      return "Already registered";
    case "needs_source_selection":
      return "Needs source selection";
    case "possible_duplicate":
      return "Possible duplicate";
    case "context_only":
      return "Context only";
    case "ignored":
      return "Ignored";
    default:
      return primary;
  }
}

