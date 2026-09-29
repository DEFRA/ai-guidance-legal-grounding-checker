"use client";

import type { JSX, ReactNode } from "react";
import { useLayoutEffect, useRef } from "react";

export type UnknownRecord = Record<string, unknown>;

const JUDIT_EXTRACTION_META_PREFIX = "judit_extraction_meta:";

/** First line in notes may embed JSON metadata from the pipeline (see ``attach_judit_extraction_meta``). */
export function parseJuditExtractionMetaFromNotes(notes: unknown): UnknownRecord | null {
  if (typeof notes !== "string" || !notes.trim()) {
    return null;
  }
  const line0 = notes.split("\n", 1)[0]?.trim() ?? "";
  if (!line0.startsWith(JUDIT_EXTRACTION_META_PREFIX)) {
    return null;
  }
  const rawJson = line0.slice(JUDIT_EXTRACTION_META_PREFIX.length).trim();
  try {
    const parsed: unknown = JSON.parse(rawJson);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    return parsed as UnknownRecord;
  } catch {
    return null;
  }
}

export type VerbatimEvidenceUi = {
  known: boolean;
  quoteText: string | undefined;
  /** Verbatim quote absent but extraction recorded that case — show traceability warning in UI. */
  showTraceabilityWarning: boolean;
};

function verbatimEvidenceUiFromMeta(data: UnknownRecord | null): VerbatimEvidenceUi {
  const none: VerbatimEvidenceUi = {
    known: false,
    quoteText: undefined,
    showTraceabilityWarning: false,
  };
  if (!data) {
    return none;
  }
  if (!Object.prototype.hasOwnProperty.call(data, "evidence_quote")) {
    return none;
  }
  const eq = data["evidence_quote"];
  if (typeof eq !== "string") {
    return none;
  }
  return {
    known: true,
    quoteText: eq,
    showTraceabilityWarning: !eq.trim(),
  };
}

/** Legacy: first-line JSON in ``notes``. Prefer {@link extractionMetaFromProposition}. */
export function verbatimEvidenceUiFromNotes(notes: unknown): VerbatimEvidenceUi {
  return verbatimEvidenceUiFromMeta(parseJuditExtractionMetaFromNotes(notes));
}

/** Structured debug meta on the proposition, with legacy ``notes`` fallback. */
export function extractionMetaFromProposition(oa: UnknownRecord): UnknownRecord | null {
  const dbg = asRecord(oa.extraction_debug_meta);
  if (dbg && Object.keys(dbg).length > 0) {
    return dbg;
  }
  return parseJuditExtractionMetaFromNotes(oa.notes);
}

/** Human review text only — never the ``judit_extraction_meta`` blob. */
export function humanReviewNotesForDisplay(oa: UnknownRecord): string | null {
  const review = oa.review_notes;
  if (typeof review === "string" && review.trim()) {
    return review.trim();
  }
  const notes = oa.notes;
  if (typeof notes !== "string" || !notes.trim()) {
    return null;
  }
  if (notes.trim().startsWith(JUDIT_EXTRACTION_META_PREFIX)) {
    return null;
  }
  return notes.trim();
}

export function verbatimEvidenceUiFromProposition(oa: UnknownRecord): VerbatimEvidenceUi {
  return verbatimEvidenceUiFromMeta(extractionMetaFromProposition(oa));
}

/**
 * Full extraction/debug payload for trace-oriented UI (raw/debug views only).
 * Omits raw model excerpts unless ``includeRawModelOutput`` is true.
 */
export function extractionDebugPayloadForUi(
  oa: UnknownRecord,
  opts?: { includeRawModelOutput?: boolean },
): UnknownRecord | null {
  const meta = extractionMetaFromProposition(oa);
  if (!meta) {
    return null;
  }
  if (opts?.includeRawModelOutput) {
    return meta;
  }
  const out: UnknownRecord = { ...meta };
  delete out.raw_model_output_excerpt;
  delete out.raw_model_output_truncated;
  delete out.extraction_llm_call_traces;
  return Object.keys(out).length > 0 ? out : null;
}

export function asRecord(value: unknown): UnknownRecord | null {
  return typeof value === "object" && value !== null ? (value as UnknownRecord) : null;
}

const REPAIRABLE_FAILURE_HINT_SUBSTRINGS: readonly string[] = [
  "insufficient credit",
  "credit balance",
  "not enough credit",
  "quota",
  "rate limit",
  "ratelimit",
  "429",
  "context window",
  "context_window",
  "max token",
  "token limit",
  "model alias",
  "unknown model",
  "model not found",
  "json parse",
  "jsondecode",
  "model call or json parse failed",
  "model call failed",
  "llm call failure",
  "llm invocation",
  "overloaded",
  "api error",
];

function blobLowerParts(...parts: unknown[]): string {
  return parts
    .filter((p) => p != null && String(p).trim().length > 0)
    .map((p) => String(p))
    .join(" ")
    .toLowerCase();
}

/** Heuristic aligned with pipeline ``classify_repairable_failure_type`` substrings. */
export function textSuggestsRepairableExtractionFailure(text: string): boolean {
  const b = text.toLowerCase();
  if (!b.trim()) {
    return false;
  }
  return REPAIRABLE_FAILURE_HINT_SUBSTRINGS.some((s) => b.includes(s));
}

/**
 * Client-side repair banner hint when API quality summary is stale/unavailable but traces or
 * proposition notes show frontier fallback with infra-style validation errors.
 */
export function clientRepairableExtractionHintFromExplorerData(
  traces: UnknownRecord[],
  propositionRows: UnknownRecord[],
): boolean {
  for (const tr of traces) {
    const ev = asRecord(tr.effective_value) ?? {};
    const mode = String(ev.extraction_mode ?? "").trim();
    const method = String(ev.extraction_method ?? "").trim();
    const sig = asRecord(ev.signals);
    const fb =
      Boolean(ev.fallback_used) || Boolean(sig?.fallback_used) || method === "fallback";
    if (mode === "frontier" && fb) {
      const valErrs = Array.isArray(ev.validation_errors) ? ev.validation_errors : [];
      const errExtra = Array.isArray(ev.errors) ? ev.errors : [];
      const blob = blobLowerParts(ev.reason, ...valErrs, ...errExtra);
      if (textSuggestsRepairableExtractionFailure(blob)) {
        return true;
      }
    }
  }
  for (const row of propositionRows) {
    const oa = asRecord(row.original_artifact) ?? {};
    const meta = extractionMetaFromProposition(oa);
    if (!meta) {
      continue;
    }
    if (String(meta.extraction_mode ?? "").trim() !== "frontier") {
      continue;
    }
    if (!Boolean(meta.fallback_used)) {
      continue;
    }
    const mve = Array.isArray(meta.validation_errors) ? meta.validation_errors : [];
    const blob = blobLowerParts(...mve);
    if (textSuggestsRepairableExtractionFailure(blob)) {
      return true;
    }
  }
  return false;
}

/**
 * run_quality_summary.metrics.repairable_extraction token estimate label for the repair banner.
 * Null/missing must not render as numeric zero — that reads as "free retry" vs "estimate unavailable".
 */
export function formatRepairBannerRetryTokenEstimate(
  scan: UnknownRecord | null | undefined,
): string {
  const s = scan ?? {};
  const primary = s.estimated_retry_tokens;
  if (typeof primary === "number") {
    return primary.toLocaleString("en-US");
  }
  const legacy = s.estimated_retry_token_count;
  if (typeof legacy === "number" && legacy > 0) {
    return legacy.toLocaleString("en-US");
  }
  return "unknown";
}

/** Matches ``failure_type`` slugs that warrant the credits/quota helper under the repair banner. */
export const REPAIR_BANNER_CREDITS_OR_QUOTA_FAILURE_TYPES = new Set([
  "insufficient_credits",
  "quota",
]);

export const REPAIR_BANNER_CREDITS_QUOTA_HELPER_TEXT =
  "Restore provider credits before repairing, otherwise repair will fail again.";

/** Labels for pipeline ``repairable_extraction.failure_reasons`` / ``failure_type`` slugs (dedupe e.g. both credit + quota → one phrase). */
const REPAIR_BANNER_FAILURE_TYPE_LABELS: Record<string, string> = {
  insufficient_credits: "credits/quota",
  quota: "credits/quota",
  rate_limit: "rate limit",
  context_window: "context window",
  model_availability: "model availability",
  json_parse_or_llm_failure: "JSON parse",
  llm_call_failure: "LLM call",
  other_model_infra: "provider/infra",
  unknown: "unknown",
};

function repairBannerSlugToFallbackLabel(slug: string): string {
  const t = slug.trim();
  return t.replace(/_/g, " ").replace(/\s+/g, " ").trim() || slug;
}

function parseRepairBannerFailureReasonTypes(reasonsUnknown: unknown): string[] {
  if (!Array.isArray(reasonsUnknown)) {
    return [];
  }
  const out = reasonsUnknown.filter(
    (x): x is string => typeof x === "string" && x.trim().length > 0,
  ).map((x) => x.trim());
  return out;
}

function compactRepairBannerFailureReasonLabels(canonicalTypes: string[]): string[] {
  const uniqueTypes = [...new Set(canonicalTypes)].sort((a, b) => a.localeCompare(b));
  const seenLabels = new Set<string>();
  const labels: string[] = [];
  for (const slug of uniqueTypes) {
    const mapped =
      REPAIR_BANNER_FAILURE_TYPE_LABELS[slug] ?? repairBannerSlugToFallbackLabel(slug);
    if (!seenLabels.has(mapped)) {
      seenLabels.add(mapped);
      labels.push(mapped);
    }
  }
  return labels;
}

/** Compact sentence for banner, or null when metrics carry no usable reasons array. */
export function repairBannerFailureReasonsSentence(reasonsUnknown: unknown): string | null {
  const types = parseRepairBannerFailureReasonTypes(reasonsUnknown);
  if (!types.length) {
    return null;
  }
  const labels = compactRepairBannerFailureReasonLabels(types);
  if (!labels.length) {
    return null;
  }
  return `Reasons: ${labels.join(", ")}`;
}

/** True when any failure_reasons entry is credits/quota-ish (shows restore-credits helper). */
export function repairBannerNeedsCreditsQuotaHelper(reasonsUnknown: unknown): boolean {
  const types = parseRepairBannerFailureReasonTypes(reasonsUnknown);
  return types.some((t) => REPAIR_BANNER_CREDITS_OR_QUOTA_FAILURE_TYPES.has(t));
}

/**
 * Same rule as structured scope UI default list: direct relevance + high link confidence only.
 * Scope filtering uses this so results match what users see before "Show all scopes".
 */
export function isPrimaryScopeLinkRow(ln: UnknownRecord): boolean {
  const relevance = String(ln.relevance ?? "")
    .trim()
    .toLowerCase();
  const confidence = String(ln.confidence ?? "")
    .trim()
    .toLowerCase();
  if (!(relevance === "direct" && confidence === "high")) {
    return false;
  }
  const method = String(ln.method ?? "")
    .trim()
    .toLowerCase();
  const signals = asRecord(ln.signals);
  const evidenceField = String(signals?.evidence_field ?? "")
    .trim()
    .toLowerCase();
  const groundedEvidenceFields = new Set([
    "proposition_text",
    "source_fragment_text",
    "legal_subject",
    "affected_subjects",
    "required_documents",
    "conditions",
  ]);
  if (evidenceField && !groundedEvidenceFields.has(evidenceField)) {
    return false;
  }
  if (method === "deterministic" && !evidenceField) {
    return false;
  }
  return true;
}

