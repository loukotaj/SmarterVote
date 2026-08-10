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
