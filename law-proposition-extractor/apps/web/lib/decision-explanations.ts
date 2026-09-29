/**
 * TypeScript models + indexes for Law Proposition Extractor decision_explanations.json.
 * Mirrors law_proposition_extractor_domain.DecisionExplanation — no heuristic reruns, no LLM prose.
 */

export type DecisionStage =
  | "selection"
  | "extraction"
  | "classification"
  | "grouping"
  | "relationship"
  | "effective_law"
  | "provenance"
  | "source_effect"
  | "review"
  | "unknown";

export type DecisionType =
  | "select"
  | "suppress"
  | "exclude"
  | "retain"
  | "diagnose"
  | "classify"
  | "infer"
  | "target"
  | "group"
  | "attach"
  | "link"
  | "inherit"
  | "assess"
  | "unknown";

export type DecisionSubjectKind =
  | "source_fragment"
  | "source_snapshot"
  | "source_legal_effect"
  | "proposition"
  | "extraction_candidate"
  | "legal_rule_relationship"
  | "legal_rule_group"
  | "effective_law_statement"
  | "unknown";

export type HeuristicMethod =
  | "deterministic"
  | "llm"
  | "hybrid"
  | "human"
  | "configuration"
  | "unknown";

export type DecisionInput = {
  kind: string;
  label?: string | null;
  value?: string | null;
  id?: string | null;
  [key: string]: unknown;
};

export type DecisionEvidence = {
  kind: string;
  label?: string | null;
  value?: string | null;
  id?: string | null;
  [key: string]: unknown;
};

export type DecisionAlternative = {
  kind: string;
  id?: string | null;
  label?: string | null;
  value?: string | null;
  role?: string | null;
  [key: string]: unknown;
};

export type SuppressedDecisionItem = {
  kind: string;
  id: string;
  reason?: string | null;
  label?: string | null;
  [key: string]: unknown;
};

export type DecisionTraceReference = {
  kind: string;
  id?: string | null;
  label?: string | null;
  [key: string]: unknown;
};

export type DecisionExplanation = {
  id: string;
  stage: DecisionStage | string;
  decision_type: DecisionType | string;
  subject_kind: DecisionSubjectKind | string;
  subject_id: string;
  outcome: string;
  method: HeuristicMethod | string;
  rule_id: string;
  rule_version: string;
  summary: string;
  inputs: DecisionInput[];
  evidence: DecisionEvidence[];
  alternatives: DecisionAlternative[];
  suppressed_items: SuppressedDecisionItem[];
  confidence?: string | null;
  diagnostics: string[];
  code_references: string[];
  trace_references: DecisionTraceReference[];
  model_alias?: string | null;
  prompt_version?: string | null;
  metadata: Record<string, unknown>;
  [key: string]: unknown;
};

export type DecisionExplanationsArtifact = {
  schema_version?: string;
  run_id?: string;
  decisions: DecisionExplanation[];
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

export type DecisionExplanationsResponse = {
  run_id?: string;
  decision_explanations: DecisionExplanationsArtifact;
  decision_count: number;
  artifact_present: boolean;
};

export type HeuristicDefinition = {
  rule_id: string;
  version: string;
  name: string;
  plain_english_summary: string;
  stage: DecisionStage | string;
  method: HeuristicMethod | string;
  input_kinds?: string[];
  output_kinds?: string[];
  trigger_summary?: string;
  precedence_summary?: string;
  failure_mode?: string;
  diagnostic_codes?: string[];
  code_references?: string[];
  test_references?: string[];
  example_summary?: string;
  [key: string]: unknown;
};

export type HeuristicsResponse = {
  registry_version?: string;
  run_id?: string | null;
  referenced_only?: boolean;
  heuristic_count: number;
  heuristics: HeuristicDefinition[];
};

export type DecisionExplanationIndex = {
  artifactPresent: boolean;
  runId: string | null;
  decisions: DecisionExplanation[];
  parseDiagnostics: string[];
  byId: Map<string, DecisionExplanation>;
  bySubjectKey: Map<string, DecisionExplanation[]>;
  byRuleId: Map<string, DecisionExplanation[]>;
  byStage: Map<string, DecisionExplanation[]>;
  bySourceFragmentId: Map<string, DecisionExplanation[]>;
  byPropositionId: Map<string, DecisionExplanation[]>;
  byLegalRuleGroupId: Map<string, DecisionExplanation[]>;
  byLegalRelationshipId: Map<string, DecisionExplanation[]>;
  byEffectiveLawStatementId: Map<string, DecisionExplanation[]>;
  bySourceLocator: Map<string, DecisionExplanation[]>;
};

const KNOWN_STAGES = new Set<string>([
  "selection",
  "extraction",
  "classification",
  "grouping",
  "relationship",
  "effective_law",
  "provenance",
  "source_effect",
  "review",
]);

const KNOWN_TYPES = new Set<string>([
  "select",
  "suppress",
  "exclude",
  "retain",
  "diagnose",
  "classify",
  "infer",
  "target",
  "group",
  "attach",
  "link",
  "inherit",
  "assess",
]);

const KNOWN_SUBJECTS = new Set<string>([
  "source_fragment",
  "source_snapshot",
  "source_legal_effect",
  "proposition",
  "extraction_candidate",
  "legal_rule_relationship",
  "legal_rule_group",
  "effective_law_statement",
]);

const KNOWN_METHODS = new Set<string>([
  "deterministic",
  "llm",
  "hybrid",
  "human",
  "configuration",
]);

function trimOrNull(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text ? text : null;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item ?? "").trim()).filter(Boolean);
}