/** Exact token match on scope id, slug, label, or synonym (no substring — avoids "non-equine" ⊆ "equine"). */
export function scopeMatchesTaxonomyFilter(
  filterToken: string,
  scopeId: string,
  scope: UnknownRecord | undefined
): boolean {
  const want = filterToken.trim().toLowerCase();
  if (!want) {
    return true;
  }
  const sid = scopeId.trim().toLowerCase();
  if (sid === want) {
    return true;
  }
  if (!scope) {
    return false;
  }
  const slug = String(scope.slug ?? "")
    .trim()
    .toLowerCase();
  if (slug === want) {
    return true;
  }
  const label = String(scope.label ?? "")
    .trim()
    .toLowerCase();
  if (label === want) {
    return true;
  }
  const syn = scope.synonyms;
  if (Array.isArray(syn)) {
    for (const raw of syn) {
      if (String(raw).trim().toLowerCase() === want) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Whether a proposition should appear for the scope filter: at least one *primary* scope link
 * must match the token (visible chips by default in the proposition UI).
 */
export function propositionMatchesPrimaryVisibleScopeFilter(
  propositionId: string,
  filterToken: string,
  allLinks: UnknownRecord[],
  scopeById: Map<string, UnknownRecord>
): boolean {
  const want = filterToken.trim();
  if (!want) {
    return true;
  }
  const pid = propositionId.trim();
  if (!pid) {
    return false;
  }
  const forProp = allLinks.filter(
    (ln) => String((ln as { proposition_id?: string }).proposition_id ?? "").trim() === pid
  );
  const primary = forProp.filter(isPrimaryScopeLinkRow);
  if (primary.length === 0) {
    return false;
  }
  for (const ln of primary) {
    const sco = String((ln as { scope_id?: string }).scope_id ?? "").trim();
    const sc = scopeById.get(sco);
    if (scopeMatchesTaxonomyFilter(want, sco, sc)) {
      return true;
    }
  }
  return false;
}

/** Tooltip for EU / UK (and similar) chips: clarifies these are source versions, not divergence. */
export const SOURCE_JURISDICTION_CHIP_TOOLTIP =
  "Source jurisdiction/version, not a divergence finding.";

export const TERRITORIAL_APPLICATION_CHIP_TOOLTIP =
  "Where this rule applies (territorial application). Prefer this over coarse source jurisdiction when browsing.";

/** Normalised territorial_application from a proposition artifact (empty when absent). */
export function territorialApplicationFromProposition(artifact: UnknownRecord): string[] {
  const raw = artifact.territorial_application;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map((x) => String(x).trim()).filter(Boolean);
}

/** Law-making / source jurisdiction on the proposition, falling back to source record. */
export function sourceJurisdictionFromProposition(
  artifact: UnknownRecord,
  sources: UnknownRecord[],
  sourceId: string,
): string {
  const explicit = String(artifact.source_jurisdiction ?? "").trim();
  if (explicit) {
    return explicit;
  }
  return jurisdictionForSource(sources, sourceId);
}

/**
 * Primary territory label for browsing/filter copy — prefers territorial_application
 * over coarse jurisdiction on the proposition row.
 */
export function territoryBrowseLabel(artifact: UnknownRecord): string {
  const terr = territorialApplicationFromProposition(artifact);
  if (terr.length > 0) {
    return terr.join(", ");
  }
  return "";
}

/** Distinct territorial_application labels across explorer rows in a section/group. */
export function territoryLabelsRepresented(rows: ReadonlyArray<UnknownRecord>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const row of rows) {
    const oa = asRecord(row.original_artifact) ?? {};
    for (const label of territorialApplicationFromProposition(oa)) {
      if (!seen.has(label)) {
        seen.add(label);
        out.push(label);
      }
    }
  }
  return [...out].sort((a, b) => a.localeCompare(b));
}

const SCOPE_FILTER_DISPLAY_LABELS: Readonly<Record<string, string>> = {
  equine: "Equine",
  bovine: "Bovine",
  porcine: "Porcine",
  germinal_products: "Germinal products",
};

/** Human label for scope preset chips and filter explainer copy. */
export function scopeFilterDisplayLabel(filterToken: string): string {
  const t = filterToken.trim().toLowerCase();
  if (!t) {
    return "";
  }
  return SCOPE_FILTER_DISPLAY_LABELS[t] ?? filterToken.trim();
}

/** EU/UK badges in compact group summaries — flag + short label for scanability. */
function jurisdictionBadgeSummaryFragment(badgeLabel: string): string {
  const u = badgeLabel.trim().toUpperCase();
  if (u === "EU") {
    return "🇪🇺 EU";
  }
  if (u === "UK") {
    return "🇬🇧 UK";
  }
  return badgeLabel.trim();
}

/**
 * Summary chip for a proposition *group* (one card, multiple source rows).
 * Uses “source rows” / “EU/UK pair” wording so chips are not mistaken for divergence findings.
 */
export function propositionGroupMetaChipText(args: {
  sourceRowCount: number;
  allSameWording: boolean;
  jurisdictionBadgeLabels: string[];
}): string {
  const { sourceRowCount, allSameWording, jurisdictionBadgeLabels } = args;
  const wording = allSameWording ? "same wording" : "different wording";
  const uniq = [...new Set(jurisdictionBadgeLabels.map((x) => String(x).trim()).filter(Boolean))];
  const jPart = uniq.map(jurisdictionBadgeSummaryFragment).join(", ");

  if (sourceRowCount <= 1) {
    return jPart ? `Single source row · ${jPart}` : "Single source row";
  }

  const upper = new Set(uniq.map((x) => x.toUpperCase()));
  const isEuUkPair =
    sourceRowCount === 2 &&
    upper.size === 2 &&
    upper.has("EU") &&
    upper.has("UK");
  if (isEuUkPair) {
    return `🇪🇺 EU / 🇬🇧 UK · ${wording}`;
  }
  return `${sourceRowCount} source rows · ${jPart} · ${wording}`;
}

const GENERIC_FRAGMENT_LOCATORS = new Set(["document:full", "full", "document", ""]);
const CLUSTER_KEY_SEP = "\u001f";
/** Appended after lineage group key when splitting one lineage into per-article subgroups (must differ from {@link CLUSTER_KEY_SEP}). */
const PARTITION_SUBGROUP_APPEND_SEP = "\u001e";

/** Fields for grouping / suppression; tolerates top-level mirrors on effective view rows. */
export function propositionArtifactFields(row: UnknownRecord): {
  id: string;
  proposition_key: string;
  fragment_locator: string;
  proposition_text: string;
} {
  const oa = asRecord(row.original_artifact) ?? {};
  const pk = String(oa.proposition_key ?? row.proposition_key ?? "").trim();
  const id = String(oa.id ?? row.id ?? "").trim();
  const fl = String(oa.fragment_locator ?? row.fragment_locator ?? "").trim();
  const text = String(oa.proposition_text ?? row.proposition_text ?? "").trim();
  return { id, proposition_key: pk, fragment_locator: fl, proposition_text: text };
}

/**
 * Light normalisation so EU/UK or near-duplicate wordings share one explorer lineage group without
 * changing stored proposition identities.
 */
export function normalizePropositionTextForLineageGroup(s: string): string {
  let t = s.trim().replace(/\s+/g, " ").toLowerCase();
  t = t.replace(/\bshall\b/g, "must");
  t = t.replace(/\bthat the information\b/g, "that information");
  return t;
}

// Mirror of law_proposition_extractor_pipeline.repealed_provisions.is_repealed_or_empty_fragment (keep in sync).
const REPEALED_PLACEHOLDER_RE =
  /^[.\u2026\u00b7\u2022)\s]*(?:(?:\(?\d+[a-z]?\)?|\((?:[a-z]|[ivxlcdm]{1,5})\)|(?:article|section|regulation|paragraph|sub-?paragraph|annex|schedule|part|chapter)\s*[ivxlcdm\d]+[a-z]?)[.\u2026\u00b7\u2022)\s]*)*$/i;

/**
 * True when a fragment / proposition carries no extractable normative content: blank text, bare
 * enumerators ((2), 5.), lone headings (ANNEX II), or repealed/omitted dot runs (Article 5. . . .).
 */
export function isRepealedOrEmptyFragment(text: string | null | undefined): boolean {
  const collapsed = String(text ?? "").trim().replace(/\s+/g, " ");
  if (!collapsed) {
    return true;
  }
  return REPEALED_PLACEHOLDER_RE.test(collapsed);
}

/** Whether `fragment_locator` resolves to bare `article:N` / `section:N` (optional registry prefix only). */
export function isCoarseArticleScopedLocator(loc: string): boolean {
  let t = loc.trim().replace(/__+/g, "-");
  if (!t || GENERIC_FRAGMENT_LOCATORS.has(t.toLowerCase()) || t.includes(":list:")) {
    return false;
  }
  const si = t.indexOf("/");
  if (si > 0 && si <= 200) {
    t = t.slice(0, si).trim();
  }
  const colonIdx = t.indexOf(":");
  if (colonIdx > 0 && colonIdx < 24) {
    const head = t.slice(0, colonIdx).toLowerCase();
    const rest = t.slice(colonIdx + 1).trim();
    const headIsRole = head === "article" || head === "section";
    if (!headIsRole && /^[a-z][a-z0-9_-]{0,20}$/.test(head)) {
      t = rest;
    }
  }
  return /^(article|section):\d+[a-z]?$/i.test(t);
}

/**
 * Stem for frontier / human-readable locators (`Article 114(1)(a)`, `Article 109(1)(d)(i)`,
 * `Article 114(2)`) aligned with pipeline `article:N:list:` keys for lineage grouping.
 */
export function humanReadableArticleLocatorLineageStem(rawLoc: string): string | null {
  const t = rawLoc.trim();
  const multi = t.match(/^article\s+(\d+[a-z]?)\s*((?:\(\s*[^()]+\s*\))+)\s*$/i);
  if (multi) {
    const art = multi[1].toLowerCase();
    const inner = [...multi[2].matchAll(/\(\s*([^()]+)\s*\)/g)].map((m) =>
      String(m[1] ?? "")
        .trim()
        .toLowerCase()
    );
    if (inner.length >= 2 && /^\d+$/.test(inner[0])) {
      const path = inner.join("-");
      return `article:${art}:list:${path}`;
    }
  }
  const para = t.match(/^article\s+(\d+[a-z]?)\s*\(\s*(\d+)\s*\)\s*$/i);
  if (para) {
    return `article:${para[1].toLowerCase()}:para:${para[2]}`;
  }
  return null;
}

function normalizeStructuredListPathSegments(path: string): string {
  return path
    .replace(/__/g, "-")
    .split("-")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean)
    .join("-");
}

/**
 * Normalizes structured list / slug / human-readable fragment locators to one lineage group key
 * (`article:N:list:path` or `article:N:para:P`) so EU/UK rows that differ only by encoding merge.
 */
export function canonicalLineageKeyForGrouping(rawLoc: string): string | null {
  let t = rawLoc.trim();
  if (!t || GENERIC_FRAGMENT_LOCATORS.has(t.toLowerCase())) {
    return null;
  }
  t = t.replace(/__+/g, "-");
  const si = t.indexOf("/");
  if (si > 0 && si <= 200) {
    t = t.slice(0, si).trim();
  }
  const colonIdx0 = t.indexOf(":");
  if (colonIdx0 > 0 && colonIdx0 < 24) {
    const head = t.slice(0, colonIdx0).toLowerCase();
    const rest = t.slice(colonIdx0 + 1).trim();
    const headIsRole = head === "article" || head === "section";
    if (!headIsRole && /^[a-z][a-z0-9_-]{0,20}$/.test(head)) {
      t = rest;
    }
  }

  if (t.toLowerCase().includes(":list:")) {
    const pathKey = canonicalStructuredListPathKey(t);
    if (!pathKey) {
      return null;
    }
    const io = pathKey.indexOf(":");
    if (io <= 0) {
      return null;
    }
    const art = pathKey.slice(0, io).toLowerCase();
    const path = normalizeStructuredListPathSegments(pathKey.slice(io + 1));
    if (!path) {
      return null;
    }
    return `article:${art}:list:${path}`;
  }

  /** Pipeline / registry colon form e.g. `article:3:para:1` — must align with human `Article 3(1)`. */
  const colonPara = t.match(/^(article|section):(\d+[a-z]?):para:(\d+)$/i);
  if (colonPara) {
    const role = colonPara[1].toLowerCase() === "section" ? "section" : "article";
    return `${role}:${colonPara[2].toLowerCase()}:para:${colonPara[3]}`;
  }

  /** Pipeline `article:6:paragraph:1`, `article:6:paragraph:1(a)(i)` — align with `:para:`/`:list:`. */
  const colonParagraph = t.match(
    /^(article|section):(\d+[a-z]?):paragraph:(\d+[a-z]?)((?:\([^()]+\))*)$/i
  );
  if (colonParagraph) {
    const role = colonParagraph[1].toLowerCase() === "section" ? "section" : "article";
    const art = colonParagraph[2].toLowerCase();
    const para = colonParagraph[3].toLowerCase();
    const subs = [...(colonParagraph[4] ?? "").matchAll(/\(([^()]+)\)/g)].map((m) =>
      String(m[1] ?? "")
        .trim()
        .toLowerCase()
    );
    if (subs.length > 0) {
      return `${role}:${art}:list:${[para, ...subs].join("-")}`;
    }
    return `${role}:${art}:para:${para}`;
  }

  if (/^article_/i.test(t)) {
    t = t.replace(/_/g, "-");
  }
  /** Hyphen slug `article-3-para-1` (after `_`→`-`); must not fall through to list slug `article-3-1-a`. */
  const hyphenPara = t.match(/^(article|section)-(\d+[a-z]?)-para-(\d+)$/i);
  if (hyphenPara) {
    const role = hyphenPara[1].toLowerCase() === "section" ? "section" : "article";
    return `${role}:${hyphenPara[2].toLowerCase()}:para:${hyphenPara[3]}`;
  }
  const slugM = t.match(/^article-(\d+[a-z]?)-(\S+)$/i);
  if (slugM) {
    const tail = slugM[2].replace(/_/g, "-");
    if (!tail.includes(":") && !/^article\b/i.test(tail)) {
      const path = normalizeStructuredListPathSegments(tail);
      if (path.includes("-")) {
        return `article:${slugM[1].toLowerCase()}:list:${path}`;
      }
    }
  }

  return humanReadableArticleLocatorLineageStem(t);
}

/**
 * Heuristic extractor sometimes emits coarse `article:N` umbrellas alongside `article:N:list:*` rows.
 * Drop the umbrella from the default explorer rows when subsection list items capture the §1 obligations.
 */
