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

/** Return a readable first sentence without splitting common abbreviations. */
export function stancePreview(stance: string, fallbackLength = 180): string {
  const normalized = stance.trim();

  for (let index = 0; index < normalized.length; index += 1) {
    const character = normalized[index];
    if (!".!?".includes(character)) continue;

    const nextCharacter = normalized[index + 1];
    if (nextCharacter && !/\s/.test(nextCharacter)) continue;
    if (character === "." && isAbbreviation(normalized.slice(0, index + 1)))
      continue;

    return normalized.slice(0, index + 1);
  }

  if (normalized.length <= fallbackLength) return normalized;

  const shortened = normalized.slice(0, fallbackLength);
  const lastSpace = shortened.lastIndexOf(" ");
  return `${shortened.slice(0, lastSpace > fallbackLength * 0.66 ? lastSpace : fallbackLength).trim()}…`;
}
