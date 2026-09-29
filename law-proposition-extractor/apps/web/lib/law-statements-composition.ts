import {
  isResolvedTypedContext,
  propositionRefsForStatement,
  type LawStatementPropRef,
  type LawStatementPropRole,
  type LawStatementRow,
  type PropositionRow,
  type SourceRow,
} from "@/lib/law-statements-index";

export const EXPORT_FIELD_UNAVAILABLE = "not available from current export";

export type SupportStatus = "supported" | "partial" | "unresolved" | "unsupported";

export type StatementFragmentView = {
  id: string;
  text: string;
  derived: boolean;
};

export type StatementRecipeRow = {
  rowId: string;
  statement_fragment: string;
  supporting_proposition_ids: string[];
  proposition_text: string;
  source_locator: string;
  source_excerpt: string;
  support_status: SupportStatus;
  /** legislation.gov.uk XML/HTML URL from the linked source record, when known. */
  source_url?: string;
};

export type CoverageCheckKey =
  | "source_text_used"
  | "statement_text_supported"
  | "conditions_preserved"
  | "exceptions_preserved"
  | "cross_references_resolved"
  | "scope_preserved";

export type CoverageCheckEntry = {
  key: CoverageCheckKey;
  label: string;
  value: string;
  fromExport: boolean;
};

export type StructuralHeadingRow = {
  kind?: string | null;
  text?: string | null;
  number_label?: string | null;
  owner_fragment_id?: string | null;
  owner_locator?: string | null;
  source_element?: string | null;
  change_ids?: string[] | null;
  commentary_refs?: string[] | null;
};

export type SourceFragmentRow = {
  id?: string;
  fragment_id?: string;
  source_record_id?: string;
  source_snapshot_id?: string;
  fragment_text?: string;
  locator?: string;
  fragment_hash?: string;
  text_hash?: string;
  /** Structural parent within the same source snapshot, when exported. */
  parent_fragment_id?: string | null;
  /** Source-provided number label (e.g. Article 49a / TITLE IV). */
  number_label?: string | null;
  /** Source-provided legislative heading (not operative proposition text). */
  structural_heading?: StructuralHeadingRow | null;
};

export type CompositionBuildContext = {
  propositionById: Map<string, PropositionRow>;
  sourceById: Map<string, SourceRow>;
  fragmentById: Map<string, SourceFragmentRow>;
  sourceCompletenessByPropositionId?: Map<string, string>;
};

function normalizeForMatch(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .trim();
}

function findFragmentSpan(statementText: string, propositionText: string): string | null {
  const normalizedStatement = normalizeForMatch(statementText);
  const normalizedProposition = normalizeForMatch(propositionText);
  if (!normalizedProposition || normalizedProposition.length < 12) {
    return null;
  }
  const index = normalizedStatement.indexOf(normalizedProposition);
  if (index < 0) {
    return null;
  }
  return statementText.slice(index, index + propositionText.length);
}

function splitStatementIntoSentences(statementText: string): string[] {
  const trimmed = statementText.trim();
  if (!trimmed) {
    return [];
  }
  const parts = trimmed.split(/(?<=[.!?])\s+/).map((part) => part.trim()).filter(Boolean);
  return parts.length > 0 ? parts : [trimmed];
}