export function shouldSuppressCoarseParentPropositionInDefaultView(
  row: UnknownRecord,
  universe: ReadonlyArray<UnknownRecord>
): boolean {
  const pf = propositionArtifactFields(row);
  if (isRepealedOrEmptyFragment(pf.proposition_text)) {
    return true;
  }
  const loc = pf.fragment_locator;
  if (!loc || !isCoarseArticleScopedLocator(loc)) {
    return false;
  }
  const hostArt = canonicalArticleFromFragmentLocator(loc);
  if (!hostArt || hostArt.role !== "article") {
    return false;
  }
  let hasStructuredListChild = false;
  for (const other of universe) {
    const o = propositionArtifactFields(other);
    if (o.id === pf.id || o.fragment_locator === loc) {
      continue;
    }
    const oLineage = canonicalLineageKeyForGrouping(o.fragment_locator);
    const oIsListRow =
      o.fragment_locator.includes(":list:") ||
      (oLineage !== null && oLineage.includes(":list:"));
    if (!oIsListRow) {
      continue;
    }
    const ca = canonicalArticleFromFragmentLocator(o.fragment_locator);
    if (ca && ca.role === "article" && ca.num === hostArt.num) {
      hasStructuredListChild = true;
      break;
    }
  }
  if (!hasStructuredListChild) {
    return false;
  }
  const textLower = pf.proposition_text.toLowerCase();
  return textLower.includes("(a)") && textLower.includes("individually identified");
}

function sourceMetadata(asSource: UnknownRecord): UnknownRecord {
  return asRecord(asSource.metadata) ?? {};
}

function parseYearSlashInstrumentToken(text: string): string | null {
  const t = text.replace(/\u00a0/g, " ");
  const m = t.match(/\b(20\d{2})\s*\/\s*(\d{3,4})\b/);
  if (!m) {
    return null;
  }
  return `${m[1]}/${m[2]}`;
}

/**
 * Stable key shared by EU/UK (and other parallel) source rows for the same legal instrument.
 * Prefer source metadata `instrument_id`; otherwise parse year/number from citation or title.
 */
export function sourceInstrumentFamilyKeyFromSourceRecord(source: UnknownRecord): string {
  const md = sourceMetadata(source);
  const inst = String(
    md.instrument_id ?? md.instrumentId ?? md.instrument_identity ?? ""
  ).trim();
  if (inst) {
    return inst.replace(/\s+/g, " ").trim();
  }
  const citation = typeof source.citation === "string" ? source.citation.trim() : "";
  const title = typeof source.title === "string" ? source.title.trim() : "";
  const tok = parseYearSlashInstrumentToken(`${citation} ${title}`);
  if (tok) {
    return tok;
  }
  const id = String((source as { id?: string }).id ?? "").trim();
  return id ? `__source:${id}` : "__unknown_source__";
}

/** Jurisdiction codes present in a section or group (EU/UK first, then sorted). */
export function jurisdictionLabelsRepresented(
  rows: ReadonlyArray<UnknownRecord>,
  sources: UnknownRecord[]
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const row of rows) {
    const oa = asRecord(row.original_artifact) ?? {};
    const sid = String(oa.source_record_id ?? "").trim();
    const j = jurisdictionForSource(sources, sid).trim().toUpperCase();
    if (!j || j === "—" || seen.has(j)) {
      continue;
    }
    seen.add(j);
    out.push(j);
  }
  const rank = (x: string): number => (x === "EU" ? 0 : x === "UK" ? 1 : 2);
  return [...out].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

export function sourceInstrumentFamilyKeyForRow(
  row: UnknownRecord,
  sources: UnknownRecord[]
): string {
  const oa = asRecord(row.original_artifact) ?? {};
  const sid = String(oa.source_record_id ?? "").trim();
  if (!sid) {
    return "__no_source__";
  }
  for (const s of sources) {
    const id = String((s as { id?: string }).id ?? "").trim();
    if (id === sid) {
      return sourceInstrumentFamilyKeyFromSourceRecord(s);
    }
  }
  return `__orphan__:${sid}`;
}

/**
 * Groups UI sections: instrument/source family + provision cluster (not Article N across instruments).
 */
export function explorerSectionClusterKeyFromRow(
  row: UnknownRecord,
  sources: UnknownRecord[]
): string {
  let fam: string;
  if (sources.length > 0) {
    fam = sourceInstrumentFamilyKeyForRow(row, sources);
  } else {
    const sid = String((asRecord(row.original_artifact) ?? {}).source_record_id ?? "").trim();
    fam = sid ? `__src:${sid}` : "__no_source__";
  }
  const prov = articleClusterKeyFromRow(row);
  return `${fam}${CLUSTER_KEY_SEP}${prov}`;
}

function pickRepresentativeSourceForFamily(
  familyKey: string,
  sources: UnknownRecord[]
): UnknownRecord | undefined {
  const matches = sources.filter((s) => sourceInstrumentFamilyKeyFromSourceRecord(s) === familyKey);
  if (matches.length === 0) {
    return undefined;
  }
  const eu = matches.find((s) => String((s as { jurisdiction?: string }).jurisdiction ?? "").toUpperCase() === "EU");
  return eu ?? matches[0];
}

/** Title line for instrument (strip trailing "— Article …" from capture titles). */
export function baseInstrumentTitleFromSource(source: UnknownRecord | undefined): string {
  if (!source) {
    return "";
  }
  const raw = typeof source.title === "string" ? source.title.trim() : "";
  if (!raw) {
    return typeof source.citation === "string" ? source.citation.trim() : "";
  }
  const cut = raw.split(/\s+[—–-]\s+/)[0]?.trim() ?? raw;
  return cut || raw;
}

/** Curated readable nicknames keyed by instruments’ `YYYY/NNN` token (EU pilot corpus — display only). */
const CURATED_INSTRUMENT_SHORT_NAME: Readonly<Record<string, string>> = {
  "2015/262": "Equine Passport Regulation",
  "2016/429": "Animal Health Law",
  "2018/659": "Entry of live equidae",
  "2019/2035": "Registration / establishments",
  "2021/963": "Equine identification",
};

function clipMiddleTitleForInstrument(s: string, maxChars: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length <= maxChars) {
    return t;
  }
  const slice = t.slice(0, maxChars);
  const sp = slice.lastIndexOf(" ");
  return (sp > 30 ? slice.slice(0, sp) : slice).trim().replace(/[,;]+$/, "") || t.slice(0, maxChars);
}

/**
 * Short scan label for dropdowns / section headings. Full legal title stays on the source row and tooltips.
 * Curated corpus instruments get “YYYY/NNN — nickname”; unknowns fall back to citation + clipped title then id.
 */
export function shortInstrumentLabel(sourceRecord: UnknownRecord | undefined): string {
  if (!sourceRecord || typeof sourceRecord !== "object") {
    return "";
  }
  const citation = typeof sourceRecord.citation === "string" ? sourceRecord.citation.trim() : "";
  const rawTitle = typeof sourceRecord.title === "string" ? sourceRecord.title.trim() : "";
  const baseOfficial = rawTitle.split(/\s+[—–-]\s+/)[0]?.trim() ?? rawTitle;

  const refTok =
    parseYearSlashInstrumentToken(`${citation} ${baseOfficial || rawTitle} ${extractInstrumentIdSnippet(sourceRecord)}`) ??
    extractYearNumFromEuLexStyleCitation(citation);

  if (refTok && CURATED_INSTRUMENT_SHORT_NAME[refTok]) {
    return `${refTok} — ${CURATED_INSTRUMENT_SHORT_NAME[refTok]}`;
  }

  if (refTok) {
    const base = clipMiddleTitleForInstrument(baseInstrumentTitleFromSource(sourceRecord) || baseOfficial || rawTitle, 56);
    if (base.length >= 14) {
      return `${refTok} — ${base}`;
    }
    return refTok;
  }

  const citeShow = citation || clipMiddleTitleForInstrument(baseOfficial || rawTitle, 72);
  if (citeShow) {
    return citeShow.length > 88 ? `${citeShow.slice(0, 84)}…` : citeShow;
  }

  const id = String((sourceRecord as { id?: string }).id ?? "").trim();
  return id || "—";
}

function extractInstrumentIdSnippet(source: UnknownRecord): string {
  const md = asRecord(source.metadata) ?? {};
  const inst = (
    md.instrument_id ?? md.instrumentId ?? md.instrument_identity ?? ""
  ) as string;
  return String(inst).trim();
}

/** Match `32016R0429` etc. embedded in CELEX-ish tokens for slash display. */
function extractYearNumFromEuLexStyleCitation(citation: string): string | null {
  const m = citation.replace(/\u00a0/g, " ").match(/(20\d{2})[Rr]0*(\d{3,5})/i);
  if (!m?.[2]) {
    return null;
  }
  const yr = m[1];
  const tail = parseInt(String(m[2]).replace(/^0+/, "") || "0", 10);
  if (!Number.isFinite(tail)) {
    return null;
  }
  return `${yr}/${tail}`;
}

const INSTRUMENT_FAMILY_HUMAN_NAMES: Readonly<Record<string, string>> = {
  "EU 2016/429": "2016/429 Animal Health Law",
  "2016/429": "2016/429 Animal Health Law",
  "EU 2015/262": "2015/262 Equine Passport Regulation",
  "2015/262": "2015/262 Equine Passport Regulation",
  "EU 2019/2035": "2019/2035 Delegated identification rules",
  "2019/2035": "2019/2035 Delegated identification rules",
  "EU 2021/963": "2021/963 Equine identification implementation",
  "2021/963": "2021/963 Equine identification implementation",
  "EU 2020/688": "2020/688 movement / entry (related)",
  "EU 2020/692": "2020/692 movement / entry (related)",
};

export function instrumentFamilyFilterLabel(familyKey: string): string {
  if (INSTRUMENT_FAMILY_HUMAN_NAMES[familyKey]) {
    return INSTRUMENT_FAMILY_HUMAN_NAMES[familyKey]!;
  }
  const slash = parseYearSlashInstrumentToken(familyKey);
  if (slash && INSTRUMENT_FAMILY_HUMAN_NAMES[slash]) {
    return INSTRUMENT_FAMILY_HUMAN_NAMES[slash]!;
  }
  for (const [k, v] of Object.entries(INSTRUMENT_FAMILY_HUMAN_NAMES)) {
    if (familyKey.includes(k) || k.includes(familyKey)) {
      return v;
    }
  }
  if (familyKey.startsWith("__")) {
    return familyKey;
  }
  return familyKey.length > 72 ? `${familyKey.slice(0, 68)}…` : familyKey;
}

export type ExplorerSectionHeading = {
  /** Narrow layouts: `{primaryInstrumentLine} · {provisionLine}` */
  headline: string;
  headlineCompact: string;
  subtitle: string;
  primaryInstrumentLine: string;
  provisionLine: string;
  metadataLine: string;
  /** Official instrument title without Article tail (first segment before em dash split). */
  fullOfficialInstrumentTitle: string;
  /** Hover: full stored title · citation where useful. */
  fullTitleTooltip: string;
  /** Citation on representative source row (CELEX/OJ id), when present — details panel. */
  representativeCitation: string;
};

function jurisdictionPrettyForMetadata(labels: string[]): string {
  if (labels.length === 0) {
    return "";
  }
  return labels
    .map((x) => {
      const u = x.trim().toUpperCase();
      if (u === "EU") {
        return "🇪🇺 EU";
      }
      if (u === "UK") {
        return "🇬🇧 UK";
      }
      return x.trim();
    })
    .join(", ");
}