function normalizeEnum(value: unknown, known: Set<string>, fallback: string): string {
  const raw = trimOrNull(value);
  if (!raw) {
    return fallback;
  }
  return known.has(raw) ? raw : raw;
}

function parseFactRow(row: unknown): DecisionInput | null {
  if (!row || typeof row !== "object") {
    return null;
  }
  const raw = row as Record<string, unknown>;
  const kind = trimOrNull(raw.kind);
  if (!kind) {
    return null;
  }
  return {
    ...raw,
    kind,
    label: trimOrNull(raw.label),
    value: raw.value == null ? null : String(raw.value),
    id: trimOrNull(raw.id),
  };
}

function parseAlternative(row: unknown): DecisionAlternative | null {
  if (!row || typeof row !== "object") {
    return null;
  }
  const raw = row as Record<string, unknown>;
  const kind = trimOrNull(raw.kind);
  if (!kind) {
    return null;
  }
  return {
    ...raw,
    kind,
    id: trimOrNull(raw.id),
    label: trimOrNull(raw.label),
    value: raw.value == null ? null : String(raw.value),
    role: trimOrNull(raw.role),
  };
}

function parseSuppressed(row: unknown): SuppressedDecisionItem | null {
  if (!row || typeof row !== "object") {
    return null;
  }
  const raw = row as Record<string, unknown>;
  const kind = trimOrNull(raw.kind);
  const id = trimOrNull(raw.id);
  if (!kind || !id) {
    return null;
  }
  return {
    ...raw,
    kind,
    id,
    reason: trimOrNull(raw.reason),
    label: trimOrNull(raw.label),
  };
}

function parseTrace(row: unknown): DecisionTraceReference | null {
  if (!row || typeof row !== "object") {
    return null;
  }
  const raw = row as Record<string, unknown>;
  const kind = trimOrNull(raw.kind);
  if (!kind) {
    return null;
  }
  return {
    ...raw,
    kind,
    id: trimOrNull(raw.id),
    label: trimOrNull(raw.label),
  };
}

export function emptyDecisionExplanationsArtifact(
  runId?: string | null,
): DecisionExplanationsArtifact {
  return {
    schema_version: "1",
    run_id: trimOrNull(runId) ?? undefined,
    decisions: [],
    metadata: { missing_artifact: true },
  };
}

