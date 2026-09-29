import { ensureEnrichedStatement } from "@/lib/analyze-trace-blocked-hard-cases";
import { EXPORT_FIELD_UNAVAILABLE } from "@/lib/law-statements-composition";
import type { CompositionBuildContext } from "@/lib/law-statements-composition";
import type { LawStatementRow } from "@/lib/law-statements-index";
import type { PropositionReviewView } from "@/lib/review-workbench-views";

export type WorkbenchPropositionRole =
  | "core"
  | "constraint"
  | "definition"
  | "exception"
  | "supporting";

export type ClassifiedProposition = {
  proposition: PropositionReviewView;
  role: WorkbenchPropositionRole;
  roleLabel: string;
};

export type PropositionRoleCounts = Record<WorkbenchPropositionRole, number>;

const ROLE_LABEL: Record<WorkbenchPropositionRole, string> = {
  core: "core",
  constraint: "constraint",
  definition: "definition",
  exception: "exception",
  supporting: "supporting",
};

const ROLE_PRIORITY: Record<WorkbenchPropositionRole, number> = {
  supporting: 0,
  exception: 1,
  definition: 2,
  constraint: 3,
  core: 4,
};

const MAIN_ROLES: ReadonlySet<WorkbenchPropositionRole> = new Set([
  "core",
  "constraint",
  "definition",
  "exception",
]);

const TRACE_ROLE_MAP: Record<string, WorkbenchPropositionRole | null> = {
  core_proposition: "core",
  constraint: "constraint",
  definition: "definition",
  exception: "exception",
  supporting_proposition: "supporting",
  required_context: null,
  connector: null,
  connector_inference: null,
  unknown: null,
};

function emptyRoleCounts(): PropositionRoleCounts {
  return {
    core: 0,
    constraint: 0,
    definition: 0,
    exception: 0,
    supporting: 0,
  };
}

function pluralizeRole(role: WorkbenchPropositionRole, count: number): string {
  if (count === 1) {
    return ROLE_LABEL[role];
  }
  if (role === "definition") {
    return "definitions";
  }
  return `${ROLE_LABEL[role]}s`;
}

export function formatPropositionRoleSummary(counts: PropositionRoleCounts): string {
  const parts: string[] = [];
  const order: WorkbenchPropositionRole[] = [
    "core",
    "constraint",
    "definition",
    "exception",
    "supporting",
  ];
  for (const role of order) {
    const count = counts[role];
    if (count > 0) {
      parts.push(`${count} ${pluralizeRole(role, count)}`);
    }
  }
  return parts.join(" • ");
}

export function formatMainPropositionRoleSummary(counts: PropositionRoleCounts): string {
  const mainCounts = { ...counts, supporting: 0 };
  return formatPropositionRoleSummary(mainCounts);
}

function fallbackRoleForProposition(proposition: PropositionReviewView): WorkbenchPropositionRole {
  if (proposition.role === "supporting") {
    return "supporting";
  }
  if (
    proposition.role === "required_context" ||
    proposition.role === "exception" ||
    proposition.role === "displaced_rule" ||
    proposition.role === "trigger"
  ) {
    return proposition.role === "exception" ? "exception" : "supporting";
  }
  return "core";
}

function classifyPropositionRolesFromTrace(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): Map<string, WorkbenchPropositionRole> {
  const enriched = ensureEnrichedStatement(statement, context);
  const roleByPropositionId = new Map<string, WorkbenchPropositionRole>();

  for (const span of enriched.composition_trace ?? []) {
    const mappedRole = TRACE_ROLE_MAP[span.role] ?? null;
    if (!mappedRole) {
      continue;
    }
    for (const propositionId of span.proposition_ids) {
      const trimmed = propositionId.trim();
      if (!trimmed) {
        continue;
      }
      const existing = roleByPropositionId.get(trimmed);
      if (!existing || ROLE_PRIORITY[mappedRole] > ROLE_PRIORITY[existing]) {
        roleByPropositionId.set(trimmed, mappedRole);
      }
    }
  }

  return roleByPropositionId;
}