export function formatExplorerSectionHeading(
  sectionClusterKey: string,
  sources: UnknownRecord[],
  sectionRows: ReadonlyArray<UnknownRecord>,
  options?: {
    fragments?: ReadonlyArray<{
      locator?: string;
      structural_heading?: { text?: string | null } | null;
    }>;
  },
): ExplorerSectionHeading {
  const sep = sectionClusterKey.indexOf(CLUSTER_KEY_SEP);
  const familyKey = sep >= 0 ? sectionClusterKey.slice(0, sep).trim() : "";
  const provisionKey = sep >= 0 ? sectionClusterKey.slice(sep + 1).trim() : sectionClusterKey;
  const rep = pickRepresentativeSourceForFamily(familyKey, sources);
  let legislativeHeading: string | null = null;
  const artMatch = provisionKey.match(/^article:(\d+[a-z]?)$/i);
  if (artMatch && options?.fragments) {
    const want = `article:${artMatch[1]!.toLowerCase()}`;
    for (const frag of options.fragments) {
      if (String(frag.locator ?? "").toLowerCase() === want) {
        const text = String(frag.structural_heading?.text ?? "")
          .replace(/\u00a0/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        if (text) {
          legislativeHeading = text;
          break;
        }
      }
    }
  }
  const provHeadline = formatArticleClusterDisplayHeading(provisionKey, {
    legislativeHeading,
  });
  const js = jurisdictionLabelsRepresented(sectionRows, sources);
  const jPretty = jurisdictionPrettyForMetadata(js);
  const terrPretty = territoryLabelsRepresented(sectionRows);
  const cite = rep && typeof rep.citation === "string" ? rep.citation.trim() : "";

  const rawStoredTitle =
    rep && typeof rep.title === "string" ? rep.title.replace(/\u00a0/g, " ").trim() : "";
  const strippedForMeta = rawStoredTitle
    ? rawStoredTitle.replace(/\s+[—–-]\s+Article\b.*$/is, "").trim() || rawStoredTitle
    : "";
  /** One-line identity for subtitles (drops trailing “— Article …” from capture titles). */
  let metaOfficial = strippedForMeta || baseInstrumentTitleFromSource(rep);
  if (!metaOfficial.trim() && cite) {
    metaOfficial = cite;
  }
  metaOfficial = metaOfficial.trim();
  /** Pair opaque CELEX-style citations when they are not redundant with slash reference in title. */
  if (cite && !metaOfficial.includes(cite.trim()) && !/\bEU\s?\)\s*20\d{2}\//i.test(metaOfficial)) {
    metaOfficial =
      cite.length <= 56 && cite ? `${metaOfficial} · citation: ${cite}` : `${metaOfficial} · ${cite}`;
  }

  const rowCount = sectionRows.length;

  const primaryInstrumentLine =
    sources.length === 0
      ? familyKey.startsWith("__src:")
        ? familyKey.slice(6).trim()
        : familyKey.startsWith("__")
          ? "Unknown source cluster"
          : familyKey || provHeadline
      : shortInstrumentLabel(rep ?? undefined) || cite || familyKey;

  const fullTitleTooltipPieces = [
    rawStoredTitle || metaOfficial || cite || "",
    cite && rawStoredTitle && !rawStoredTitle.includes(cite) ? cite : "",
  ].filter(Boolean);
  const fullTitleTooltip = [...new Set(fullTitleTooltipPieces)]
    .join(" · ")
    .replace(/\s*·\s*·+/g, " · ")
    .trim();

  const metadataLineParts: string[] = [];
  if (metaOfficial.trim()) {
    metadataLineParts.push(metaOfficial.trim());
  }
  if (jPretty) {
    metadataLineParts.push(`source jurisdiction: ${jPretty}`);
  }
  if (terrPretty.length > 0) {
    metadataLineParts.push(`applies in: ${terrPretty.join(", ")}`);
  }
  metadataLineParts.push(`source rows: ${rowCount}`);
  const metadataLine = metadataLineParts.join(" · ");

  const headlineCompact =
    primaryInstrumentLine && provHeadline
      ? `${primaryInstrumentLine} · ${provHeadline}`
      : provHeadline;

  return {
    headline: headlineCompact,
    headlineCompact,
    subtitle: metadataLine,
    primaryInstrumentLine: primaryInstrumentLine || provHeadline,
    provisionLine: provHeadline,
    metadataLine,
    fullOfficialInstrumentTitle:
      rawStoredTitle || strippedForMeta || baseInstrumentTitleFromSource(rep) || cite || familyKey,
    fullTitleTooltip: fullTitleTooltip || metaOfficial || familyKey,
    representativeCitation: cite,
  };
}

/** Visible label only; combine with {@link sourceDocumentFilterOptionTitle} on `<option title=…>` for full title. */
export function sourceDocumentFilterLabel(
  sourceId: string,
  sources: UnknownRecord[],
  titleById: ReadonlyMap<string, string>
): string {
  const jRaw = jurisdictionForSource(sources, sourceId).trim();
  const jU = jRaw.toUpperCase();
  let src: UnknownRecord | undefined;
  for (const s of sources) {
    if (String((s as { id?: string }).id ?? "").trim() === sourceId) {
      src = s;
      break;
    }
  }
  if (!src) {
    const fallback = titleById.get(sourceId)?.trim() ?? sourceId;
    return !jRaw || jRaw === "—" ? fallback : `${jU === "EU" ? "🇪🇺 " : jU === "UK" ? "🇬🇧 " : ""}${fallback}`;
  }

  const short = shortInstrumentLabel(src);
  if (jU === "EU") {
    return short.startsWith("🇪🇺") ? short : `🇪🇺 ${short}`;
  }
  if (jU === "UK") {
    return short.startsWith("🇬🇧") ? short : `🇬🇧 ${short}`;
  }
  if (!jRaw || jRaw === "—") {
    return short;
  }
  return `${short} — ${jRaw}`;
}

/** Full legal title (+ citation after middle dot when both exist) — use as native tooltip on dropdown options. */
export function sourceDocumentFilterOptionTitle(
  sourceId: string,
  sources: UnknownRecord[],
  titleById: ReadonlyMap<string, string>
): string {
  let src: UnknownRecord | undefined;
  for (const s of sources) {
    if (String((s as { id?: string }).id ?? "").trim() === sourceId) {
      src = s;
      break;
    }
  }
  const fullTitle = src && typeof src.title === "string" && src.title.trim() ? src.title.trim() : "";
  const cite = src && typeof src.citation === "string" && src.citation.trim() ? src.citation.trim() : "";
  const fb = titleById.get(sourceId)?.trim();
  const body = fullTitle || fb || "";
  const parts = [body, cite && body !== cite ? cite : ""].filter(Boolean);
  const line = parts.join(" · ").trim();
  return line.length > 560 ? `${line.slice(0, 556)}…` : line;
}

/** Strip optional partition suffix from a subgroup key for display. */
export function stripPropositionSubgroupPartitionSuffix(key: string): string {
  const i = key.indexOf(PARTITION_SUBGROUP_APPEND_SEP);
  return i >= 0 ? key.slice(0, i) : key;
}

export function compactPropositionSourceSummaryLines(
  rows: UnknownRecord[],
  sources: UnknownRecord[]
): string[] {
  const lines: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const oa = asRecord(row.original_artifact) ?? {};
    const sid = String(oa.source_record_id ?? "").trim();
    const key = sid || String(oa.id ?? "");
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    let src: UnknownRecord | undefined;
    for (const s of sources) {
      if (String((s as { id?: string }).id ?? "").trim() === sid) {
        src = s;
        break;
      }
    }
    const disp = jurisdictionDisplay(jurisdictionForSource(sources, sid), sid);
    const title = baseInstrumentTitleFromSource(src);
    const jUpper = jurisdictionForSource(sources, sid).toUpperCase();
    const ys = parseYearSlashInstrumentToken(
      `${typeof src?.citation === "string" ? src.citation : ""} ${title}`
    );
    let body: string;
    if (title) {
      if (jUpper === "UK" && /\bretained\b/i.test(title)) {
        body = ys ? `UK retained ${ys}` : title;
      } else {
        body = title;
      }
    } else {
      body = sid || "Unknown source";
    }
    const prefix = disp.icon ? `${disp.icon} ` : "· ";
    lines.push(`${prefix}${body}`.trim());
  }
  return lines;
}

export function compareExplorerSectionClusterKeys(a: string, b: string): number {
  const sa = a.indexOf(CLUSTER_KEY_SEP);
  const sb = b.indexOf(CLUSTER_KEY_SEP);
  const fa = sa >= 0 ? a.slice(0, sa) : "";
  const fb = sb >= 0 ? b.slice(0, sb) : "";
  if (fa !== fb) {
    return fa.localeCompare(fb);
  }
  const pa = sa >= 0 ? a.slice(sa + 1) : a;
  const pb = sb >= 0 ? b.slice(sb + 1) : b;
  return compareArticleClusterKeys(pa, pb);
}

function groupKeyCoreForPropositionRow(row: UnknownRecord): string {
  const oa = asRecord(row.original_artifact) ?? {};
  const pf = propositionArtifactFields(row);
  const loc = pf.fragment_locator;
  const lineageKey = canonicalLineageKeyForGrouping(loc);
  if (lineageKey) {
    // `:list:` paths are precise → key directly so EU/UK merge. Bare `:para:` paragraphs can hold
    // several distinct rules → discriminate by text (identical EU/UK wording still merges).
    if (lineageKey.includes(":list:")) {
      return lineageKey;
    }
    const nt = normalizePropositionTextForLineageGroup(pf.proposition_text);
    return nt ? `${lineageKey}::${nt}` : lineageKey;
  }
  if (loc && isCoarseArticleScopedLocator(loc)) {
    const nt = normalizePropositionTextForLineageGroup(pf.proposition_text);
    if (nt) {
      return `__coarse_article:${stripLocatorNamespaceForStem(loc)}::${nt}`;
    }
  }
  const pk = String(oa.proposition_key ?? "").trim() || pf.proposition_key;
  if (pk) {
    return pk;
  }
  const id = String(oa.id ?? "").trim() || pf.id;
  return id ? `__opaque:${id}` : `__row:${Math.random().toString(36).slice(2)}`;
}

/**
 * Lineage group key: same structured provision across parallel source versions of one instrument
 * (requires `sources` so EU/UK rows can merge while different instruments stay separate).
 */
export function groupKeyForPropositionRow(row: UnknownRecord, sources?: UnknownRecord[]): string {
  const core = groupKeyCoreForPropositionRow(row);
  if (!sources || sources.length === 0) {
    return core;
  }
  const fam = sourceInstrumentFamilyKeyForRow(row, sources);
  return `${fam}${CLUSTER_KEY_SEP}${core}`;
}

/** Field separator for {@link rowExplorerSemanticMergeKey}. */
const SEMANTIC_MERGE_KEY_FIELD_SEP = "\u001d";
const SEMANTIC_MERGE_GROUP_ROW_SEP = "\u001e";

function primaryScopeIdsSignatureForExplorerMerge(
  propositionId: string,
  scopeLinkRowsByPropId: Map<string, UnknownRecord[]>
): string {
  const pid = propositionId.trim();
  if (!pid) {
    return "";
  }
  const links = scopeLinkRowsByPropId.get(pid) ?? [];
  const ids: string[] = [];
  for (const ln of links) {
    const r = asRecord(ln) ?? {};
    if (!isPrimaryScopeLinkRow(r)) {
      continue;
    }
    ids.push(String((ln as { scope_id?: string }).scope_id ?? "").trim());
  }
  ids.sort();
  return ids.join(",");
}

/**
 * Stable identity for collapsing duplicate explorer groups: instrument family, jurisdiction,
 * article cluster, provision lineage (or stable fallback), normalized proposition text, review
 * layer, optional proposition kind, and primary taxonomy links.
 */
export function rowExplorerSemanticMergeKey(
  row: UnknownRecord,
  sources: UnknownRecord[],
  scopeLinkRowsByPropId?: Map<string, UnknownRecord[]>,
  scopeById?: Map<string, UnknownRecord>
): string {
  const oa = asRecord(row.original_artifact) ?? {};
  const pf = propositionArtifactFields(row);
  const fam = sourceInstrumentFamilyKeyForRow(row, sources);
  const sid = String(oa.source_record_id ?? "").trim();
  const jur = jurisdictionForSource(sources, sid).trim().toLowerCase();
  const art = articleClusterKeyFromRow(row);
  const locRaw = String(pf.fragment_locator ?? "").trim();
  const lin = locRaw ? canonicalLineageKeyForGrouping(locRaw) : null;
  const lineagePart =
    lin ??
    `__no_lineage__:${locRaw}:${String(oa.proposition_key ?? pf.proposition_key ?? "").trim()}`;
  const text = normalizePropositionTextForLineageGroup(pf.proposition_text);
  const status = String(row.effective_status ?? "").trim().toLowerCase();
  const kind = String(
    (oa as { kind?: unknown }).kind ?? (oa as { proposition_type?: unknown }).proposition_type ?? ""
  )
    .trim()
    .toLowerCase();
  const pid = String(oa.id ?? "").trim();
  let scopeSig = "";
  if (scopeLinkRowsByPropId && scopeById && pid) {
    scopeSig = primaryScopeIdsSignatureForExplorerMerge(pid, scopeLinkRowsByPropId);
  }
  return [fam, jur, art, lineagePart, text, status, kind, scopeSig].join(SEMANTIC_MERGE_KEY_FIELD_SEP);
}

function groupSemanticMergeSignature(
  group: { rows: UnknownRecord[] },
  sources: UnknownRecord[],
  scopeLinkRowsByPropId?: Map<string, UnknownRecord[]>,
  scopeById?: Map<string, UnknownRecord>
): string {
  const keys = group.rows.map((r) =>
    rowExplorerSemanticMergeKey(r, sources, scopeLinkRowsByPropId, scopeById)
  );
  keys.sort();
  return keys.join(SEMANTIC_MERGE_GROUP_ROW_SEP);
}

/** Observability payload when multiple explorer groups collapse into one card. */
export type PropositionExplorerGroupMergeDebug = {
  mergedGroupCount: number;
  mergedGroupIds: string[];
  mergedArtifactIds: string[];
  canonicalLineageKey: string | null;
  contributingLocatorForms: string[];
  contributingPropositionKeys: string[];
};

export type PropositionExplorerMergedPropositionGroup = {
  key: string;
  rows: UnknownRecord[];
  mergeDebug?: PropositionExplorerGroupMergeDebug;
};

/**
 * Raw/debug-only panel: show when merge combined different locator strings or distinct artifacts.
 */
export function shouldShowPropositionGroupMergeLocatorDebug(
  meta: PropositionExplorerGroupMergeDebug | undefined
): boolean {
  if (!meta || meta.mergedGroupCount <= 1) {
    return false;
  }
  const distinctLocators = new Set(meta.contributingLocatorForms).size;
  const distinctArtifacts = new Set(meta.mergedArtifactIds).size;
  return distinctLocators > 1 || distinctArtifacts > 1;
}