export function parseDecisionExplanation(
  row: unknown,
  diagnostics: string[],
): DecisionExplanation | null {
  if (!row || typeof row !== "object") {
    diagnostics.push("Skipped non-object decision record.");
    return null;
  }
  const raw = row as Record<string, unknown>;
  const id = trimOrNull(raw.id);
  const subjectId = trimOrNull(raw.subject_id);
  const ruleId = trimOrNull(raw.rule_id);
  const ruleVersion = trimOrNull(raw.rule_version);
  const outcome = trimOrNull(raw.outcome);
  const summary = trimOrNull(raw.summary);
  if (!id || !subjectId || !ruleId || !ruleVersion || !outcome || !summary) {
    diagnostics.push(
      `Omitted malformed decision (missing required fields): ${id ?? "(no id)"}.`,
    );
    return null;
  }

  const metadata =
    raw.metadata && typeof raw.metadata === "object" && !Array.isArray(raw.metadata)
      ? (raw.metadata as Record<string, unknown>)
      : {};

  return {
    ...raw,
    id,
    stage: normalizeEnum(raw.stage, KNOWN_STAGES, "unknown"),
    decision_type: normalizeEnum(raw.decision_type, KNOWN_TYPES, "unknown"),
    subject_kind: normalizeEnum(raw.subject_kind, KNOWN_SUBJECTS, "unknown"),
    subject_id: subjectId,
    outcome,
    method: normalizeEnum(raw.method, KNOWN_METHODS, "unknown"),
    rule_id: ruleId,
    rule_version: ruleVersion,
    summary,
    inputs: Array.isArray(raw.inputs)
      ? raw.inputs.map(parseFactRow).filter((item): item is DecisionInput => item != null)
      : [],
    evidence: Array.isArray(raw.evidence)
      ? raw.evidence.map(parseFactRow).filter((item): item is DecisionEvidence => item != null)
      : [],
    alternatives: Array.isArray(raw.alternatives)
      ? raw.alternatives
          .map(parseAlternative)
          .filter((item): item is DecisionAlternative => item != null)
      : [],
    suppressed_items: Array.isArray(raw.suppressed_items)
      ? raw.suppressed_items
          .map(parseSuppressed)
          .filter((item): item is SuppressedDecisionItem => item != null)
      : [],
    confidence: trimOrNull(raw.confidence),
    diagnostics: asStringList(raw.diagnostics),
    code_references: asStringList(raw.code_references),
    trace_references: Array.isArray(raw.trace_references)
      ? raw.trace_references
          .map(parseTrace)
          .filter((item): item is DecisionTraceReference => item != null)
      : [],
    model_alias: trimOrNull(raw.model_alias),
    prompt_version: trimOrNull(raw.prompt_version),
    metadata,
  };
}

export function parseDecisionExplanationsArtifact(
  payload: unknown,
  runId?: string | null,
): DecisionExplanationsArtifact {
  if (!payload || typeof payload !== "object") {
    return emptyDecisionExplanationsArtifact(runId);
  }
  const root = payload as Record<string, unknown>;
  const nested =
    root.decision_explanations && typeof root.decision_explanations === "object"
      ? (root.decision_explanations as Record<string, unknown>)
      : root;

  const diagnostics: string[] = [];
  const decisionsRaw = nested.decisions;
  const decisions = Array.isArray(decisionsRaw)
    ? decisionsRaw
        .map((row) => parseDecisionExplanation(row, diagnostics))
        .filter((row): row is DecisionExplanation => row != null)
    : [];

  const metadata =
    nested.metadata && typeof nested.metadata === "object" && !Array.isArray(nested.metadata)
      ? { ...(nested.metadata as Record<string, unknown>) }
      : {};
  if (diagnostics.length > 0) {
    metadata.parse_diagnostics = diagnostics;
  }

  return {
    ...nested,
    schema_version: trimOrNull(nested.schema_version) ?? "1",
    run_id: trimOrNull(nested.run_id) ?? trimOrNull(runId) ?? undefined,
    decisions,
    metadata,
  };
}

export function parseDecisionExplanationsResponse(
  payload: unknown,
  runId?: string | null,
): DecisionExplanationsResponse {
  if (!payload || typeof payload !== "object") {
    return {
      run_id: trimOrNull(runId) ?? undefined,
      decision_explanations: emptyDecisionExplanationsArtifact(runId),
      decision_count: 0,
      artifact_present: false,
    };
  }
  const root = payload as Record<string, unknown>;
  const artifact = parseDecisionExplanationsArtifact(payload, runId);
  const present =
    root.artifact_present === true ||
    (root.artifact_present !== false &&
      artifact.metadata?.missing_artifact !== true &&
      artifact.decisions.length > 0);
  return {
    run_id: trimOrNull(root.run_id) ?? artifact.run_id,
    decision_explanations: artifact,
    decision_count:
      typeof root.decision_count === "number" ? root.decision_count : artifact.decisions.length,
    artifact_present: present,
  };
}