export function buildStatementFragments(
  statement: LawStatementRow,
  propositionById: Map<string, PropositionRow>,
): StatementFragmentView[] {
  const exportFragments = (statement as LawStatementRow & {
    statement_fragments?: Array<{ id?: string; text?: string; fragment_text?: string }>;
  }).statement_fragments;
  if (Array.isArray(exportFragments) && exportFragments.length > 0) {
    return exportFragments.map((fragment, index) => ({
      id: String(fragment.id ?? `export-fragment-${index}`),
      text: String(fragment.text ?? fragment.fragment_text ?? "").trim(),
      derived: false,
    }));
  }

  const sourceIds = statement.source_proposition_ids ?? [];
  if (sourceIds.length <= 1) {
    return [
      {
        id: "whole-statement",
        text: statement.statement_text,
        derived: true,
      },
    ];
  }

  const matchedSpans: string[] = [];
  for (const propositionId of sourceIds) {
    const proposition = propositionById.get(propositionId);
    const propositionText = proposition?.proposition_text?.trim() ?? "";
    if (!propositionText) {
      continue;
    }
    const span = findFragmentSpan(statement.statement_text, propositionText);
    if (span && !matchedSpans.includes(span)) {
      matchedSpans.push(span);
    }
  }

  if (matchedSpans.length > 1) {
    return matchedSpans.map((text, index) => ({
      id: `matched-fragment-${index}`,
      text,
      derived: true,
    }));
  }

  const sentences = splitStatementIntoSentences(statement.statement_text);
  if (sentences.length > 1) {
    return sentences.map((text, index) => ({
      id: `sentence-fragment-${index}`,
      text,
      derived: true,
    }));
  }

  return [
    {
      id: "whole-statement",
      text: statement.statement_text,
      derived: true,
    },
  ];
}

export function inferSupportStatus(
  ref: LawStatementPropRef,
  completenessStatus?: string,
): SupportStatus {
  const exportStatus = readExportSupportStatus(ref);
  if (exportStatus) {
    return exportStatus;
  }

  if (ref.role === "source") {
    if (completenessStatus === "fragmentary" || completenessStatus === "context_dependent") {
      return "partial";
    }
    return "supported";
  }
  if (ref.role === "supporting") {
    return "supported";
  }
  if (ref.role === "required_context" || ref.role === "exception" || ref.role === "displaced_rule" || ref.role === "trigger") {
    if (ref.contextResolutionStatus === "unresolved") {
      return "unresolved";
    }
    if (ref.contextResolutionStatus === "ambiguous") {
      return "partial";
    }
    return "supported";
  }
  if (ref.role === "connector" || ref.role === "via") {
    return "partial";
  }
  return "unsupported";
}

function readExportSupportStatus(ref: LawStatementPropRef): SupportStatus | null {
  const raw = (ref as LawStatementPropRef & { support_status?: string }).support_status;
  if (
    raw === "supported" ||
    raw === "partial" ||
    raw === "unresolved" ||
    raw === "unsupported"
  ) {
    return raw;
  }
  return null;
}

function resolveSourceLocator(
  proposition: PropositionRow | undefined,
  source: SourceRow | undefined,
  fragmentById?: Map<string, SourceFragmentRow>,
): string {
  // Prefer the canonical fragment locator (article:N:…) over free-text prop locators.
  const fragmentId = proposition?.source_fragment_id?.trim();
  if (fragmentId && fragmentById) {
    const fragmentLocator = fragmentById.get(fragmentId)?.locator?.trim();
    if (fragmentLocator) {
      return fragmentLocator;
    }
  }
  const locator = proposition?.fragment_locator?.trim();
  if (locator) {
    return locator;
  }
  const citation = source?.citation?.trim();
  if (citation) {
    return citation;
  }
  const title = source?.title?.trim();
  if (title) {
    return title;
  }
  return EXPORT_FIELD_UNAVAILABLE;
}

function resolveSourceExcerpt(
  proposition: PropositionRow | undefined,
  fragmentById: Map<string, SourceFragmentRow>,
): string {
  const fragmentId = proposition?.source_fragment_id?.trim();
  if (fragmentId) {
    const fragment = fragmentById.get(fragmentId);
    const fragmentText = fragment?.fragment_text?.trim();
    if (fragmentText) {
      return fragmentText;
    }
  }

  const evidenceQuote = proposition?.extraction_debug_meta?.evidence_quote?.trim();
  if (evidenceQuote) {
    return evidenceQuote;
  }

  return EXPORT_FIELD_UNAVAILABLE;
}

function resolvePropositionText(proposition: PropositionRow | undefined): string {
  const text = proposition?.proposition_text?.trim();
  if (text) {
    return text;
  }
  const label = proposition?.label?.trim();
  if (label) {
    return label;
  }
  return EXPORT_FIELD_UNAVAILABLE;
}