/** Per-row strings merged into merge-debug locator forms / proposition keys. */
export function collectRowContributionsForMergeDebug(row: UnknownRecord): {
  locatorForms: string[];
  propositionKeys: string[];
} {
  const oa = asRecord(row.original_artifact) ?? {};
  const pf = propositionArtifactFields(row);
  const locatorForms: string[] = [];
  const fl = String(pf.fragment_locator ?? "").trim();
  if (fl) {
    locatorForms.push(fl);
  }
  const ar = typeof oa.article_reference === "string" ? oa.article_reference.trim() : "";
  if (ar) {
    locatorForms.push(`article_ref:${ar}`);
  }
  const lab = typeof oa.label === "string" ? oa.label.trim() : "";
  if (lab) {
    locatorForms.push(`label:${lab}`);
  }
  const ack = articleClusterKeyFromRow(row);
  if (ack) {
    locatorForms.push(`article_cluster:${ack}`);
  }
  const propositionKeys: string[] = [];
  const pk = String(oa.proposition_key ?? pf.proposition_key ?? "").trim();
  if (pk) {
    propositionKeys.push(pk);
  }
  return { locatorForms, propositionKeys };
}

function canonicalLineageKeyFromMergedRows(rows: UnknownRecord[]): string | null {
  for (const r of rows) {
    const pf = propositionArtifactFields(r);
    const loc = String(pf.fragment_locator ?? "").trim();
    if (!loc) {
      continue;
    }
    const c = canonicalLineageKeyForGrouping(loc);
    if (c) {
      return c;
    }
  }
  return null;
}

export function dedupePropositionRowsByArtifactId(rows: UnknownRecord[]): UnknownRecord[] {
  const seen = new Set<string>();
  const out: UnknownRecord[] = [];
  for (const r of rows) {
    const oa = asRecord(r.original_artifact) ?? {};
    const id = String(oa.id ?? "").trim();
    if (id) {
      if (seen.has(id)) {
        continue;
      }
      seen.add(id);
    }
    out.push(r);
  }
  return out;
}

export function sortPropositionExplorerGroupRows(
  rows: UnknownRecord[],
  sources: UnknownRecord[]
): UnknownRecord[] {
  return [...rows].sort((a, b) => {
    const oa = asRecord(a.original_artifact) ?? {};
    const ob = asRecord(b.original_artifact) ?? {};
    const sa = String(oa.source_record_id ?? "").trim();
    const sb = String(ob.source_record_id ?? "").trim();
    const ja = jurisdictionForSource(sources, sa).toUpperCase();
    const jb = jurisdictionForSource(sources, sb).toUpperCase();
    const ra = ja === "EU" ? 0 : ja === "UK" ? 1 : 2;
    const rb = jb === "EU" ? 0 : jb === "UK" ? 1 : 2;
    if (ra !== rb) {
      return ra - rb;
    }
    return sa.localeCompare(sb);
  });
}

/**
 * Merges explorer groups that encode the same logical proposition (duplicate extractions or
 * locator spelling variants). Preserves all source rows on the merged card and optional
 * {@link PropositionExplorerGroupMergeDebug} when multiple input groups collapsed.
 */
export function mergeSemanticallyDuplicatePropositionGroups(
  groups: ReadonlyArray<{ key: string; rows: UnknownRecord[] }>,
  sources: UnknownRecord[],
  scopeLinkRowsByPropId?: Map<string, UnknownRecord[]>,
  scopeById?: Map<string, UnknownRecord>
): PropositionExplorerMergedPropositionGroup[] {
  type Bucket = {
    key: string;
    rows: UnknownRecord[];
    sourceGroupKeys: string[];
    locatorForms: Set<string>;
    propositionKeys: Set<string>;
  };
  const buckets = new Map<string, Bucket>();

  for (const g of groups) {
    if (!g.rows.length) {
      continue;
    }
    const sig = groupSemanticMergeSignature(g, sources, scopeLinkRowsByPropId, scopeById);
    const existing = buckets.get(sig);
    if (!existing) {
      const locatorForms = new Set<string>();
      const propositionKeys = new Set<string>();
      for (const r of g.rows) {
        const c = collectRowContributionsForMergeDebug(r);
        for (const x of c.locatorForms) {
          locatorForms.add(x);
        }
        for (const x of c.propositionKeys) {
          propositionKeys.add(x);
        }
      }
      buckets.set(sig, {
        key: g.key,
        rows: dedupePropositionRowsByArtifactId([...g.rows]),
        sourceGroupKeys: [g.key],
        locatorForms,
        propositionKeys,
      });
    } else {
      existing.sourceGroupKeys.push(g.key);
      for (const r of g.rows) {
        const c = collectRowContributionsForMergeDebug(r);
        for (const x of c.locatorForms) {
          existing.locatorForms.add(x);
        }
        for (const x of c.propositionKeys) {
          existing.propositionKeys.add(x);
        }
      }
      existing.rows = dedupePropositionRowsByArtifactId([...existing.rows, ...g.rows]);
      if (g.key.localeCompare(existing.key) < 0) {
        existing.key = g.key;
      }
    }
  }

  return [...buckets.values()].map((b) => {
    const rows = sortPropositionExplorerGroupRows(b.rows, sources);
    const mergedGroupIds = [...new Set(b.sourceGroupKeys)].sort((x, y) => x.localeCompare(y));
    let mergeDebug: PropositionExplorerGroupMergeDebug | undefined;
    if (mergedGroupIds.length > 1) {
      const mergedArtifactIds = [
        ...new Set(
          rows
            .map((r) => String((asRecord(r.original_artifact) ?? {}).id ?? "").trim())
            .filter(Boolean)
        ),
      ].sort((x, y) => x.localeCompare(y));
      mergeDebug = {
        mergedGroupCount: mergedGroupIds.length,
        mergedGroupIds,
        mergedArtifactIds,
        canonicalLineageKey: canonicalLineageKeyFromMergedRows(rows),
        contributingLocatorForms: [...b.locatorForms].sort((x, y) => x.localeCompare(y)),
        contributingPropositionKeys: [...b.propositionKeys].sort((x, y) => x.localeCompare(y)),
      };
    }
    return { key: b.key, rows, mergeDebug };
  });
}

function stripLocatorNamespaceForStem(loc: string): string {
  const t = loc.trim().replace(/__+/g, "-");
  const colonIdx = t.indexOf(":");
  if (colonIdx > 0 && colonIdx < 24) {
    const head = t.slice(0, colonIdx).toLowerCase();
    const rest = t.slice(colonIdx + 1).trim();
    if (head !== "article" && head !== "section" && /^[a-z][a-z0-9_-]{0,20}$/.test(head)) {
      return rest.toLowerCase();
    }
  }
  return t.toLowerCase();
}

export type ArticleLocatorParse = { role: "article" | "section"; num: string; suffix: string };

/** Parse `article_reference` into a stable article/section token (UI grouping). */
export function parseArticleNumberFromReference(ar: string): ArticleLocatorParse | null {
  const t = ar.trim();
  if (!t) {
    return null;
  }
  const labeled = t.match(/\b(?:article|art\.?)\s*(\d+[a-z]?)(?:\s*[—–-]\s*.*)?$/i);
  if (labeled) {
    return { role: "article", num: labeled[1].toLowerCase(), suffix: "" };
  }
  const secLab = t.match(/\b(?:section|sec\.?)\s*(\d+[a-z]?)(?:\s*[—–-]\s*.*)?$/i);
  if (secLab) {
    return { role: "section", num: secLab[1].toLowerCase(), suffix: "" };
  }
  const bareNum = t.match(/^(\d+[a-z]?)$/);
  if (bareNum) {
    return { role: "article", num: bareNum[1].toLowerCase(), suffix: "" };
  }
  return null;
}

/**
 * Canonical article identity from `fragment_locator` for clustering. Strips `:list:` tails, `/fragment` paths,
 * namespace prefixes, and trailing paragraph/item segments.
 */
export function canonicalArticleFromFragmentLocator(rawLoc: string): ArticleLocatorParse | null {
  let t = rawLoc.trim();
  if (!t || GENERIC_FRAGMENT_LOCATORS.has(t.toLowerCase())) {
    return null;
  }
  const li = t.indexOf(":list:");
  if (li >= 0) {
    t = t.slice(0, li).trim();
  }
  const si = t.indexOf("/");
  if (si > 0 && si <= 200) {
    t = t.slice(0, si).trim();
  }
  const colonIdx = t.indexOf(":");
  if (colonIdx > 0 && colonIdx < 24) {
    const head = t.slice(0, colonIdx).toLowerCase();
    const rest = t.slice(colonIdx + 1).trim();
    const headIsRole = head === "article" || head === "section";
    if (!headIsRole && /^[a-z][a-z0-9_-]{0,20}$/.test(head)) {
      t = rest;
    }
  }
  t = t.replace(/__+/g, "-");
  const roleHint: "article" | "section" = /section/i.test(t) ? "section" : "article";
  const artSeg = t.match(/(?:article|section)[:/_-](\d+[a-z]?)/i);
  if (artSeg) {
    const r = /section/i.test(artSeg[0]) ? "section" : /section/i.test(t) ? "section" : "article";
    return { role: r, num: artSeg[1].toLowerCase(), suffix: "" };
  }
  const hyphenArt = t.match(/(?:article|section)-(\d+[a-z]?)(?:[-_.\/](?:\d+|[ivxlcdm]+).*)?$/i);
  if (hyphenArt) {
    return {
      role: hyphenArt[0].toLowerCase().includes("section")
        ? "section"
        : roleHint === "section"
          ? "section"
          : "article",
      num: hyphenArt[1].toLowerCase(),
      suffix: "",
    };
  }
  const glued = t.match(/(?:article|section)(\d+[a-z]?)(?:[-_./](?:\d+|[ivxlcdm]+).*)?$/i);
  if (glued) {
    return {
      role: glued[0].toLowerCase().includes("section")
        ? "section"
        : roleHint === "section"
          ? "section"
          : "article",
      num: glued[1].toLowerCase(),
      suffix: "",
    };
  }
  /** `Article 114(1)(a)` — space after "Article", optional points in parentheses */
  const spacedArticle = t.match(/^article\s+(\d+[a-z]?)\b/i);
  if (spacedArticle && !/^section\b/i.test(t)) {
    return {
      role: "article",
      num: spacedArticle[1].toLowerCase(),
      suffix: "",
    };
  }
  return null;
}

/**
 * Canonical article-section cluster key (shared by EU/UK rows). Omits `source_record_id` when
 * article_reference or fragment_locator yields an identity.
 *
 * Prefer a parsed `fragment_locator` over `article_reference` so parent-scope references (e.g. Article
 * 109 intro) do not override list/item locators that point at another article (e.g. `article:114:list:…`).
 */
export function canonicalArticleClusterKey(oa: UnknownRecord): string | null {
  const ar = typeof oa.article_reference === "string" ? oa.article_reference.trim() : "";
  const loc = typeof oa.fragment_locator === "string" ? oa.fragment_locator.trim() : "";
  const fromLoc = loc ? canonicalArticleFromFragmentLocator(loc) : null;

  if (fromLoc) {
    return `${fromLoc.role}:${fromLoc.num}${fromLoc.suffix}`;
  }

  if (ar) {
    const p = parseArticleNumberFromReference(ar);
    if (p) {
      return `${p.role}:${p.num}${p.suffix}`;
    }
    const norm = ar
      .toLowerCase()
      .replace(/\s+/g, " ")
      .replace(/[^\p{L}\p{N} _./:-]/gu, "")
      .trim()
      .slice(0, 160);
    if (norm) {
      return `ref:${norm}`;
    }
  }

  if (loc && !GENERIC_FRAGMENT_LOCATORS.has(loc.toLowerCase())) {
    let base = loc.includes(":list:") ? (loc.split(":list:", 2)[0] ?? "").trim() : loc;
    const slashIdx = base.indexOf("/");
    if (slashIdx > 0) {
      base = base.slice(0, slashIdx).trim();
    }
    base = base.toLowerCase().replace(/__+/g, "-").trim();
    if (base.length > 0 && base.length <= 140) {
      return `loc:${base}`;
    }
  }
  return null;
}

/**
 * When the structured locator is in one article but `article_reference` cites a later article
 * (in-text forward cross-reference), surface a short banner — not for "mis-bucketed" rows where the
 * locator already targets the cited article.
 */
export function relatedCrossReferenceDisplayLine(oa: UnknownRecord): string | null {
  const ar = typeof oa.article_reference === "string" ? oa.article_reference.trim() : "";
  const loc = typeof oa.fragment_locator === "string" ? oa.fragment_locator.trim() : "";
  if (!ar || !loc) {
    return null;
  }
  const fromLoc = canonicalArticleFromFragmentLocator(loc);
  const refParsed = parseArticleNumberFromReference(ar);
  if (
    !fromLoc ||
    !refParsed ||
    fromLoc.role !== "article" ||
    refParsed.role !== "article" ||
    fromLoc.num === refParsed.num
  ) {
    return null;
  }
  const hostN = parseInt(fromLoc.num.replace(/[^0-9]/g, ""), 10);
  const refN = parseInt(refParsed.num.replace(/[^0-9]/g, ""), 10);
  if (!Number.isFinite(hostN) || !Number.isFinite(refN) || refN <= hostN) {
    return null;
  }
  const cited = formatArticleClusterHeading(`article:${refParsed.num}`);
  return `Related cross-reference to ${cited}`;
}

/** Optional article-level phrase for known EU pilot articles (display-only fallback). */
const ARTICLE_HEADLINE_SUBTITLE: Partial<Record<string, string>> = {
  "109": "database of kept terrestrial animals",
  "114": "identification of kept equine animals",
};

