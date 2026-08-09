const STATE_ABBREVIATIONS: Record<string, string> = {
  al: "alabama",
  ak: "alaska",
  az: "arizona",
  ar: "arkansas",
  ca: "california",
  co: "colorado",
  ct: "connecticut",
  de: "delaware",
  fl: "florida",
  ga: "georgia",
  hi: "hawaii",
  id: "idaho",
  il: "illinois",
  in: "indiana",
  ia: "iowa",
  ks: "kansas",
  ky: "kentucky",
  la: "louisiana",
  me: "maine",
  md: "maryland",
  ma: "massachusetts",
  mi: "michigan",
  mn: "minnesota",
  ms: "mississippi",
  mo: "missouri",
  mt: "montana",
  ne: "nebraska",
  nv: "nevada",
  nh: "new hampshire",
  nj: "new jersey",
  nm: "new mexico",
  ny: "new york",
  nc: "north carolina",
  nd: "north dakota",
  oh: "ohio",
  ok: "oklahoma",
  or: "oregon",
  pa: "pennsylvania",
  ri: "rhode island",
  sc: "south carolina",
  sd: "south dakota",
  tn: "tennessee",
  tx: "texas",
  ut: "utah",
  vt: "vermont",
  va: "virginia",
  wa: "washington",
  wv: "west virginia",
  wi: "wisconsin",
  wy: "wyoming",
  dc: "district of columbia",
};

export function normalizeSearchText(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\./g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function getSearchTokens(value: string): string[] {
  const normalized = normalizeSearchText(value);
  return normalized ? normalized.split(/\s+/).filter(Boolean) : [];
}

/** Check if a single query term matches any token or state expansion in searchable tokens */
function matchesTerm(
  term: string,
  searchableTokens: string[],
  fullSearchableText: string,
): boolean {
  if (!term) return false;

  // 1. Direct word prefix or exact match
  if (searchableTokens.some((token) => token.startsWith(term))) {
    return true;
  }

  // 2. State abbreviation expansion (e.g. term "tx" matches "texas")
  const stateFullName = STATE_ABBREVIATIONS[term];
  if (stateFullName) {
    const stateTokens = stateFullName.split(/\s+/);
    if (
      stateTokens.every((st) =>
        searchableTokens.some((token) => token.startsWith(st)),
      )
    ) {
      return true;
    }
  }

  // 3. Substring match for longer terms (3+ chars) across joined text
  if (term.length >= 3 && fullSearchableText.includes(term)) {
    return true;
  }

  return false;
}

/** Match every query term anywhere across the supplied searchable fields. */
export function matchesSearchQuery(
  query: string,
  ...values: Array<string | null | undefined>
): boolean {
  const terms = getSearchTokens(query);
  if (terms.length === 0) return false;

  const validValues = values.filter(Boolean) as string[];
  if (validValues.length === 0) return false;

  const searchableText = validValues.map(normalizeSearchText).join(" ");
  const searchableTokens = getSearchTokens(searchableText);

  return terms.every((term) =>
    matchesTerm(term, searchableTokens, searchableText),
  );
}

/** Calculate relevance score for ranking search results (higher is more relevant). */
export function scoreSearchMatch(
  query: string,
  primaryTitle: string | null | undefined,
  ...otherValues: Array<string | null | undefined>
): number {
  if (!query.trim()) return 0;
  const qNorm = normalizeSearchText(query);
  if (!qNorm) return 0;

  const pNorm = normalizeSearchText(primaryTitle || "");
  let score = 0;

  if (pNorm === qNorm) {
    score += 100;
  } else if (pNorm.startsWith(qNorm)) {
    score += 80;
  } else if (pNorm.includes(qNorm)) {
    score += 60;
  }

  const terms = qNorm.split(/\s+/).filter(Boolean);
  const pTokens = getSearchTokens(pNorm);

  for (const term of terms) {
    if (pTokens.some((t) => t === term)) {
      score += 25;
    } else if (pTokens.some((t) => t.startsWith(term))) {
      score += 15;
    }
  }

  const secondaryText = (otherValues.filter(Boolean) as string[])
    .map(normalizeSearchText)
    .join(" ");
  if (secondaryText.includes(qNorm)) {
    score += 10;
  }

  return score;
}
