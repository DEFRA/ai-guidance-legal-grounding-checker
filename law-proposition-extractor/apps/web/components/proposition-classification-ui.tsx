import type { JSX } from "react";

import type {
  PropositionGroupSummary,
  UnknownRecord,
} from "@/components/proposition-explorer-helpers";
import { territorialApplicationFromProposition } from "@/components/proposition-explorer-helpers";

export type PropositionTierToken =
  | "instrument_metadata"
  | "scope_rule"
  | "substantive_rule"
  | "procedural_rule"
  | "definitional_rule"
  | "relationship_reference"
  | "unknown"
  | "";

export type LegalEffectTypeToken =
  | "citation"
  | "commencement"
  | "extent"
  | "application_scope"
  | "definition"
  | "obligation"
  | "prohibition"
  | "permission"
  | "power"
  | "recordkeeping"
  | "notification"
  | "certification"
  | "inspection"
  | "enforcement"
  | "appeal"
  | "derogation"
  | "cross_reference"
  | "unknown"
  | "";

export type PropositionClassificationView = {
  tier: PropositionTierToken;
  legalEffectType: LegalEffectTypeToken;
  label: string;
  territorialApplication: string[];
  extent: string[];
  isComplianceRelevant: boolean | null;
  isComparisonAnchor: boolean | null;
  displayClass: string | null;
};

export type ExplorerClassificationFilters = {
  filterPropositionTier: string;
  filterLegalEffectType: string;
  filterTerritorialApplication: string;
  filterExtent: string;
  showInstrumentMetadata: boolean;
  complianceRelevantOnly: boolean;
  comparisonAnchorsOnly: boolean;
  collapseScopeRules: boolean;
};

export const DEFAULT_EXPLORER_CLASSIFICATION_FILTERS: ExplorerClassificationFilters = {
  filterPropositionTier: "",
  filterLegalEffectType: "",
  filterTerritorialApplication: "",
  filterExtent: "",
  showInstrumentMetadata: false,
  complianceRelevantOnly: false,
  comparisonAnchorsOnly: false,
  collapseScopeRules: true,
};

export const PROPOSITION_TIER_FILTER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "(any tier)" },
  { value: "substantive_rule", label: "Substantive rule" },
  { value: "procedural_rule", label: "Procedural rule" },
  { value: "definitional_rule", label: "Definitional rule" },
  { value: "scope_rule", label: "Scope rule" },
  { value: "instrument_metadata", label: "Instrument metadata" },
  { value: "relationship_reference", label: "Relationship reference" },
  { value: "unknown", label: "Unknown" },
];

export const LEGAL_EFFECT_FILTER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "(any type)" },
  { value: "obligation", label: "Obligation" },
  { value: "prohibition", label: "Prohibition" },
  { value: "application_scope", label: "Application scope" },
  { value: "definition", label: "Definition" },
  { value: "extent", label: "Extent" },
  { value: "citation", label: "Citation" },
  { value: "commencement", label: "Commencement" },
  { value: "recordkeeping", label: "Recordkeeping" },
  { value: "notification", label: "Notification" },
  { value: "enforcement", label: "Enforcement" },
  { value: "cross_reference", label: "Cross-reference" },
  { value: "unknown", label: "Unknown" },
];

const TIER_LABELS: Record<string, string> = {
  instrument_metadata: "Instrument metadata",
  scope_rule: "Scope rule",
  substantive_rule: "Substantive rule",
  procedural_rule: "Procedural rule",
  definitional_rule: "Definitional rule",
  relationship_reference: "Relationship reference",
  unknown: "Unknown",
};

const EFFECT_LABELS: Record<string, string> = {
  citation: "Citation",
  commencement: "Commencement",
  extent: "Extent",
  application_scope: "Application scope",
  definition: "Definition",
  obligation: "Obligation",
  prohibition: "Prohibition",
  permission: "Permission",
  power: "Power",
  recordkeeping: "Recordkeeping",
  notification: "Notification",
  certification: "Certification",
  inspection: "Inspection",
  enforcement: "Enforcement",
  appeal: "Appeal",
  derogation: "Derogation",
  cross_reference: "Cross-reference",
  unknown: "Unknown",
};

function normToken(raw: unknown): string {
  return String(raw ?? "")
    .trim()
    .toLowerCase()
    .replace(/-/g, "_");
}

function readBool(raw: unknown): boolean | null {
  if (raw === true || raw === false) {
    return raw;
  }
  if (raw === "true") {
    return true;
  }
  if (raw === "false") {
    return false;
  }
  return null;
}