export type ArticleClusterDisplayHeadingOptions = {
  /** Source-captured legislative heading text (preferred over compatibility subtitles). */
  legislativeHeading?: string | null;
};

/**
 * Article section banner precedence:
 * 1. captured source legislative heading
 * 2. existing compatibility subtitle (109/114) when source data unavailable
 * 3. locator-derived display label
 */
export function formatArticleClusterDisplayHeading(
  clusterKey: string,
  options?: ArticleClusterDisplayHeadingOptions,
): string {
  const art = clusterKey.match(/^article:(\d+)([a-z]?)$/i);
  if (art) {
    // Preserve locator letter case (Article 49a), matching CLML number_label.
    const suf = art[2] ?? "";
    const num = art[1];
    const captured = String(options?.legislativeHeading ?? "")
      .replace(/\u00a0/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (captured) {
      return `Article ${num}${suf} — ${captured}`;
    }
    const sub = ARTICLE_HEADLINE_SUBTITLE[num.toLowerCase()];
    if (sub) {
      return `Article ${num}${suf} — ${sub}`;
    }
    return `Article ${num}${suf}`;
  }
  return formatArticleClusterHeading(clusterKey);
}

/** Title-case leading "article N" / "section N" segments inside free-text cluster titles (ref:/loc:). */
export function prettifyArticleHeadingFragment(inner: string): string {
  const t = inner.trim();
  if (!t) {
    return t;
  }
  return t
    .replace(/\barticle\s+(\d+[a-z]?)\b/gi, (_m, num: string) => `Article ${num}`)
    .replace(/\bsection\s+(\d+[a-z]?)\b/gi, (_m, num: string) => `Section ${num}`);
}

/** Human title for a cluster key (`article:109` → `Article 109`). */
export function formatArticleClusterHeading(clusterKey: string): string {
  const k = clusterKey.includes(PARTITION_SUBGROUP_APPEND_SEP)
    ? clusterKey.split(PARTITION_SUBGROUP_APPEND_SEP)[0] ?? clusterKey
    : clusterKey;
  if (k.includes(CLUSTER_KEY_SEP)) {
    const partsTail = k.split(CLUSTER_KEY_SEP, 2)[1];
    if (partsTail === "__no_canonical_article__") {
      return "Unspecified article / locator";
    }
    return partsTail ? formatArticleClusterHeading(partsTail) : "Unspecified article / locator";
  }
  const refP = k.match(/^ref:(.+)$/);
  if (refP) {
    const inner = prettifyArticleHeadingFragment(refP[1]);
    return inner.length > 72 ? `${inner.slice(0, 68)}…` : inner;
  }
  const locP = k.match(/^loc:(.+)$/);
  if (locP) {
    const inner = prettifyArticleHeadingFragment(locP[1]);
    return inner.length > 72 ? `${inner.slice(0, 68)}…` : inner;
  }
  const art = k.match(/^article:(\d+)([a-z]?)$/i);
  if (art) {
    const suf = art[2] ? art[2].toUpperCase() : "";
    return `Article ${art[1]}${suf}`;
  }
  const sec = k.match(/^section:(\d+)([a-z]?)$/i);
  if (sec) {
    const suf = sec[2] ? sec[2].toUpperCase() : "";
    return `Section ${sec[1]}${suf}`;
  }
  return k.length > 88 ? `${k.slice(0, 84)}…` : k;
}

type ParsedClusterSort = { tier: number; n: number; suf: string; tail: string };

function provisionClusterKeyForSort(key: string): string {
  const noPart = key.includes(PARTITION_SUBGROUP_APPEND_SEP)
    ? key.split(PARTITION_SUBGROUP_APPEND_SEP)[0] ?? key
    : key;
  const si = noPart.indexOf(CLUSTER_KEY_SEP);
  if (si >= 0) {
    return noPart.slice(si + 1).trim() || noPart;
  }
  return noPart;
}

function parseClusterKeyForSort(key: string): ParsedClusterSort {
  const prov = provisionClusterKeyForSort(key);
  const am = prov.match(/^article:(\d+)([a-z]?)$/i);
  if (am) {
    return { tier: 0, n: parseInt(am[1], 10), suf: (am[2] ?? "").toLowerCase(), tail: "" };
  }
  const sm = prov.match(/^section:(\d+)([a-z]?)$/i);
  if (sm) {
    return { tier: 1, n: parseInt(sm[1], 10), suf: (sm[2] ?? "").toLowerCase(), tail: "" };
  }
  if (prov.startsWith("ref:")) {
    return { tier: 2, n: 0, suf: "", tail: prov.slice(4) };
  }
  if (prov.startsWith("loc:")) {
    return { tier: 3, n: 0, suf: "", tail: prov.slice(4) };
  }
  if (prov !== key && prov) {
    return { tier: 4, n: 0, suf: "", tail: prov };
  }
  return { tier: 5, n: 0, suf: "", tail: key };
}

export function compareArticleClusterKeys(a: string, b: string): number {
  const pa = parseClusterKeyForSort(a);
  const pb = parseClusterKeyForSort(b);
  if (pa.tier !== pb.tier) {
    return pa.tier - pb.tier;
  }
  if (pa.tier <= 1) {
    if (pa.n !== pb.n) {
      return pa.n - pb.n;
    }
    const c = pa.suf.localeCompare(pb.suf);
    if (c !== 0) {
      return c;
    }
    return 0;
  }
  return pa.tail.localeCompare(pb.tail);
}

/** Debug fallback segment when no canonical key. */
export function articleClusterSegment(oa: UnknownRecord): string {
  const ar = typeof oa.article_reference === "string" ? oa.article_reference.trim() : "";
  if (ar) {
    return ar;
  }
  const loc = typeof oa.fragment_locator === "string" ? oa.fragment_locator.trim() : "";
  if (!loc || GENERIC_FRAGMENT_LOCATORS.has(loc.toLowerCase())) {
    return "__unspecified__";
  }
  if (loc.includes(":list:")) {
    const base = loc.split(":list:", 2)[0]?.trim() ?? "";
    return base || "__unspecified__";
  }
  const slashIdx = loc.indexOf("/");
  if (slashIdx > 0 && slashIdx <= 140) {
    return loc.slice(0, slashIdx).trim();
  }
  const cap = 96;
  return loc.length <= cap ? loc : `${loc.slice(0, cap)}…`;
}

export function articleClusterKeyFromOriginalArtifact(oa: UnknownRecord): string {
  const canon = canonicalArticleClusterKey(oa);
  if (canon !== null) {
    return canon;
  }
  const sid = String(oa.source_record_id ?? "").trim() || "__no_source__";
  return `${sid}${CLUSTER_KEY_SEP}__no_canonical_article__`;
}

export function articleClusterKeyFromRow(row: UnknownRecord): string {
  const oa = asRecord(row.original_artifact) ?? {};
  return articleClusterKeyFromOriginalArtifact(oa);
}

/** Count source rows hidden by default coarse-parent suppression, keyed by explorer section cluster. */
export function suppressedParentListSummaryCountByArticleCluster(
  rowsMatchingFilters: ReadonlyArray<UnknownRecord>,
  sources: UnknownRecord[] = []
): Map<string, number> {
  const map = new Map<string, number>();
  for (const row of rowsMatchingFilters) {
    if (!shouldSuppressCoarseParentPropositionInDefaultView(row, rowsMatchingFilters)) {
      continue;
    }
    const ck = explorerSectionClusterKeyFromRow(row, sources);
    map.set(ck, (map.get(ck) ?? 0) + 1);
  }
  return map;
}

/** Default-view footnote when parent/list-summary rows are suppressed; null if count is zero. */
export function hiddenParentListSummaryExplorerNote(hiddenRowCount: number): string | null {
  if (hiddenRowCount <= 0) {
    return null;
  }
  if (hiddenRowCount === 1) {
    return "1 parent/list-summary proposition hidden because child list items are shown.";
  }
  return `${hiddenRowCount} parent/list-summary propositions hidden because child list items are shown.`;
}

/**
 * Split each lineage-linked group into one subgroup per canonical article cluster. Without this,
 * filtering can remove every row matching the group's first-row article while sibling rows belong
 * to another article — leaving an Article N banner with nothing visible underneath.
 */
export function partitionPropositionGroupsByArticleCluster(
  groups: ReadonlyArray<{ key: string; rows: UnknownRecord[] }>
): Array<{ key: string; rows: UnknownRecord[] }> {
  const out: Array<{ key: string; rows: UnknownRecord[] }> = [];
  for (const g of groups) {
    if (!g.rows.length) {
      continue;
    }
    const byCluster = new Map<string, UnknownRecord[]>();
    const clusterOrder: string[] = [];
    for (const row of g.rows) {
      const ck = articleClusterKeyFromRow(row);
      if (!byCluster.has(ck)) {
        clusterOrder.push(ck);
        byCluster.set(ck, []);
      }
      byCluster.get(ck)!.push(row);
    }
    for (const ck of clusterOrder) {
      const chunk = byCluster.get(ck)!;
      if (!chunk.length) {
        continue;
      }
      const subKey =
        clusterOrder.length === 1 ? g.key : `${g.key}${PARTITION_SUBGROUP_APPEND_SEP}${ck}`;
      out.push({ key: subKey, rows: chunk });
    }
  }
  return out;
}

/** Bucket sorted proposition groups under explorer section keys (instrument family + provision). */
export function buildArticleSectionsGrouped(
  sortedPropositionGroups: ReadonlyArray<PropositionExplorerMergedPropositionGroup>,
  sources: UnknownRecord[] = []
): Array<{
  clusterKey: string;
  groups: PropositionExplorerMergedPropositionGroup[];
}> {
  const order: string[] = [];
  const buckets = new Map<string, PropositionExplorerMergedPropositionGroup[]>();
  for (const g of sortedPropositionGroups) {
    if (!g.rows.length) {
      continue;
    }
    const ck = explorerSectionClusterKeyFromRow(g.rows[0], sources);
    if (!buckets.has(ck)) {
      order.push(ck);
      buckets.set(ck, []);
    }
    buckets.get(ck)!.push(g);
  }
  return order
    .map((clusterKey) => ({
      clusterKey,
      groups: (buckets.get(clusterKey) ?? []).filter((gr) => gr.rows.length > 0),
    }))
    .filter((sec) => sec.groups.length > 0);
}

function scopeBucketForPropositionGroup(
  group: { rows: UnknownRecord[] },
  scopeLinkRowsByPropId: Map<string, UnknownRecord[]>,
  scopeById: Map<string, UnknownRecord>
): { clusterKey: string; label: string } {
  const slugs: string[] = [];
  for (const row of group.rows) {
    const oa = asRecord(row.original_artifact) ?? {};
    const pid = String(oa.id ?? "").trim();
    const links = pid ? (scopeLinkRowsByPropId.get(pid) ?? []) : [];
    for (const ln of links) {
      const r = asRecord(ln) ?? {};
      if (!isPrimaryScopeLinkRow(r)) {
        continue;
      }
      const sco = String((ln as { scope_id?: string }).scope_id ?? "").trim();
      const sc = scopeById.get(sco);
      const slug = String(sc?.slug ?? sco).trim();
      if (slug && !slugs.includes(slug)) {
        slugs.push(slug);
      }
    }
  }
  if (slugs.length === 0) {
    return { clusterKey: "scope:__none__", label: "Unscoped / other" };
  }
  slugs.sort((a, b) => a.localeCompare(b));
  const pickSlug = slugs[0]!;
  let friendly = pickSlug;
  for (const sc of scopeById.values()) {
    if (String((sc as { slug?: string }).slug ?? "").trim() === pickSlug) {
      friendly = String((sc as { label?: string }).label ?? pickSlug).trim() || pickSlug;
      break;
    }
  }
  return { clusterKey: `scope:${pickSlug}`, label: friendly };
}

/** Bucket groups under primary scope (first matching slug per group). */
export function buildScopeSectionsGrouped(
  sortedPropositionGroups: ReadonlyArray<PropositionExplorerMergedPropositionGroup>,
  scopeLinkRowsByPropId: Map<string, UnknownRecord[]>,
  scopeById: Map<string, UnknownRecord>
): Array<{
  clusterKey: string;
  scopeSectionLabel: string;
  groups: PropositionExplorerMergedPropositionGroup[];
}> {
  const order: string[] = [];
  const labels = new Map<string, string>();
  const buckets = new Map<string, PropositionExplorerMergedPropositionGroup[]>();
  for (const g of sortedPropositionGroups) {
    if (!g.rows.length) {
      continue;
    }
    const { clusterKey, label } = scopeBucketForPropositionGroup(
      g,
      scopeLinkRowsByPropId,
      scopeById
    );
    if (!labels.has(clusterKey)) {
      labels.set(clusterKey, label);
    }
    if (!buckets.has(clusterKey)) {
      order.push(clusterKey);
      buckets.set(clusterKey, []);
    }
    buckets.get(clusterKey)!.push(g);
  }
  return order.map((clusterKey) => ({
    clusterKey,
    scopeSectionLabel: labels.get(clusterKey) ?? clusterKey,
    groups: (buckets.get(clusterKey) ?? []).filter((gr) => gr.rows.length > 0),
  }));
}

/** Server /ops/proposition-groups summary row (no full proposition or trace payloads). */
export type PropositionGroupSummary = {
  group_id: string;
  article_key: string;
  article_heading: string;
  section_cluster_key: string;
  scope_nav_cluster_key: string;
  scope_section_label: string;
  representative_source_record_id: string;
  display_label: string;
  proposition_count: number;
  source_row_count: number;
  jurisdictions: string[];
  primary_scopes: string[];
  completeness_status: string | null;
  review_summary: Record<string, number>;
  wording_status: "same" | "diff" | "single";
  row_ids: string[];
  merge_debug?: UnknownRecord;
};

export type ExplorerNavModeToken = "source_document" | "by_scope" | "compare_versions";

function syntheticRowsForSectionHeading(summaries: PropositionGroupSummary[]): UnknownRecord[] {
  return summaries.flatMap((s) =>
    s.row_ids.map((id) => ({
      original_artifact: {
        id,
        source_record_id: s.representative_source_record_id,
      },
    }))
  );
}

/** Bucket paginated group summaries into article/scope sections (same ordering as full explorer). */
export function buildSectionsFromPropositionSummaries(
  summaries: PropositionGroupSummary[],
  explorerNavMode: ExplorerNavModeToken,
  sources: UnknownRecord[]
): Array<{
  clusterKey: string;
  sectionHeadline: string;
  sectionHeadlineCompact: string;
  sectionSubtitle: string | null;
  instrumentSectionHeading: ExplorerSectionHeading | null;
  summaries: PropositionGroupSummary[];
}> {
  if (explorerNavMode === "by_scope") {
    const order: string[] = [];
    const buckets = new Map<string, PropositionGroupSummary[]>();
    for (const s of summaries) {
      const ck = (s.scope_nav_cluster_key || "scope:__none__").trim() || "scope:__none__";
      if (!buckets.has(ck)) {
        order.push(ck);
        buckets.set(ck, []);
      }
      buckets.get(ck)!.push(s);
    }
    return order.map((clusterKey) => {
      const secSummaries = buckets.get(clusterKey)!;
      const label = secSummaries[0]?.scope_section_label ?? clusterKey;
      return {
        clusterKey,
        sectionHeadline: label,
        sectionHeadlineCompact: label,
        sectionSubtitle:
          "Grouped by primary scope links (direct relevance + high confidence).",
        instrumentSectionHeading: null,
        summaries: secSummaries,
      };
    });
  }
  const order: string[] = [];
  const buckets = new Map<string, PropositionGroupSummary[]>();
  for (const s of summaries) {
    const ck = s.section_cluster_key;
    if (!buckets.has(ck)) {
      order.push(ck);
      buckets.set(ck, []);
    }
    buckets.get(ck)!.push(s);
  }
  return order.map((clusterKey) => {
    const secSummaries = buckets.get(clusterKey)!;
    const synRows = syntheticRowsForSectionHeading(secSummaries);
    const h = formatExplorerSectionHeading(clusterKey, sources, synRows);
    // Prefer API-supplied article_heading when it carries a captured legislative title.
    const apiHeading = String(secSummaries[0]?.article_heading ?? "").trim();
    const headlineCompact =
      apiHeading.includes("—") || apiHeading.includes("–")
        ? (() => {
            const primary = h.headlineCompact.includes(" · ")
              ? h.headlineCompact.split(" · ")[0]
              : "";
            return primary ? `${primary} · ${apiHeading}` : apiHeading;
          })()
        : h.headlineCompact;
    return {
      clusterKey,
      instrumentSectionHeading: { ...h, headline: headlineCompact, headlineCompact },
      sectionHeadline: headlineCompact,
      sectionHeadlineCompact: headlineCompact,
      sectionSubtitle: h.subtitle,
      summaries: secSummaries,
    };
  });
}

export function citationForSourceRecord(
  sources: UnknownRecord[],
  sourceRecordId: string
): string {
  const sid = sourceRecordId.trim();
  for (const s of sources) {
    const id = String((s as { id?: string }).id ?? "").trim();
    if (id === sid && typeof s.citation === "string") {
      return s.citation.trim();
    }
  }
  return "";
}

/** Concise article banner title; `sourceLabel` is for tooltips only (not shown in the main article header). */
export function articleSectionHeadingParts(
  oa: UnknownRecord,
  sourceTitleById: ReadonlyMap<string, string>,
  options?: { legislativeHeading?: string | null },
): { headline: string; sourceLabel: string } {
  const sid = String(oa.source_record_id ?? "").trim();
  const sourceLabel = sid ? (sourceTitleById.get(sid) ?? sid) : "—";
  const clusterKey = articleClusterKeyFromOriginalArtifact(oa);
  const headline = formatArticleClusterDisplayHeading(clusterKey, {
    legislativeHeading: options?.legislativeHeading,
  });
  return { headline, sourceLabel };
}

/** Mirror pipeline `_format_structured_list_locator_for_label` for display only */
export function formatStructuredLocatorLabel(fragmentLocator: string): string | null {
  if (!fragmentLocator.includes(":list:")) {
    return null;
  }
  const parts = fragmentLocator.split(":list:", 2);
  if (parts.length !== 2) {
    return null;
  }
  const base = parts[0].trim();
  const path = parts[1].split("/", 1)[0]?.trim() ?? "";
  if (!path) {
    return null;
  }
  const artM = base.match(/(?:article|section)[:/_-]?(\d+[a-z]?)/i);
  const artLabel = artM ? `Art ${artM[1]}` : base;
  const bits = path.replace(/__/g, "-").split("-").filter(Boolean);
  if (bits.length < 2) {
    return null;
  }
  const [, letter, ...romans] = bits;
  const para = bits[0];
  let seg = `§${para}(${letter})`;
  for (const r of romans) {
    seg += `(${r})`;
  }
  return `${artLabel} ${seg}`;
}

/** Human line under the main label: locator + optional short title from fields */
export function propositionSubtitleParts(oa: UnknownRecord): {
  locatorLine: string | null;
  shortTitle: string | null;
} {
  const rawLoc = typeof oa.fragment_locator === "string" ? oa.fragment_locator.trim() : "";
  const listed = rawLoc ? formatStructuredLocatorLabel(rawLoc) : null;
  const locatorLine =
    listed ??
    (rawLoc && !["document:full", "full", "document", ""].includes(rawLoc.toLowerCase())
      ? rawLoc
      : null) ??
    (typeof oa.article_reference === "string" && oa.article_reference.trim()
      ? oa.article_reference.trim()
      : null);

  const shortTitle =
    typeof oa.short_name === "string" && oa.short_name.trim()
      ? oa.short_name.trim()
      : typeof oa.legal_subject === "string" || typeof oa.action === "string"
        ? [oa.legal_subject, oa.action]
            .map((x) => (typeof x === "string" ? x.trim() : ""))
            .filter(Boolean)
            .join(" — ") || null
        : null;

  return { locatorLine, shortTitle };
}

/** Stable `:list:` path identity: `article:109:list:1-a-i` → `109:1-a-i`. */
export function canonicalStructuredListPathKey(fragmentLocator: string): string | null {
  if (!fragmentLocator.includes(":list:")) {
    return null;
  }
  const parts = fragmentLocator.split(":list:", 2);
  const base = parts[0]?.trim() ?? "";
  const path = parts[1]?.split("/", 1)[0]?.trim().replace(/__/g, "-") ?? "";
  if (!path) {
    return null;
  }
  const artM = base.match(/(?:article|section)[:/_-]?(\d+[a-z]?)/i);
  const articleNum = artM?.[1]?.toLowerCase();
  if (!articleNum) {
    return null;
  }
  return `${articleNum}:${path}`;
}

/** Curated tails for equine pilot structured lists (ADR-style display only). */
const STRUCTURED_PROP_TAIL_BY_PATH: Partial<Record<string, string>> = {
  "109:1-a-i": "establishment identification information",
  "109:1-b-i": "operator information",
  "109:1-c-i": "animal identification information",
  "109:1-d-i": "equine identification information",
  "114:1-a": "unique code recorded in database",
  "114:1-b": "physical identification method",
  "114:1-c": "lifetime identification document",
};

function splitLabelLocatorAndBody(rawLabel: string): { left: string; right: string } | null {
  const t = rawLabel.trim();
  const m = t.match(/^(.*?)\s+[—–-]\s+(.+)$/s);
  if (!m?.[2]) {
    return null;
  }
  return { left: (m[1] ?? "").trim(), right: m[2].trim() };
}

function looksLikeStructuredLocatorPhrase(s: string): boolean {
  const u = s.slice(0, 80).toLowerCase();
  return /\bart\.?\s*\d+|§\s*\d/.test(u);
}

/** Heuristic: body is ancestor paragraph boilerplate rather than bullet duty */
function looksLikeParentScopeIntro(body: string): boolean {
  const b = body.slice(0, 280).toLowerCase();
  if (
    b.includes("establish and maintain a computer database") ||
    b.includes("recording of at least")
  ) {
    return true;
  }
  if (b.includes("member state") && b.includes("database") && b.length > 90) {
    return true;
  }
  if (/the following information related to kept animals of the/.test(b) && b.length > 80) {
    return true;
  }
  return false;
}

function clipDisplayPhrase(s: string, maxChars: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length <= maxChars) {
    return t;
  }
  const slice = t.slice(0, maxChars);
  const sp = slice.lastIndexOf(" ");
  return (sp > 24 ? slice.slice(0, sp) : slice).trim();
}

