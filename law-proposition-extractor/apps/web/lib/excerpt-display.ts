/**
 * Display-only whitespace repair for law/source excerpts in the Review Workbench.
 * Does not mutate exported review data or source records.
 */

/** Punctuation / whitespace where adjacent parts need no inserted space. */
export function isSafeExcerptBoundary(left: string, right: string): boolean {
  if (!left || !right) {
    return true;
  }
  const leftChar = left.slice(-1);
  const rightChar = right.charAt(0);
  if (/\s/.test(leftChar) || /\s/.test(rightChar)) {
    return true;
  }
  if (/[([{—–-]/.test(leftChar)) {
    return false;
  }
  if (/[.,;:!?)\]}—–-]/.test(rightChar)) {
    return true;
  }
  if (leftChar === "." && /\d/.test(rightChar)) {
    return true;
  }
  return false;
}

/** Join excerpt parts with a single space unless the boundary is already safe. */
export function joinExcerptParts(parts: readonly string[]): string {
  const trimmed = parts.map((part) => part.trim()).filter(Boolean);
  if (trimmed.length === 0) {
    return "";
  }
  let result = trimmed[0]!;
  for (let index = 1; index < trimmed.length; index += 1) {
    const next = trimmed[index]!;
    if (isSafeExcerptBoundary(result, next)) {
      result += next;
    } else {
      result += ` ${next}`;
    }
  }
  return normalizeExcerptDisplay(result);
}

export function normalizeExcerptDisplay(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) {
    return trimmed;
  }
  return trimmed
    .replace(/\.([A-Z])/g, ". $1")
    .replace(/\)([A-Z])/g, ") $1")
    .replace(/\)([a-z])/g, ") $1");
}

export function formatExcerptForDisplay(
  excerpt: string,
  unavailableSentinel?: string,
): string {
  if (unavailableSentinel && excerpt === unavailableSentinel) {
    return excerpt;
  }
  if (!excerpt.trim()) {
    return excerpt;
  }
  return normalizeExcerptDisplay(excerpt);
}

/** Display-layer normalisation for human-visible source excerpts in the workbench. */
export function displaySourceExcerpt(
  excerpt: string,
  unavailableSentinel?: string,
): string {
  return formatExcerptForDisplay(excerpt, unavailableSentinel);
}