/** When tier/effect are absent (pre-normalisation exports), infer boilerplate from text for filters only. */
export function legacyLegalEffectGuess(oa: UnknownRecord): LegalEffectTypeToken {
  const stored = normToken(oa.legal_effect_type);
  if (stored) {
    return stored as LegalEffectTypeToken;
  }
  const text = `${String(oa.proposition_text ?? "")} ${String(oa.action ?? "")}`.toLowerCase();
  if (/\bmay be cited as\b/.test(text)) {
    return "citation";
  }
  if (/\bcome into force\b/.test(text)) {
    return "commencement";
  }
  if (/\bextends?\s+to\b/.test(text)) {
    return "extent";
  }
  if (/\bapply in relation to\b/.test(text) || /\bapply to\b/.test(text) || /\bapplies to\b/.test(text)) {
    return "application_scope";
  }
  return "";
}

export function classificationFromProposition(oa: UnknownRecord): PropositionClassificationView {
  const tier = normToken(oa.proposition_tier) as PropositionTierToken;
  const legalEffectType = normToken(oa.legal_effect_type) as LegalEffectTypeToken;
  const label = typeof oa.label === "string" ? oa.label.trim() : "";
  const dbg = oa.extraction_debug_meta;
  const displayClass =
    dbg && typeof dbg === "object" && typeof (dbg as { display_label?: string }).display_label === "string"
      ? String((dbg as { display_label: string }).display_label).trim()
      : null;
  const extentRaw = oa.extent;
  const extent = Array.isArray(extentRaw)
    ? extentRaw.map((x) => String(x).trim()).filter(Boolean)
    : [];
  return {
    tier,
    legalEffectType,
    label,
    territorialApplication: territorialApplicationFromProposition(oa),
    extent,
    isComplianceRelevant: readBool(oa.is_compliance_relevant),
    isComparisonAnchor: readBool(oa.is_comparison_anchor),
    displayClass,
  };
}

export function tierDisplayLabel(tier: PropositionTierToken): string {
  return TIER_LABELS[tier] ?? (tier ? tier.replace(/_/g, " ") : "—");
}

export function legalEffectDisplayLabel(effect: LegalEffectTypeToken): string {
  return EFFECT_LABELS[effect] ?? (effect ? effect.replace(/_/g, " ") : "—");
}

export function isInstrumentMetadataTier(tier: PropositionTierToken): boolean {
  return tier === "instrument_metadata";
}

export function isScopeRuleTier(tier: PropositionTierToken): boolean {
  return tier === "scope_rule";
}

export function passesDefaultTierVisibility(
  view: PropositionClassificationView,
  filters: ExplorerClassificationFilters
): boolean {
  if (filters.filterPropositionTier.trim()) {
    return view.tier === filters.filterPropositionTier.trim();
  }
  if (filters.showInstrumentMetadata) {
    return true;
  }
  if (isInstrumentMetadataTier(view.tier)) {
    return false;
  }
  return (
    view.tier === "substantive_rule" ||
    view.tier === "procedural_rule" ||
    view.tier === "definitional_rule" ||
    view.tier === "scope_rule" ||
    view.tier === "relationship_reference" ||
    view.tier === "unknown" ||
    view.tier === ""
  );
}

export function matchesExplorerClassificationFilters(
  oa: UnknownRecord,
  filters: ExplorerClassificationFilters
): boolean {
  const view = classificationFromProposition(oa);

  if (!passesDefaultTierVisibility(view, filters)) {
    return false;
  }

  const effectFilter = filters.filterLegalEffectType.trim();
  if (effectFilter && view.legalEffectType !== effectFilter) {
    return false;
  }

  const effectForHide = view.legalEffectType || legacyLegalEffectGuess(oa);
  if (!filters.showInstrumentMetadata && !effectFilter) {
    if (
      effectForHide === "citation" ||
      effectForHide === "commencement" ||
      effectForHide === "extent" ||
      isInstrumentMetadataTier(view.tier)
    ) {
      return false;
    }
  }

  if (filters.complianceRelevantOnly && view.isComplianceRelevant !== true) {
    return false;
  }

  if (filters.comparisonAnchorsOnly && view.isComparisonAnchor !== true) {
    return false;
  }

  const terrFilter = filters.filterTerritorialApplication.trim().toLowerCase();
  if (terrFilter) {
    const hay = view.territorialApplication.join(" ").toLowerCase();
    if (!hay.includes(terrFilter)) {
      return false;
    }
  }

  const extentFilter = filters.filterExtent.trim().toLowerCase();
  if (extentFilter) {
    const hay = view.extent.join(" ").toLowerCase();
    if (!hay.includes(extentFilter)) {
      return false;
    }
  }

  return true;
}

export function propositionInformativeLabel(oa: UnknownRecord): string {
  const view = classificationFromProposition(oa);
  if (view.label) {
    return view.label;
  }
  const text = typeof oa.proposition_text === "string" ? oa.proposition_text.trim() : "";
  return text.length > 120 ? `${text.slice(0, 117)}…` : text || "—";
}