export function parseHeuristicDefinition(row: unknown): HeuristicDefinition | null {
  if (!row || typeof row !== "object") {
    return null;
  }
  const raw = row as Record<string, unknown>;
  const ruleId = trimOrNull(raw.rule_id);
  const version = trimOrNull(raw.version);
  const name = trimOrNull(raw.name);
  const summary = trimOrNull(raw.plain_english_summary);
  if (!ruleId || !version || !name || !summary) {
    return null;
  }
  return {
    ...raw,
    rule_id: ruleId,
    version,
    name,
    plain_english_summary: summary,
    stage: normalizeEnum(raw.stage, KNOWN_STAGES, "unknown"),
    method: normalizeEnum(raw.method, KNOWN_METHODS, "unknown"),
    input_kinds: asStringList(raw.input_kinds),
    output_kinds: asStringList(raw.output_kinds),
    trigger_summary: trimOrNull(raw.trigger_summary) ?? undefined,
    precedence_summary: trimOrNull(raw.precedence_summary) ?? undefined,
    failure_mode: trimOrNull(raw.failure_mode) ?? undefined,
    diagnostic_codes: asStringList(raw.diagnostic_codes),
    code_references: asStringList(raw.code_references),
    test_references: asStringList(raw.test_references),
    example_summary: trimOrNull(raw.example_summary) ?? undefined,
  };
}

export function parseHeuristicsResponse(payload: unknown): HeuristicsResponse {
  if (!payload || typeof payload !== "object") {
    return { heuristic_count: 0, heuristics: [] };
  }
  const root = payload as Record<string, unknown>;
  const heuristics = Array.isArray(root.heuristics)
    ? root.heuristics
        .map(parseHeuristicDefinition)
        .filter((row): row is HeuristicDefinition => row != null)
    : [];
  return {
    registry_version: trimOrNull(root.registry_version) ?? undefined,
    run_id: trimOrNull(root.run_id),
    referenced_only: root.referenced_only === true,
    heuristic_count:
      typeof root.heuristic_count === "number" ? root.heuristic_count : heuristics.length,
    heuristics,
  };
}

export function heuristicByRuleId(
  heuristics: Iterable<HeuristicDefinition>,
): Map<string, HeuristicDefinition> {
  const map = new Map<string, HeuristicDefinition>();
  for (const row of heuristics) {
    map.set(row.rule_id, row);
  }
  return map;
}

function pushIndex(
  map: Map<string, DecisionExplanation[]>,
  key: string | null | undefined,
  decision: DecisionExplanation,
) {
  const normalized = trimOrNull(key);
  if (!normalized) {
    return;
  }
  const existing = map.get(normalized);
  if (existing) {
    if (existing.some((row) => row.id === decision.id)) {
      return;
    }
    existing.push(decision);
  } else {
    map.set(normalized, [decision]);
  }
}

function metaString(metadata: Record<string, unknown>, key: string): string | null {
  return trimOrNull(metadata[key]);
}

function metaStringList(metadata: Record<string, unknown>, key: string): string[] {
  const value = metadata[key];
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  return [];
}

function evidenceValues(decision: DecisionExplanation, kind: string): string[] {
  return decision.evidence
    .filter((row) => row.kind === kind)
    .map((row) => trimOrNull(row.value) ?? trimOrNull(row.id))
    .filter((value): value is string => value != null);
}

/**
 * Build once-per-run indexes from structured fields only (no summary parsing).
 */