function tracePropositionIds(statement: LawStatementRow, context: CompositionBuildContext): string[] {
  const enriched = ensureEnrichedStatement(statement, context);
  const ids = new Set<string>();
  for (const span of enriched.composition_trace ?? []) {
    for (const propositionId of span.proposition_ids) {
      const trimmed = propositionId.trim();
      if (trimmed) {
        ids.add(trimmed);
      }
    }
  }
  return Array.from(ids);
}

export function buildReviewPropositionsForClassification(input: {
  statement: LawStatementRow;
  propositions: PropositionReviewView[];
  compositionSourcePropositionIds: readonly string[];
  context: CompositionBuildContext;
}): PropositionReviewView[] {
  const existingById = new Map(
    input.propositions.map((proposition) => [proposition.propositionId, proposition]),
  );
  const traceIds = tracePropositionIds(input.statement, input.context);
  const targetIds =
    traceIds.length > 0 ? traceIds : input.compositionSourcePropositionIds.filter(Boolean);

  return targetIds.map((propositionId) => {
    const existing = existingById.get(propositionId);
    if (existing) {
      return existing;
    }
    const proposition = input.context.propositionById.get(propositionId);
    return {
      propositionId,
      role: "supporting",
      roleLabel: "Supporting",
      propositionText:
        proposition?.proposition_text?.trim() ??
        proposition?.label?.trim() ??
        EXPORT_FIELD_UNAVAILABLE,
      sourceLocator: EXPORT_FIELD_UNAVAILABLE,
      sourceExcerpt: EXPORT_FIELD_UNAVAILABLE,
      legislationUrl: null,
    };
  });
}

export function classifyWorkbenchPropositions(input: {
  statement: LawStatementRow;
  propositions: PropositionReviewView[];
  compositionSourcePropositionIds?: readonly string[];
  context: CompositionBuildContext;
}): {
  classified: ClassifiedProposition[];
  main: ClassifiedProposition[];
  supporting: ClassifiedProposition[];
  roleCounts: PropositionRoleCounts;
  mainRoleCounts: PropositionRoleCounts;
} {
  const reviewPropositions = buildReviewPropositionsForClassification({
    statement: input.statement,
    propositions: input.propositions,
    compositionSourcePropositionIds:
      input.compositionSourcePropositionIds ??
      input.propositions.map((proposition) => proposition.propositionId),
    context: input.context,
  });
  const traceRoles = classifyPropositionRolesFromTrace(input.statement, input.context);
  const classified = reviewPropositions.map((proposition) => {
    const role =
      traceRoles.get(proposition.propositionId) ??
      fallbackRoleForProposition(proposition);
    return {
      proposition,
      role,
      roleLabel: ROLE_LABEL[role],
    };
  });

  const roleCounts = emptyRoleCounts();
  for (const entry of classified) {
    roleCounts[entry.role] += 1;
  }

  const main = classified.filter((entry) => MAIN_ROLES.has(entry.role));
  const supporting = classified.filter((entry) => entry.role === "supporting");

  return {
    classified,
    main,
    supporting,
    roleCounts,
    mainRoleCounts: {
      ...roleCounts,
      supporting: 0,
    },
  };
}

export function groupMainPropositionsByRole(
  main: ClassifiedProposition[],
): Array<{ role: WorkbenchPropositionRole; label: string; items: ClassifiedProposition[] }> {
  const order: WorkbenchPropositionRole[] = ["core", "constraint", "definition", "exception"];
  const byRole = new Map<WorkbenchPropositionRole, ClassifiedProposition[]>();
  for (const entry of main) {
    const bucket = byRole.get(entry.role) ?? [];
    bucket.push(entry);
    byRole.set(entry.role, bucket);
  }
  return order
    .filter((role) => (byRole.get(role)?.length ?? 0) > 0)
    .map((role) => ({
      role,
      label: pluralizeRole(role, byRole.get(role)!.length),
      items: byRole.get(role)!,
    }));
}