export function isScopeRuleProposition(oa: UnknownRecord): boolean {
  return isScopeRuleTier(classificationFromProposition(oa).tier);
}

export function partitionSummariesByScopeSecondary(
  summaries: PropositionGroupSummary[],
  propById: ReadonlyMap<string, UnknownRecord>,
  collapseScopeRules: boolean
): { primary: PropositionGroupSummary[]; scopeSecondary: PropositionGroupSummary[] } {
  if (!collapseScopeRules) {
    return { primary: summaries, scopeSecondary: [] };
  }
  const primary: PropositionGroupSummary[] = [];
  const scopeSecondary: PropositionGroupSummary[] = [];
  for (const sum of summaries) {
    let isScope = false;
    for (const id of sum.row_ids) {
      const oa = propById.get(id);
      if (oa && isScopeRuleProposition(oa)) {
        isScope = true;
        break;
      }
    }
    if (isScope) {
      scopeSecondary.push(sum);
    } else {
      primary.push(sum);
    }
  }
  return { primary, scopeSecondary };
}

export function partitionGroupsByScopeSecondary<T extends { rows: UnknownRecord[] }>(
  groups: T[],
  collapseScopeRules: boolean
): { primary: T[]; scopeSecondary: T[] } {
  if (!collapseScopeRules) {
    return { primary: groups, scopeSecondary: [] };
  }
  const primary: T[] = [];
  const scopeSecondary: T[] = [];
  for (const g of groups) {
    const oa = g.rows[0] ? (g.rows[0].original_artifact as UnknownRecord) : null;
    if (oa && isScopeRuleProposition(oa)) {
      scopeSecondary.push(g);
    } else {
      primary.push(g);
    }
  }
  return { primary, scopeSecondary };
}

export function classificationFiltersActive(filters: ExplorerClassificationFilters): boolean {
  return Boolean(
    filters.filterPropositionTier.trim() ||
      filters.filterLegalEffectType.trim() ||
      filters.filterTerritorialApplication.trim() ||
      filters.filterExtent.trim() ||
      filters.showInstrumentMetadata ||
      filters.complianceRelevantOnly ||
      filters.comparisonAnchorsOnly ||
      !filters.collapseScopeRules
  );
}

const CHIP =
  "rounded border px-1.5 py-0.5 font-mono text-[10px] leading-tight";

export function PropositionClassificationMeta({
  oa,
  compact = false,
  showExtractionDebug = false,
}: {
  oa: UnknownRecord;
  compact?: boolean;
  /** When false, hides pipeline extraction class hints (raw/debug views only). */
  showExtractionDebug?: boolean;
}): JSX.Element {
  const view = classificationFromProposition(oa);
  const yesNo = (v: boolean | null) => (v === true ? "Yes" : v === false ? "No" : "—");

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-1">
        <span className={`${CHIP} border-violet-700/40 bg-violet-950/25 text-violet-100`} title="Proposition tier">
          {tierDisplayLabel(view.tier)}
        </span>
        <span className={`${CHIP} border-sky-700/40 bg-sky-950/25 text-sky-100`} title="Legal effect type">
          {legalEffectDisplayLabel(view.legalEffectType)}
        </span>
        {view.territorialApplication.length > 0 ? (
          <span className={`${CHIP} border-amber-700/40 bg-amber-950/20 text-amber-100`}>
            {view.territorialApplication.join(", ")}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <dl className="grid gap-1.5 text-[11px] sm:grid-cols-2">
      <div>
        <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Tier</dt>
        <dd className="font-medium text-foreground">{tierDisplayLabel(view.tier)}</dd>
      </div>
      <div>
        <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Type</dt>
        <dd className="font-medium text-foreground">{legalEffectDisplayLabel(view.legalEffectType)}</dd>
      </div>
      <div className="sm:col-span-2">
        <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Label</dt>
        <dd className="font-medium leading-snug text-foreground">{propositionInformativeLabel(oa)}</dd>
      </div>
      <div>
        <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Territory</dt>
        <dd className="text-foreground">{view.territorialApplication.join(", ") || "—"}</dd>
      </div>
      <div>
        <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Extent</dt>
        <dd className="text-foreground">{view.extent.join(", ") || "—"}</dd>
      </div>
      <div>
        <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Compliance relevant
        </dt>
        <dd className="text-foreground">{yesNo(view.isComplianceRelevant)}</dd>
      </div>
      <div>
        <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Comparison anchor
        </dt>
        <dd className="text-foreground">{yesNo(view.isComparisonAnchor)}</dd>
      </div>
      {showExtractionDebug && view.displayClass && view.displayClass !== view.label ? (
        <div className="sm:col-span-2">
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Extraction class
          </dt>
          <dd className="text-muted-foreground">{view.displayClass}</dd>
        </div>
      ) : null}
    </dl>
  );
}
