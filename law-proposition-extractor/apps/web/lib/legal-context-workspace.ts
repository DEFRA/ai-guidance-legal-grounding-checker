export function addReferenceToWorkspace(
  workspaceIds: readonly string[],
  referenceId: string,
): string[] {
  if (workspaceIds.includes(referenceId)) {
    return [...workspaceIds];
  }
  return [...workspaceIds, referenceId];
}

export function removeReferenceFromWorkspace(
  workspaceIds: readonly string[],
  referenceId: string,
): string[] {
  return workspaceIds.filter((id) => id !== referenceId);
}

export function selectedReferenceAfterRemoval(
  workspaceIds: readonly string[],
  removedReferenceId: string,
  currentSelectedId: string | null,
): string | null {
  if (currentSelectedId !== removedReferenceId) {
    return currentSelectedId;
  }
  const remaining = workspaceIds.filter((id) => id !== removedReferenceId);
  return remaining.length > 0 ? remaining[remaining.length - 1]! : null;
}

export function resolveWorkspaceReferences<T extends { id: string }>(
  workspaceIds: readonly string[],
  referencesById: ReadonlyMap<string, T>,
): T[] {
  return workspaceIds
    .map((id) => referencesById.get(id))
    .filter((reference): reference is T => reference !== undefined);
}
