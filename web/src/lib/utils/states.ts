export const STATE_NAMES_BY_CODE: Readonly<Record<string, string>> = {
  al: "Alabama",
  ak: "Alaska",
  az: "Arizona",
  ar: "Arkansas",
  ca: "California",
  co: "Colorado",
  ct: "Connecticut",
  de: "Delaware",
  fl: "Florida",
  ga: "Georgia",
  hi: "Hawaii",
  id: "Idaho",
  il: "Illinois",
  in: "Indiana",
  ia: "Iowa",
  ks: "Kansas",
  ky: "Kentucky",
  la: "Louisiana",
  me: "Maine",
  md: "Maryland",
  ma: "Massachusetts",
  mi: "Michigan",
  mn: "Minnesota",
  ms: "Mississippi",
  mo: "Missouri",
  mt: "Montana",
  ne: "Nebraska",
  nv: "Nevada",
  nh: "New Hampshire",
  nj: "New Jersey",
  nm: "New Mexico",
  ny: "New York",
  nc: "North Carolina",
  nd: "North Dakota",
  oh: "Ohio",
  ok: "Oklahoma",
  or: "Oregon",
  pa: "Pennsylvania",
  ri: "Rhode Island",
  sc: "South Carolina",
  sd: "South Dakota",
  tn: "Tennessee",
  tx: "Texas",
  ut: "Utah",
  vt: "Vermont",
  va: "Virginia",
  wa: "Washington",
  wv: "West Virginia",
  wi: "Wisconsin",
  wy: "Wyoming",
  dc: "District of Columbia",
};

const STATE_NAMES_BY_VALUE = new Map(
  Object.values(STATE_NAMES_BY_CODE).map((name) => [
    name.toLocaleLowerCase(),
    name,
  ]),
);

function canonicalStateValue(value: string | null | undefined): string | null {
  const normalized = value?.trim().toLocaleLowerCase();
  if (!normalized) return null;
  return (
    STATE_NAMES_BY_CODE[normalized] ??
    STATE_NAMES_BY_VALUE.get(normalized) ??
    null
  );
}

/**
 * Return a canonical state name for public filters and titles.
 *
 * Published summaries have historically contained abbreviations and, in a few
 * cases, district labels in the `state` field. Prefer recognized structured
 * values, then the stable state prefix in the race id, before exposing unknown
 * source text to voters.
 */
export function canonicalRaceState(race: {
  id?: string | null;
  state?: string | null;
  jurisdiction?: string | null;
}): string | null {
  const structured =
    canonicalStateValue(race.state) ?? canonicalStateValue(race.jurisdiction);
  if (structured) return structured;

  const idPrefix = race.id?.split("-", 1)[0]?.toLocaleLowerCase();
  if (idPrefix && STATE_NAMES_BY_CODE[idPrefix]) {
    return STATE_NAMES_BY_CODE[idPrefix];
  }

  return race.state?.trim() || race.jurisdiction?.trim() || null;
}
