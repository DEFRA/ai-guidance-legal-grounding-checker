import type {
  ContextRequirementResolution,
  ResolvedContextFragment,
  ResolvedLocatorChild,
} from "@/lib/context-locator-resolution";
import { displaySourceExcerpt, joinExcerptParts } from "@/lib/excerpt-display";
import {
  EXPORT_FIELD_UNAVAILABLE,
  buildStatementFragments,
  buildStatementRecipe,
  type CompositionBuildContext,
  type StatementRecipeRow,
} from "@/lib/law-statements-composition";
import {
  propositionRefsForStatement,
  type LawStatementPropRole,
  type LawStatementRow,
  type PropositionRow,
} from "@/lib/law-statements-index";
import { legislationProvisionUrl } from "@/lib/legislation-gov-uk-url";

export type LawFragmentView = {
  id: string;
  sourceLocator: string;
  sourceExcerpt: string;
  propositionIds: string[];
  /** Deep-link to the provision on legislation.gov.uk when source_url is known. */
  legislationUrl: string | null;
};

export type PropositionReviewView = {
  propositionId: string;
  role: LawStatementPropRole;
  roleLabel: string;
  propositionText: string;
  sourceLocator: string;
  sourceExcerpt: string;
  legislationUrl: string | null;
};

export type CompositionSourceView = {
  propositionId: string;
  role: LawStatementPropRole;
  roleLabel: string;
  fragmentLocator: string;
  evidenceExcerpt: string;
  legislationUrl: string | null;
};

export type AssessmentContextStatus =
  | "resolved"
  | "resolved_container"
  | "partially_resolved"
  | "unresolved"
  | "ambiguous"
  | "external";

export type AssessmentContextView = {
  locator: string;
  status: AssessmentContextStatus;
  inheritedContextLabel?: string;
  resolvedLocator?: string;
  unresolvedChild?: string;
  reason?: string;
  fragments: ResolvedContextFragment[];
  children?: ResolvedLocatorChild[];
};

const COMPOSITION_SOURCE_ROLES: ReadonlySet<LawStatementPropRole> = new Set([
  "source",
  "supporting",
]);

const ROLE_LABEL: Record<string, string> = {
  source: "Source",
  supporting: "Supporting",
  exception: "Exception",
  displaced_rule: "Displaced rule",
  trigger: "Trigger",
  required_context: "Required context",
  connector: "Connector",
  via: "Via",
};

function displaySourceExcerptFromParts(parts: readonly string[], fallback: string): string {
  const trimmed = parts.map((part) => part.trim()).filter(Boolean);
  if (trimmed.length === 0) {
    return displaySourceExcerpt(fallback, EXPORT_FIELD_UNAVAILABLE);
  }
  if (trimmed.length === 1) {
    return displaySourceExcerpt(trimmed[0]!, EXPORT_FIELD_UNAVAILABLE);
  }
  return joinExcerptParts(trimmed);
}

function displayContextFragment(fragment: ResolvedContextFragment): ResolvedContextFragment {
  return {
    ...fragment,
    excerpt: displaySourceExcerpt(fragment.excerpt, EXPORT_FIELD_UNAVAILABLE),
  };
}

function displayContextChild(child: ResolvedLocatorChild): ResolvedLocatorChild {
  return {
    ...child,
    fragments: child.fragments.map(displayContextFragment),
  };
}

function sourceExcerptPartsForProposition(
  proposition: PropositionRow | undefined,
  fragmentById: CompositionBuildContext["fragmentById"],
): string[] {
  const parts: string[] = [];
  const fragmentId = proposition?.source_fragment_id?.trim();
  if (fragmentId) {
    const fragmentText = fragmentById.get(fragmentId)?.fragment_text?.trim();
    if (fragmentText) {
      parts.push(fragmentText);
    }
  }
  if (parts.length === 0) {
    const evidenceQuote = proposition?.extraction_debug_meta?.evidence_quote?.trim();
    if (evidenceQuote) {
      parts.push(evidenceQuote);
    }
  }
  return parts;
}

export function buildLawFragmentViews(recipe: StatementRecipeRow[]): LawFragmentView[] {
  const byKey = new Map<string, LawFragmentView>();
  for (const [index, row] of recipe.entries()) {
    if (row.source_excerpt === EXPORT_FIELD_UNAVAILABLE) {
      continue;
    }
    const key = `${row.source_locator}::${row.source_excerpt}`;
    const existing = byKey.get(key);
    if (existing) {
      for (const propositionId of row.supporting_proposition_ids) {
        if (!existing.propositionIds.includes(propositionId)) {
          existing.propositionIds.push(propositionId);
        }
      }
      if (!existing.legislationUrl && row.source_url) {
        existing.legislationUrl = legislationProvisionUrl(row.source_url, row.source_locator);
      }
      continue;
    }
    byKey.set(key, {
      id: `law-fragment-${index}`,
      sourceLocator: row.source_locator,
      sourceExcerpt: displaySourceExcerpt(row.source_excerpt, EXPORT_FIELD_UNAVAILABLE),
      propositionIds: [...row.supporting_proposition_ids],
      legislationUrl: legislationProvisionUrl(row.source_url, row.source_locator),
    });
  }
  return Array.from(byKey.values());
}

