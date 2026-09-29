/**
 * Source-provided legislative heading helpers for Workbench display.
 * Distinct from locator labels and LLM proposition labels.
 */

export type StructuralHeadingKind =
  | "part"
  | "title"
  | "chapter"
  | "division"
  | "section"
  | "article"
  | "regulation"
  | "rule"
  | "schedule"
  | "annex"
  | "provision"
  | "cross_heading"
  | "unknown"
  | string;

export type StructuralHeadingRow = {
  kind?: StructuralHeadingKind | null;
  text?: string | null;
  number_label?: string | null;
  owner_fragment_id?: string | null;
  owner_locator?: string | null;
  source_element?: string | null;
  change_ids?: string[] | null;
  commentary_refs?: string[] | null;
};

export type StructuralHeadingContextRow = {
  kind?: StructuralHeadingKind | null;
  number_label?: string | null;
  heading_text?: string | null;
  owner_locator?: string | null;
  owner_fragment_id?: string | null;
  change_ids?: string[] | null;
  commentary_refs?: string[] | null;
};

export type FragmentWithHeading = {
  id?: string;
  fragment_id?: string;
  locator?: string;
  parent_fragment_id?: string | null;
  source_record_id?: string;
  source_snapshot_id?: string;
  number_label?: string | null;
  structural_heading?: StructuralHeadingRow | null;
};

const PROVISION_KINDS = new Set([
  "article",
  "regulation",
  "rule",
  "schedule",
  "annex",
  "section",
  "provision",
]);

function normalizeWs(value: string | null | undefined): string {
  return String(value ?? "")
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function formatStructuralHeadingDisplay(
  numberLabel: string | null | undefined,
  headingText: string | null | undefined,
): string {
  const number = normalizeWs(numberLabel);
  const heading = normalizeWs(headingText);
  if (number && heading) {
    return `${number} — ${heading}`;
  }
  return number || heading;
}

export function resolveStructuralHeadingContexts(
  fragment: FragmentWithHeading | null | undefined,
  fragmentsById: ReadonlyMap<string, FragmentWithHeading>,
): StructuralHeadingContextRow[] {
  if (!fragment) {
    return [];
  }
  const sourceRecordId = String(fragment.source_record_id ?? "").trim();
  const sourceSnapshotId = String(fragment.source_snapshot_id ?? "").trim();
  const chain: FragmentWithHeading[] = [];
  const seen = new Set<string>();
  let current: FragmentWithHeading | undefined = fragment;
  while (current) {
    const fid = String(current.id ?? current.fragment_id ?? "").trim();
    if (fid) {
      if (seen.has(fid)) {
        break;
      }
      seen.add(fid);
    }
    if (sourceRecordId && String(current.source_record_id ?? "") !== sourceRecordId) {
      break;
    }
    if (sourceSnapshotId && String(current.source_snapshot_id ?? "") !== sourceSnapshotId) {
      break;
    }
    chain.push(current);
    const parentId = String(current.parent_fragment_id ?? "").trim();
    if (!parentId) {
      break;
    }
    current = fragmentsById.get(parentId);
  }
  chain.reverse();
  const out: StructuralHeadingContextRow[] = [];
  const seenOwners = new Set<string>();
  for (const row of chain) {
    const heading = row.structural_heading;
    const text = normalizeWs(heading?.text);
    if (!text) {
      continue;
    }
    const ownerKey =
      normalizeWs(heading?.owner_locator) ||
      normalizeWs(row.locator) ||
      String(row.id ?? "") ||
      text;
    if (seenOwners.has(ownerKey)) {
      continue;
    }
    seenOwners.add(ownerKey);
    out.push({
      kind: heading?.kind ?? "unknown",
      number_label: normalizeWs(heading?.number_label) || normalizeWs(row.number_label) || null,
      heading_text: text,
      owner_locator: normalizeWs(heading?.owner_locator) || normalizeWs(row.locator) || null,
      owner_fragment_id: normalizeWs(heading?.owner_fragment_id) || String(row.id ?? "") || null,
      change_ids: Array.isArray(heading?.change_ids) ? heading.change_ids : [],
      commentary_refs: Array.isArray(heading?.commentary_refs) ? heading.commentary_refs : [],
    });
  }
  return out;
}

export function nearestProvisionHeading(
  fragment: FragmentWithHeading | null | undefined,
  fragmentsById: ReadonlyMap<string, FragmentWithHeading>,
): StructuralHeadingContextRow | null {
  const contexts = resolveStructuralHeadingContexts(fragment, fragmentsById);
  for (let i = contexts.length - 1; i >= 0; i -= 1) {
    const ctx = contexts[i]!;
    const kind = String(ctx.kind ?? "").toLowerCase();
    if (PROVISION_KINDS.has(kind)) {
      return ctx;
    }
  }
  return contexts.length > 0 ? contexts[contexts.length - 1]! : null;
}

/** Find article-level fragment for a cluster key within a source fragment set. */
export function findArticleFragmentForCluster(
  clusterKey: string,
  fragments: Iterable<FragmentWithHeading>,
): FragmentWithHeading | null {
  const key = clusterKey.includes("::")
    ? (clusterKey.split("::").pop() ?? clusterKey)
    : clusterKey;
  const match = key.match(/^article:(\d+[a-z]?)$/i);
  if (!match) {
    return null;
  }
  const locator = `article:${match[1]!.toLowerCase()}`;
  for (const frag of fragments) {
    if (String(frag.locator ?? "").toLowerCase() === locator) {
      return frag;
    }
  }
  return null;
}