function pickStatementFragmentForRef(
  statement: LawStatementRow,
  ref: LawStatementPropRef,
  proposition: PropositionRow | undefined,
  fragments: StatementFragmentView[],
): string {
  const exportFragment = (ref as LawStatementPropRef & { statement_fragment?: string })
    .statement_fragment;
  if (exportFragment?.trim()) {
    return exportFragment.trim();
  }

  const propositionText = proposition?.proposition_text?.trim() ?? "";
  if (propositionText) {
    const span = findFragmentSpan(statement.statement_text, propositionText);
    if (span) {
      return span;
    }
    const fragmentHit = fragments.find((fragment) =>
      normalizeForMatch(fragment.text).includes(normalizeForMatch(propositionText)),
    );
    if (fragmentHit) {
      return fragmentHit.text;
    }
  }

  if (fragments.length === 1) {
    return fragments[0]!.text;
  }

  return EXPORT_FIELD_UNAVAILABLE;
}

export function buildStatementRecipe(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): StatementRecipeRow[] {
  const exportRecipe = (
    statement as LawStatementRow & {
      statement_recipe?: Array<{
        statement_fragment?: string;
        supporting_proposition_ids?: string[];
        proposition_text?: string;
        source_locator?: string;
        source_excerpt?: string;
        support_status?: SupportStatus;
      }>;
    }
  ).statement_recipe;
  if (Array.isArray(exportRecipe) && exportRecipe.length > 0) {
    return exportRecipe.map((row, index) => {
      const supportingIds = Array.isArray(row.supporting_proposition_ids)
        ? row.supporting_proposition_ids.map((id) => String(id))
        : [];
      const firstPropId = supportingIds[0];
      const proposition = firstPropId
        ? context.propositionById.get(firstPropId)
        : undefined;
      const source = proposition?.source_record_id
        ? context.sourceById.get(proposition.source_record_id)
        : undefined;
      return {
        rowId: `export-recipe-${index}`,
        statement_fragment: String(row.statement_fragment ?? EXPORT_FIELD_UNAVAILABLE),
        supporting_proposition_ids: supportingIds,
        proposition_text: String(row.proposition_text ?? EXPORT_FIELD_UNAVAILABLE),
        source_locator: String(row.source_locator ?? EXPORT_FIELD_UNAVAILABLE),
        source_excerpt: String(row.source_excerpt ?? EXPORT_FIELD_UNAVAILABLE),
        support_status: row.support_status ?? "unsupported",
        source_url: source?.source_url?.trim() || undefined,
      };
    });
  }

  const fragments = buildStatementFragments(statement, context.propositionById);
  const refs = propositionRefsForStatement(statement);
  const completenessById = context.sourceCompletenessByPropositionId;

  return refs.map((ref, index) => {
    const proposition = context.propositionById.get(ref.propositionId);
    const source = proposition?.source_record_id
      ? context.sourceById.get(proposition.source_record_id)
      : undefined;
    const completeness = completenessById?.get(ref.propositionId);

    return {
      rowId: `${ref.role}-${ref.propositionId}-${ref.contextLocator ?? ""}-${index}`,
      statement_fragment: pickStatementFragmentForRef(statement, ref, proposition, fragments),
      supporting_proposition_ids: [ref.propositionId],
      proposition_text: resolvePropositionText(proposition),
      source_locator: resolveSourceLocator(proposition, source, context.fragmentById),
      source_excerpt: resolveSourceExcerpt(proposition, context.fragmentById),
      support_status: inferSupportStatus(ref, completeness),
      source_url: source?.source_url?.trim() || undefined,
    };
  });
}

function hasUnresolvedContext(statement: LawStatementRow): boolean {
  return (statement.required_context ?? []).some((ctx) => {
    if (isResolvedTypedContext(ctx)) {
      return false;
    }
    return String(ctx.resolution_status ?? "").trim() === "unresolved";
  });
}