export function buildPropositionReviewViews(
  statement: LawStatementRow,
  recipe: StatementRecipeRow[],
  propositionById: Map<string, PropositionRow>,
  fragmentById?: CompositionBuildContext["fragmentById"],
): PropositionReviewView[] {
  const recipeByPropositionId = new Map<string, StatementRecipeRow>();
  for (const row of recipe) {
    for (const propositionId of row.supporting_proposition_ids) {
      if (!recipeByPropositionId.has(propositionId)) {
        recipeByPropositionId.set(propositionId, row);
      }
    }
  }

  return propositionRefsForStatement(statement).map((ref) => {
    const row = recipeByPropositionId.get(ref.propositionId);
    const proposition = propositionById.get(ref.propositionId);
    return {
      propositionId: ref.propositionId,
      role: ref.role,
      roleLabel: ROLE_LABEL[ref.role] ?? ref.role,
      propositionText:
        row?.proposition_text ??
        proposition?.proposition_text?.trim() ??
        proposition?.label?.trim() ??
        EXPORT_FIELD_UNAVAILABLE,
      sourceLocator: row?.source_locator ?? EXPORT_FIELD_UNAVAILABLE,
      sourceExcerpt: fragmentById
        ? displaySourceExcerptFromParts(
            sourceExcerptPartsForProposition(proposition, fragmentById),
            row?.source_excerpt ?? EXPORT_FIELD_UNAVAILABLE,
          )
        : displaySourceExcerpt(row?.source_excerpt ?? EXPORT_FIELD_UNAVAILABLE, EXPORT_FIELD_UNAVAILABLE),
      legislationUrl: legislationProvisionUrl(row?.source_url, row?.source_locator),
    };
  });
}

export function assessmentContextStatus(
  resolution: ContextRequirementResolution,
): AssessmentContextStatus {
  if (resolution.reason === "external reference") {
    return "external";
  }
  if (resolution.reason === "ambiguous") {
    return "ambiguous";
  }
  if (resolution.resolved && resolution.resolutionMode === "container") {
    return "resolved_container";
  }
  if (
    resolution.exportResolutionStatus === "partially_resolved" ||
    resolution.resolutionMode === "partial"
  ) {
    return "partially_resolved";
  }
  if (resolution.resolved) {
    return "resolved";
  }
  return "unresolved";
}

export function buildCompositionSourceViews(
  propositions: PropositionReviewView[],
): CompositionSourceView[] {
  return propositions
    .filter((proposition) => COMPOSITION_SOURCE_ROLES.has(proposition.role))
    .map((proposition) => ({
      propositionId: proposition.propositionId,
      role: proposition.role,
      roleLabel: proposition.roleLabel,
      fragmentLocator: proposition.sourceLocator,
      evidenceExcerpt: proposition.sourceExcerpt,
      legislationUrl: proposition.legislationUrl,
    }));
}

export function buildCompositionLawFragments(
  lawFragments: LawFragmentView[],
  compositionSources: CompositionSourceView[],
): LawFragmentView[] {
  const compositionPropositionIds = new Set(
    compositionSources.map((source) => source.propositionId),
  );
  return lawFragments.filter((fragment) =>
    fragment.propositionIds.some((propositionId) => compositionPropositionIds.has(propositionId)),
  );
}

export function buildAssessmentContextViews(
  requirements: ContextRequirementResolution[],
): AssessmentContextView[] {
  return requirements.map((requirement) => ({
    locator: requirement.locator,
    status: assessmentContextStatus(requirement),
    inheritedContextLabel: requirement.inheritedContextLabel,
    resolvedLocator: requirement.resolvedLocator,
    unresolvedChild: requirement.unresolvedChild,
    reason: requirement.reason,
    fragments: requirement.fragments.map(displayContextFragment),
    children: requirement.children?.map(displayContextChild),
  }));
}

export function collectWorkbenchDisplayExcerpts(input: {
  composition: ReturnType<typeof buildWorkbenchComposition>;
  assessmentContext: AssessmentContextView[];
}): string[] {
  const excerpts: string[] = [];

  for (const fragment of input.composition.lawFragments) {
    excerpts.push(fragment.sourceExcerpt);
  }
  for (const fragment of input.composition.compositionLawFragments) {
    excerpts.push(fragment.sourceExcerpt);
  }
  for (const source of input.composition.compositionSources) {
    excerpts.push(source.evidenceExcerpt);
  }
  for (const proposition of input.composition.propositions) {
    excerpts.push(proposition.sourceExcerpt);
  }
  for (const context of input.assessmentContext) {
    for (const fragment of context.fragments) {
      excerpts.push(fragment.excerpt);
    }
    for (const child of context.children ?? []) {
      for (const fragment of child.fragments) {
        excerpts.push(fragment.excerpt);
      }
    }
  }

  return excerpts.filter((excerpt) => excerpt.trim() && excerpt !== EXPORT_FIELD_UNAVAILABLE);
}

export function buildWorkbenchComposition(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): {
  fragments: ReturnType<typeof buildStatementFragments>;
  recipe: StatementRecipeRow[];
  lawFragments: LawFragmentView[];
  propositions: PropositionReviewView[];
  compositionSources: CompositionSourceView[];
  compositionLawFragments: LawFragmentView[];
} {
  const fragments = buildStatementFragments(statement, context.propositionById);
  const recipe = buildStatementRecipe(statement, context);
  const lawFragments = buildLawFragmentViews(recipe);
  const propositions = buildPropositionReviewViews(
    statement,
    recipe,
    context.propositionById,
    context.fragmentById,
  );
  const compositionSources = buildCompositionSourceViews(propositions);
  return {
    fragments,
    recipe,
    lawFragments,
    propositions,
    compositionSources,
    compositionLawFragments: buildCompositionLawFragments(lawFragments, compositionSources),
  };
}