export function buildDecisionExplanationIndex(
  artifact: DecisionExplanationsArtifact,
  options?: { artifactPresent?: boolean },
): DecisionExplanationIndex {
  const parseDiagnostics = asStringList(artifact.metadata?.parse_diagnostics);
  const byId = new Map<string, DecisionExplanation>();
  const bySubjectKey = new Map<string, DecisionExplanation[]>();
  const byRuleId = new Map<string, DecisionExplanation[]>();
  const byStage = new Map<string, DecisionExplanation[]>();
  const bySourceFragmentId = new Map<string, DecisionExplanation[]>();
  const byPropositionId = new Map<string, DecisionExplanation[]>();
  const byLegalRuleGroupId = new Map<string, DecisionExplanation[]>();
  const byLegalRelationshipId = new Map<string, DecisionExplanation[]>();
  const byEffectiveLawStatementId = new Map<string, DecisionExplanation[]>();
  const bySourceLocator = new Map<string, DecisionExplanation[]>();

  for (const decision of artifact.decisions) {
    if (byId.has(decision.id)) {
      parseDiagnostics.push(`Duplicate decision id rejected from index: ${decision.id}`);
      continue;
    }
    byId.set(decision.id, decision);
    pushIndex(bySubjectKey, `${decision.subject_kind}:${decision.subject_id}`, decision);
    pushIndex(byRuleId, decision.rule_id, decision);
    pushIndex(byStage, String(decision.stage), decision);

    const metadata = decision.metadata ?? {};
    pushIndex(bySourceFragmentId, metaString(metadata, "source_fragment_id"), decision);
    pushIndex(byPropositionId, metaString(metadata, "source_proposition_id"), decision);
    pushIndex(byPropositionId, metaString(metadata, "receiving_proposition_id"), decision);
    pushIndex(byPropositionId, metaString(metadata, "context_proposition_id"), decision);
    for (const memberId of metaStringList(metadata, "member_proposition_ids")) {
      pushIndex(byPropositionId, memberId, decision);
    }
    if (decision.subject_kind === "proposition") {
      pushIndex(byPropositionId, decision.subject_id, decision);
    }

    pushIndex(byLegalRuleGroupId, metaString(metadata, "legal_rule_group_id"), decision);
    if (decision.subject_kind === "legal_rule_group") {
      pushIndex(byLegalRuleGroupId, decision.subject_id, decision);
    }
    pushIndex(byLegalRelationshipId, metaString(metadata, "legal_rule_relationship_id"), decision);
    pushIndex(byLegalRelationshipId, metaString(metadata, "typed_relationship_id"), decision);
    if (decision.subject_kind === "legal_rule_relationship") {
      pushIndex(byLegalRelationshipId, decision.subject_id, decision);
    }

    pushIndex(
      byEffectiveLawStatementId,
      metaString(metadata, "effective_law_statement_id"),
      decision,
    );
    if (decision.subject_kind === "effective_law_statement") {
      pushIndex(byEffectiveLawStatementId, decision.subject_id, decision);
    }

    for (const locator of evidenceValues(decision, "source_locator")) {
      pushIndex(bySourceLocator, locator, decision);
    }
    for (const locator of evidenceValues(decision, "canonical_target_locator")) {
      pushIndex(bySourceLocator, locator, decision);
    }
    for (const locator of evidenceValues(decision, "canonical_locator")) {
      pushIndex(bySourceLocator, locator, decision);
    }
    for (const row of decision.alternatives) {
      pushIndex(bySourceLocator, trimOrNull(row.value), decision);
    }

    if (decision.subject_kind === "source_fragment") {
      pushIndex(bySourceFragmentId, decision.subject_id, decision);
    }
  }

  const artifactPresent =
    options?.artifactPresent ??
    (artifact.metadata?.missing_artifact !== true && artifact.decisions.length > 0);

  return {
    artifactPresent,
    runId: trimOrNull(artifact.run_id),
    decisions: [...byId.values()],
    parseDiagnostics,
    byId,
    bySubjectKey,
    byRuleId,
    byStage,
    bySourceFragmentId,
    byPropositionId,
    byLegalRuleGroupId,
    byLegalRelationshipId,
    byEffectiveLawStatementId,
    bySourceLocator,
  };
}

export function methodLabel(method: string | null | undefined): string {
  switch (String(method ?? "").trim()) {
    case "configuration":
      return "Run configuration";
    case "deterministic":
      return "Deterministic rule";
    case "llm":
      return "Language model";
    case "hybrid":
      return "Model + deterministic checks";
    case "human":
      return "Human review";
    default:
      return "Unknown method";
  }
}

export const STAGE_TIMELINE_ORDER = [
  "provenance",
  "selection",
  "extraction",
  "classification",
  "grouping",
  "relationship",
  "effective_law",
  "source_effect",
] as const;

export const STAGE_DISPLAY_TITLES: Record<(typeof STAGE_TIMELINE_ORDER)[number], string> = {
  provenance: "Source and version",
  selection: "Source selection",
  extraction: "Extraction and composition",
  classification: "Legal classification",
  grouping: "Rule grouping",
  relationship: "Legal relationships",
  effective_law: "Effective-law context",
  source_effect: "Source change annotations",
};