function hasAmbiguousContext(statement: LawStatementRow): boolean {
  return (statement.required_context ?? []).some((ctx) => {
    if (isResolvedTypedContext(ctx)) {
      return false;
    }
    return String(ctx.resolution_status ?? "").trim() === "ambiguous";
  });
}

function summarizeRecipeSupport(recipe: StatementRecipeRow[]): string {
  if (recipe.length === 0) {
    return EXPORT_FIELD_UNAVAILABLE;
  }
  if (recipe.some((row) => row.support_status === "unresolved")) {
    return "unresolved context in composition";
  }
  if (recipe.some((row) => row.support_status === "unsupported")) {
    return "unsupported proposition linkage present";
  }
  if (recipe.some((row) => row.support_status === "partial")) {
    return "partial support across recipe rows";
  }
  return "all recipe rows marked supported";
}

export function buildCoverageChecks(
  statement: LawStatementRow,
  recipe: StatementRecipeRow[],
): CoverageCheckEntry[] {
  const exportChecks = (
    statement as LawStatementRow & {
      coverage_checks?: Partial<Record<CoverageCheckKey, string>>;
    }
  ).coverage_checks;

  const entries: Array<{ key: CoverageCheckKey; label: string }> = [
    { key: "source_text_used", label: "Source text used" },
    { key: "statement_text_supported", label: "Statement text supported" },
    { key: "conditions_preserved", label: "Conditions preserved" },
    { key: "exceptions_preserved", label: "Exceptions preserved" },
    { key: "cross_references_resolved", label: "Cross references resolved" },
    { key: "scope_preserved", label: "Scope preserved" },
  ];

  return entries.map(({ key, label }) => {
    const exportValue = exportChecks?.[key]?.trim();
    if (exportValue) {
      return { key, label, value: exportValue, fromExport: true };
    }

    switch (key) {
      case "source_text_used": {
        const withExcerpt = recipe.filter(
          (row) => row.source_excerpt !== EXPORT_FIELD_UNAVAILABLE,
        ).length;
        if (withExcerpt === 0) {
          return { key, label, value: EXPORT_FIELD_UNAVAILABLE, fromExport: false };
        }
        return {
          key,
          label,
          value: `${withExcerpt} of ${recipe.length} recipe rows have source excerpt text`,
          fromExport: false,
        };
      }
      case "statement_text_supported":
        return {
          key,
          label,
          value: summarizeRecipeSupport(recipe),
          fromExport: false,
        };
      case "cross_references_resolved": {
        if (hasUnresolvedContext(statement)) {
          return { key, label, value: "unresolved cross-reference context", fromExport: false };
        }
        if (hasAmbiguousContext(statement)) {
          return { key, label, value: "ambiguous cross-reference context", fromExport: false };
        }
        if ((statement.required_context ?? []).length === 0 && (statement.connector_context ?? []).length === 0) {
          return { key, label, value: "no cross-reference composition required", fromExport: false };
        }
        return { key, label, value: "cross-reference context resolved in export", fromExport: false };
      }
      default:
        return { key, label, value: EXPORT_FIELD_UNAVAILABLE, fromExport: false };
    }
  });
}

export const SUPPORT_STATUS_CLASS: Record<SupportStatus, string> = {
  supported: "border-emerald-700/35 bg-emerald-950/10 text-emerald-950 dark:text-emerald-100",
  partial: "border-amber-700/35 bg-amber-950/10 text-amber-950 dark:text-amber-100",
  unresolved: "border-orange-700/35 bg-orange-950/10 text-orange-950 dark:text-orange-100",
  unsupported: "border-red-700/35 bg-red-950/10 text-red-950 dark:text-red-100",
};

export type CoverageWarningCategory =
  | "condition"
  | "exception"
  | "scope"
  | "definition"
  | "cross_reference"
  | "unresolved_context"
  | "general_warning";

export type CoverageWarningSeverity = "gap" | "warning" | "ok" | "unknown";

export type CoverageWarningItem = {
  id: string;
  category: CoverageWarningCategory;
  label: string;
  detail: string;
  severity: CoverageWarningSeverity;
  fromExport: boolean;
};

