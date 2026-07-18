function normalizeSearchText(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\./g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** Match every query term anywhere across the supplied searchable fields. */
export function matchesSearchQuery(
  query: string,
  ...values: Array<string | null | undefined>
): boolean {
  const terms = normalizeSearchText(query).split(/\s+/).filter(Boolean);
  if (terms.length === 0) return false;

  const searchableTerms = normalizeSearchText(values.filter(Boolean).join(" "))
    .split(/\s+/)
    .filter(Boolean);
  return terms.every((term) =>
    searchableTerms.some((candidate) =>
      term.length <= 2 ? candidate === term : candidate.includes(term),
    ),
  );
}