function toLowerDisplayTail(s: string): string {
  return clipDisplayPhrase(s, 96).toLowerCase();
}

function stripBoilerplateHead(s: string): string {
  let t = s;
  const patterns: RegExp[] = [
    /^(?:the\s+)?member\s+states?\s+shall\s+/i,
    /^each\s+member\s+state\s+shall\s+/i,
    /^the\s+commission\s+may\s+/i,
    /^member\s+states?\s+shall\s+/i,
    /^establish\s+and\s+maintain\s+a\s+computer\s+database\s+for\s+the\s+recording\s+of\s+at\s+least\s*:?\s*/i,
  ];
  for (const re of patterns) {
    t = t.replace(re, "");
  }
  const firstSentence = t.split(/[.;]/, 1)[0]?.trim() ?? t.trim();
  return firstSentence.length > 16 ? firstSentence : t.trim();
}

function condensedTailFromPropositionSnippet(oa: UnknownRecord): string | null {
  const rawLbl = typeof oa.label === "string" ? oa.label.trim() : "";
  let body: string | null = null;
  const split = rawLbl ? splitLabelLocatorAndBody(rawLbl) : null;
  if (split && split.right) {
    if (looksLikeStructuredLocatorPhrase(split.left) && !looksLikeParentScopeIntro(split.right)) {
      body = split.right;
    } else if (!looksLikeStructuredLocatorPhrase(split.left)) {
      body = rawLbl;
    }
  } else if (rawLbl) {
    body = rawLbl;
  }

  if (body && looksLikeParentScopeIntro(body)) {
    body = null;
  }

  const pt = typeof oa.proposition_text === "string" ? oa.proposition_text.trim() : "";
  if ((!body || looksLikeParentScopeIntro(body)) && pt) {
    body = pt;
  }

  if (!body) {
    return null;
  }
  return toLowerDisplayTail(stripBoilerplateHead(body));
}

function tailFromStructuredFields(oa: UnknownRecord): string | null {
  const sn = typeof oa.short_name === "string" ? oa.short_name.trim() : "";
  if (sn && sn.length <= 120 && !looksLikeParentScopeIntro(sn)) {
    return toLowerDisplayTail(sn);
  }
  const ls = typeof oa.legal_subject === "string" ? oa.legal_subject.trim() : "";
  const ac = typeof oa.action === "string" ? oa.action.trim() : "";
  const joined = [ls, ac].filter(Boolean).join(" — ");
  if (!joined || joined.length > 140) {
    return null;
  }
  return toLowerDisplayTail(joined);
}

/** Title-case Decision / Directive / Regulation + normalize `96/78/ec`-style endings (display-only). */
function capitalizeInstrumentKeywordsInCitationBody(s: string): string {
  return s.replace(
    /\b(decision|regulation|directive)(\s+)(\d+\/\d+(?:\/[a-z]{2,})?)\b/gi,
    (_, w: string, sp: string, ref: string) => {
      const cap = `${String(w).charAt(0).toUpperCase()}${String(w).slice(1).toLowerCase()}`;
      const segs = String(ref).split("/");
      if (segs.length >= 3) {
        segs[segs.length - 1] = segs[segs.length - 1]!.toUpperCase();
        return `${cap}${sp}${segs.join("/")}`;
      }
      return `${cap}${sp}${String(ref).replace(/\/ec\b/i, "/EC")}`;
    }
  );
}

function humanizeXmlishLabelRemainder(rest: string): string {
  let t = rest.replace(/^xml:\S*\s*/gi, "").replace(/\s+/g, " ").trim();
  t = t.replace(/\bthis\s+apply\b/gi, "this applies").replace(/^this applies\b/, "This applies");
  t = capitalizeInstrumentKeywordsInCitationBody(t);
  if (/^[a-z]/.test(t)) {
    t = `${t.charAt(0).toUpperCase()}${t.slice(1)}`;
  }
  return clipDisplayPhrase(t, 132);
}