export type CompositionPropositionStackItem = {
  recipeRowId: string;
  propositionId: string;
  role: LawStatementPropRole;
  roleLabel: string;
  sourceLocator: string;
  propositionText: string;
  sourceExcerpt: string;
  supportStatus: SupportStatus;
  stackOrder: number;
};

export type CompositionPropositionGroup = {
  sourceLocator: string;
  items: CompositionPropositionStackItem[];
};

const ROLE_ORDER: Record<LawStatementPropRole, number> = {
  source: 0,
  supporting: 1,
  exception: 2,
  displaced_rule: 3,
  trigger: 4,
  required_context: 5,
  connector: 6,
  via: 7,
};

const ROLE_LABEL: Record<LawStatementPropRole, string> = {
  source: "Source",
  supporting: "Supporting",
  exception: "Exception",
  displaced_rule: "Displaced rule",
  trigger: "Trigger",
  required_context: "Required context",
  connector: "Connector",
  via: "Via",
};

const COVERAGE_CATEGORY_BY_KEY: Partial<Record<CoverageCheckKey, CoverageWarningCategory>> = {
  conditions_preserved: "condition",
  exceptions_preserved: "exception",
  scope_preserved: "scope",
  cross_references_resolved: "cross_reference",
};

function inferCoverageSeverity(value: string): CoverageWarningSeverity {
  const normalized = value.toLowerCase();
  if (value === EXPORT_FIELD_UNAVAILABLE) {
    return "unknown";
  }
  if (
    normalized.includes("unresolved") ||
    normalized.includes("unsupported") ||
    normalized.includes("partial support") ||
    normalized.includes("ambiguous")
  ) {
    return "gap";
  }
  if (normalized.includes("no cross-reference") || normalized.includes("all recipe rows")) {
    return "ok";
  }
  return "warning";
}

function warningCategoryFromText(text: string): CoverageWarningCategory {
  const normalized = text.toLowerCase();
  if (normalized.includes("condition")) {
    return "condition";
  }
  if (normalized.includes("exception")) {
    return "exception";
  }
  if (normalized.includes("scope")) {
    return "scope";
  }
  if (normalized.includes("definition")) {
    return "definition";
  }
  if (normalized.includes("cross-reference") || normalized.includes("cross reference")) {
    return "cross_reference";
  }
  if (normalized.includes("unresolved") || normalized.includes("ambiguous")) {
    return "unresolved_context";
  }
  return "general_warning";
}

export function recipeRowsForFragment(
  fragment: StatementFragmentView,
  recipe: StatementRecipeRow[],
): StatementRecipeRow[] {
  const normalizedFragment = normalizeForMatch(fragment.text);
  if (!normalizedFragment) {
    return [];
  }
  return recipe.filter((row) => {
    const normalizedRow = normalizeForMatch(row.statement_fragment);
    if (!normalizedRow || normalizedRow === normalizeForMatch(EXPORT_FIELD_UNAVAILABLE)) {
      return false;
    }
    return (
      normalizedRow.includes(normalizedFragment) ||
      normalizedFragment.includes(normalizedRow) ||
      normalizedRow === normalizedFragment
    );
  });
}

