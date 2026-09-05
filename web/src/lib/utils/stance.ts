const NON_TERMINAL_ABBREVIATIONS = new Set([
  "dr.",
  "e.g.",
  "i.e.",
  "jr.",
  "mr.",
  "mrs.",
  "ms.",
  "prof.",
  "sen.",
  "sr.",
  "st.",
  "u.s.",
  "vs.",
]);

function isAbbreviation(textThroughPeriod: string): boolean {
  const token = textThroughPeriod.trim().split(/\s+/).at(-1)?.toLowerCase();
  if (!token) return false;
  return (
    NON_TERMINAL_ABBREVIATIONS.has(token) || /^(?:[a-z]\.){2,}$/i.test(token)
  );
}

/** Return a readable sentence-bounded preview without splitting abbreviations. */
export function stancePreview(
  stance: string,
  fallbackLength = 180,
  minimumLength = 0,
): string {
  const normalized = stance.trim();

  for (let index = 0; index < normalized.length; index += 1) {
    const character = normalized[index];
    if (!".!?".includes(character)) continue;

    const nextCharacter = normalized[index + 1];
    if (nextCharacter && !/\s/.test(nextCharacter)) continue;
    if (character === "." && isAbbreviation(normalized.slice(0, index + 1)))
      continue;

    if (index + 1 >= minimumLength) return normalized.slice(0, index + 1);
  }

  if (normalized.length <= fallbackLength) return normalized;

  const shortened = normalized.slice(0, fallbackLength);
  const lastSpace = shortened.lastIndexOf(" ");
  return `${shortened.slice(0, lastSpace > fallbackLength * 0.66 ? lastSpace : fallbackLength).trim()}…`;
}

/**
 * Hard-capped preview for dense modules (the homepage comparison) where a
 * sentence-bounded preview can still run several hundred characters.
 */
export function collapsedPreview(text: string, limit = 120): string {
  const normalized = text.trim();
  if (normalized.length <= limit) return normalized;

  const shortened = normalized.slice(0, limit);
  const lastSpace = shortened.lastIndexOf(" ");
  return `${shortened
    .slice(0, lastSpace > limit * 0.66 ? lastSpace : limit)
    .trim()}…`;
}