/** Parses `xml:article-7-8 — …`-style heuristic labels emitted by extraction (display-only). */
function rewriteXmlColonArticlePrefixedLabel(rawLabel: string): string | null {
  const t = rawLabel.trim();
  if (!/^xml:/i.test(t)) {
    return null;
  }
  const artPara = t.match(/^xml:\s*article-(\d+)-(\d+)\b\s*(?:[—–-]\s*)?(.*)$/is);
  if (artPara?.[1] && artPara[2]) {
    const locator = `Article ${artPara[1]}(${artPara[2]})`;
    const rest = (artPara[3] ?? "").trim();
    if (!rest) {
      return locator;
    }
    return `${locator} — ${humanizeXmlishLabelRemainder(rest)}`;
  }
  const artOnly = t.match(/^xml:\s*article-(\d+)\b\s*(?:[—–-]\s*)?(.*)$/is);
  if (artOnly?.[1]) {
    const locator = `Article ${artOnly[1]}`;
    const rest = (artOnly[2] ?? "").trim();
    if (!rest) {
      return locator;
    }
    return `${locator} — ${humanizeXmlishLabelRemainder(rest)}`;
  }
  return null;
}

/**
 * One-line proposition card title — locator-first when possible, concise tail; does not mutate backend fields.
 */
export function propositionDisplayLabel(oa: UnknownRecord): string {
  const frag = typeof oa.fragment_locator === "string" ? oa.fragment_locator.trim() : "";
  const listed = frag ? formatStructuredLocatorLabel(frag) : null;
  const pathKey = frag ? canonicalStructuredListPathKey(frag) : null;
  const curated = pathKey ? (STRUCTURED_PROP_TAIL_BY_PATH[pathKey] ?? null) : null;
  const rawLabelFieldTrim = typeof oa.label === "string" ? oa.label.trim() : "";
  if (/^definition\s+[—–-]\s+.+/i.test(rawLabelFieldTrim)) {
    return rawLabelFieldTrim
      .replace(/^definition/i, "Definition")
      .replace(/\s+[–-]\s+/, " — ");
  }

  const xmlRewrite =
    !listed && rawLabelFieldTrim && /^xml:/i.test(rawLabelFieldTrim)
      ? rewriteXmlColonArticlePrefixedLabel(rawLabelFieldTrim)
      : null;

  const tail =
    curated ?? tailFromStructuredFields(oa) ?? condensedTailFromPropositionSnippet(oa);

  if (listed) {
    if (!tail) {
      return listed;
    }
    return `${listed} — ${tail}`;
  }

  if (xmlRewrite) {
    const structuredPrefer = tailFromStructuredFields(oa);
    if (structuredPrefer) {
      const head = xmlRewrite.split(" — ")[0]?.trim() ?? xmlRewrite;
      return `${head} — ${structuredPrefer}`;
    }
    return xmlRewrite;
  }

  const sub = propositionSubtitleParts(oa);
  const locAbbrev =
    sub.locatorLine ??
    (typeof oa.article_reference === "string" && oa.article_reference.trim()
      ? clipDisplayPhrase(oa.article_reference.trim(), 56)
      : null);

  if (locAbbrev && tail) {
    const pref = Math.min(16, Math.max(locAbbrev.length - 4, 6));
    if (!tail.toLowerCase().startsWith(locAbbrev.toLowerCase().slice(0, pref))) {
      return `${locAbbrev} — ${tail}`;
    }
  }

  if (tail) {
    return tail;
  }

  if (locAbbrev) {
    return locAbbrev;
  }

  const raw = typeof oa.label === "string" ? oa.label.trim() : "";
  if (!raw) {
    return "—";
  }

  const squashed = toLowerDisplayTail(stripBoilerplateHead(raw));
  if (squashed.length >= 14) {
    return squashed;
  }
  return clipDisplayPhrase(raw, 92);
}

export function normalizePropositionText(s: string): string {
  return s.trim().replace(/\s+/g, " ");
}

/** Fingerprint for grouped rows: proposition text plus stored label (EU/UK label microcopy). */
export function wordingFingerprintForPropositionGroupCompare(oa: UnknownRecord): string {
  const t = typeof oa.proposition_text === "string" ? oa.proposition_text : "";
  const lab = typeof oa.label === "string" ? oa.label : "";
  return `${normalizePropositionText(t)}\u001f${normalizePropositionText(lab)}`;
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Best-effort [start, end) span in full fragment text for scroll/highlight from a fragment_locator.
 * Falls back to a short head window when locator is coarse or unmatched.
 */
export function findLocatorHighlightSpan(
  fullText: string,
  locator: string | undefined
): [number, number] {
  const text = fullText;
  if (!text) {
    return [0, 0];
  }
  const softCap = 4500;

  if (locator && locator.includes(":list:")) {
    const pathPart = locator.split(":list:", 2)[1]?.split("/", 1)[0] ?? "";
    const bits = pathPart.replace(/__/g, "-").split("-").filter(Boolean);
    if (bits.length >= 3) {
      const letter = bits[1] ?? "";
      const roman = bits[2] ?? "";
      if (letter && roman) {
        const patterns = [
          new RegExp(
            `\\n\\(${escapeRegExp(letter)}\\)\\s*\\n\\s*\\(${escapeRegExp(roman)}\\)`,
            "i"
          ),
          new RegExp(
            `\\(${escapeRegExp(letter)}\\)[^\\(]{0,800}\\(${escapeRegExp(roman)}\\)`,
            "is"
          ),
          new RegExp(`\\(${escapeRegExp(roman)}\\)`, "i"),
        ];
        for (const re of patterns) {
          const m = text.match(re);
          if (m && m.index !== undefined) {
            const start = Math.max(0, m.index - 120);
            const end = Math.min(text.length, m.index + m[0].length + 400);
            return [start, end];
          }
        }
      }
    }
  }

  const head = Math.min(softCap, text.length);
  return [0, head];
}

/** Myers diff on tokens (whitespace-preserving chunks) — for two-way compare */
export function diffTokens(left: string, right: string): { left: ReactNode[]; right: ReactNode[] } {
  const tokenize = (s: string): string[] => {
    const out: string[] = [];
    const re = /\s+|\S+/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(s))) {
      out.push(m[0]);
    }
    return out;
  };

  const a = tokenize(left);
  const b = tokenize(right);
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? 1 + dp[i + 1][j + 1] : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  let i = 0;
  let j = 0;
  const leftNodes: ReactNode[] = [];
  const rightNodes: ReactNode[] = [];
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      leftNodes.push(<span key={`l-${i}-${j}-eq`}>{a[i]}</span>);
      rightNodes.push(<span key={`r-${i}-${j}-eq`}>{b[j]}</span>);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      leftNodes.push(
        <mark key={`l-del-${i}`} className="rounded-sm bg-red-900/35 text-inherit">
          {a[i]}
        </mark>
      );
      i++;
    } else {
      rightNodes.push(
        <mark key={`r-ins-${j}`} className="rounded-sm bg-emerald-900/35 text-inherit">
          {b[j]}
        </mark>
      );
      j++;
    }
  }
  while (i < n) {
    leftNodes.push(
      <mark key={`l-del-${i}`} className="rounded-sm bg-red-900/35 text-inherit">
        {a[i]}
      </mark>
    );
    i++;
  }
  while (j < m) {
    rightNodes.push(
      <mark key={`r-ins-${j}`} className="rounded-sm bg-emerald-900/35 text-inherit">
        {b[j]}
      </mark>
    );
    j++;
  }

  return { left: leftNodes, right: rightNodes };
}

export function jurisdictionForSource(sources: UnknownRecord[], sourceId: string): string {
  for (const s of sources) {
    const id = String((s as { id?: string }).id ?? "").trim();
    if (id === sourceId) {
      const j = String((s as { jurisdiction?: string }).jurisdiction ?? "").trim();
      return j || "—";
    }
  }
  return "—";
}

export function jurisdictionBadgeLabel(jurisdiction: string, sourceId: string): string {
  const j = jurisdiction.trim().toUpperCase();
  if (j === "EU" || j === "UK") {
    return j;
  }
  if (!j || j === "—") {
    return sourceId.slice(0, 8) || "?";
  }
  return jurisdiction.slice(0, 12);
}

export type JurisdictionChipDisplay = {
  /** Regional-indicator flag for EU/UK; empty for unknown / fallback labels. */
  icon: string;
  label: string;
  title: string;
};

/**
 * Display parts for jurisdiction chips. EU/UK use flag emoji (not image assets) and
 * jurisdiction-specific tooltips; unknown keeps the same text fallback as {@link jurisdictionBadgeLabel}.
 */
export function jurisdictionDisplay(
  jurisdiction: string,
  sourceId = "",
): JurisdictionChipDisplay {
  const j = jurisdiction.trim().toUpperCase();
  if (j === "EU") {
    return { icon: "🇪🇺", label: "EU", title: "EU source version" };
  }
  if (j === "UK") {
    return { icon: "🇬🇧", label: "UK", title: "UK source version" };
  }
  return {
    icon: "",
    label: jurisdictionBadgeLabel(jurisdiction, sourceId),
    title: SOURCE_JURISDICTION_CHIP_TOOLTIP,
  };
}

const PRIMARY_JURISDICTION_CHIP_CLASS =
  "rounded border border-priguidance-discovery/45 bg-priguidance-discovery/[0.12] px-2 py-0.5 font-mono text-[11px] font-semibold text-primary";

/** Jurisdiction chip for proposition explorer (group source rows, diff headers, flat cards). */
export function PropositionJurisdictionChip({
  jurisdiction,
  sourceId,
  className = PRIMARY_JURISDICTION_CHIP_CLASS,
}: {
  jurisdiction: string;
  sourceId: string;
  /** Defaults to primary-styled chip; pass e.g. plain text for diff column headers. */
  className?: string;
}): JSX.Element {
  const d = jurisdictionDisplay(jurisdiction, sourceId);
  if (!d.icon) {
    return (
      <span title={d.title} className={className}>
        {d.label}
      </span>
    );
  }
  return (
    <span title={d.title} aria-label={d.title} className={className}>
      <span aria-hidden="true">
        {d.icon}
        {"\u00A0"}
        {d.label}
      </span>
    </span>
  );
}

type FragmentSnippetProps = {
  fullText: string;
  highlightLocator: string;
  busy: boolean;
  /** Keys injected for display readability (e.g. instrument label, parent context excerpt). */
  contextInjections?: UnknownRecord | null;
};

/** Scrollable excerpt centred on locator-derived span; full text collapsed by default */
export function FragmentSnippetView({
  fullText,
  highlightLocator,
  busy,
  contextInjections,
}: FragmentSnippetProps): JSX.Element {
  const markRef = useRef<HTMLSpanElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const [spanStart, spanEnd] = findLocatorHighlightSpan(fullText, highlightLocator);
  const padBefore = 320;
  const padAfter = 900;
  const winStart = Math.max(0, spanStart - padBefore);
  const winEnd = Math.min(fullText.length, spanEnd + padAfter);
  const prefix = winStart > 0 ? "…" : "";
  const suffix = winEnd < fullText.length ? "…" : "";
  const before = fullText.slice(winStart, spanStart);
  const focus = fullText.slice(spanStart, spanEnd);
  const after = fullText.slice(spanEnd, winEnd);

  useLayoutEffect(() => {
    if (busy || !markRef.current || !scrollRef.current) {
      return;
    }
    markRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [busy, spanStart, spanEnd, fullText]);

  if (busy) {
    return <p className="p-3 text-sm text-muted-foreground">Loading…</p>;
  }

  const injEntries =
    contextInjections && typeof contextInjections === "object"
      ? Object.entries(contextInjections).filter(
          ([k, v]) => k && v !== null && v !== undefined && String(v).trim() !== ""
        )
      : [];

  return (
    <div className="flex max-h-[min(86vh,36rem)] flex-col">
      {injEntries.length > 0 ? (
        <div className="border-b border-border/50 px-3 py-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Context used for display
          </p>
          <ul className="mt-1.5 space-y-1">
            {injEntries.map(([key, val]) => (
              <li key={key} className="text-[11px] text-foreground/90">
                <span className="font-mono text-muted-foreground">{key}</span>
                <span className="mx-1.5 text-muted-foreground">:</span>
                <span className="whitespace-pre-wrap">{String(val)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="border-b border-border/60 px-3 py-2 text-[11px] text-muted-foreground">
        Excerpt around locator{highlightLocator ? ` (${highlightLocator})` : ""}. Open full fragment
        only if needed.
      </p>
      <div
        ref={scrollRef}
        className="max-h-52 overflow-auto border-b border-border/40 bg-muted/20 px-3 py-2"
      >
        <pre className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-foreground/95">
          {prefix}
          {before}
          <span ref={markRef} className="rounded-sm bg-amber-500/25 ring-2 ring-amber-500/50">
            {focus}
          </span>
          {after}
          {suffix}
        </pre>
      </div>
      <details className="group overflow-hidden border-t border-border/40">
        <summary className="cursor-pointer select-none px-3 py-2 text-[11px] font-medium text-muted-foreground hover:bg-muted/30">
          Full source fragment ({fullText.length.toLocaleString()} chars)
        </summary>
        <pre className="max-h-[min(40vh,16rem)] overflow-auto whitespace-pre-wrap p-3 font-mono text-[11px] leading-relaxed opacity-90">
          {fullText}
        </pre>
      </details>
    </div>
  );
}