export function buildCoverageWarningItems(
  statement: LawStatementRow,
  coverageChecks: CoverageCheckEntry[],
): CoverageWarningItem[] {
  const items: CoverageWarningItem[] = [];

  for (const check of coverageChecks) {
    const category = COVERAGE_CATEGORY_BY_KEY[check.key];
    if (!category) {
      continue;
    }
    items.push({
      id: `coverage:${check.key}`,
      category,
      label: check.label,
      detail: check.value,
      severity: inferCoverageSeverity(check.value),
      fromExport: check.fromExport,
    });
  }

  const definitionWarnings = (statement.warnings ?? []).filter((warning) =>
    warning.toLowerCase().includes("definition"),
  );
  if (definitionWarnings.length > 0) {
    for (const [index, warning] of definitionWarnings.entries()) {
      items.push({
        id: `definition-warning:${index}`,
        category: "definition",
        label: "Definition warning",
        detail: warning,
        severity: "warning",
        fromExport: true,
      });
    }
  } else if (statement.presentation_role === "supporting_definition") {
    items.push({
      id: "definition:presentation-role",
      category: "definition",
      label: "Definition material",
      detail: "Statement presentation role is supporting definition",
      severity: "warning",
      fromExport: true,
    });
  } else {
    items.push({
      id: "coverage:definitions_preserved",
      category: "definition",
      label: "Definitions preserved",
      detail: EXPORT_FIELD_UNAVAILABLE,
      severity: "unknown",
      fromExport: false,
    });
  }

  for (const [index, ctx] of (statement.required_context ?? []).entries()) {
    if (isResolvedTypedContext(ctx)) {
      continue;
    }
    const status = String(ctx.resolution_status ?? "").trim();
    if (status !== "unresolved" && status !== "ambiguous") {
      continue;
    }
    items.push({
      id: `context:${index}:${ctx.locator ?? "unknown"}`,
      category: "unresolved_context",
      label: `${status} context`,
      detail: `${ctx.locator ?? "unknown locator"} (${status})`,
      severity: status === "unresolved" ? "gap" : "warning",
      fromExport: true,
    });
  }

  for (const [index, warning] of (statement.warnings ?? []).entries()) {
    if (warning.toLowerCase().includes("definition")) {
      continue;
    }
    items.push({
      id: `warning:${index}`,
      category: warningCategoryFromText(warning),
      label: "Export warning",
      detail: warning,
      severity: "warning",
      fromExport: true,
    });
  }

  return items.sort((left, right) => {
    const severityRank: Record<CoverageWarningSeverity, number> = {
      gap: 0,
      warning: 1,
      unknown: 2,
      ok: 3,
    };
    const severityDelta = severityRank[left.severity] - severityRank[right.severity];
    if (severityDelta !== 0) {
      return severityDelta;
    }
    return left.label.localeCompare(right.label);
  });
}

export function buildCompositionPropositionGroups(
  statement: LawStatementRow,
  recipe: StatementRecipeRow[],
): CompositionPropositionGroup[] {
  const refs = propositionRefsForStatement(statement);
  const recipeByPropositionId = new Map<string, StatementRecipeRow>();
  for (const row of recipe) {
    for (const propositionId of row.supporting_proposition_ids) {
      if (!recipeByPropositionId.has(propositionId)) {
        recipeByPropositionId.set(propositionId, row);
      }
    }
  }

  const stackItems: CompositionPropositionStackItem[] = refs.map((ref, index) => {
    const row = recipeByPropositionId.get(ref.propositionId);
    return {
      recipeRowId: row?.rowId ?? `${ref.role}-${ref.propositionId}-${index}`,
      propositionId: ref.propositionId,
      role: ref.role,
      roleLabel: ROLE_LABEL[ref.role],
      sourceLocator: row?.source_locator ?? EXPORT_FIELD_UNAVAILABLE,
      propositionText: row?.proposition_text ?? EXPORT_FIELD_UNAVAILABLE,
      sourceExcerpt: row?.source_excerpt ?? EXPORT_FIELD_UNAVAILABLE,
      supportStatus: row?.support_status ?? "unsupported",
      stackOrder: index,
    };
  });

  const groupOrder: string[] = [];
  const buckets = new Map<string, CompositionPropositionStackItem[]>();
  for (const item of stackItems) {
    const key = item.sourceLocator;
    if (!buckets.has(key)) {
      groupOrder.push(key);
      buckets.set(key, []);
    }
    buckets.get(key)!.push(item);
  }

  return groupOrder.map((sourceLocator) => ({
    sourceLocator,
    items: (buckets.get(sourceLocator) ?? []).sort((left, right) => {
      const roleDelta = ROLE_ORDER[left.role] - ROLE_ORDER[right.role];
      if (roleDelta !== 0) {
        return roleDelta;
      }
      return left.stackOrder - right.stackOrder;
    }),
  }));
}
