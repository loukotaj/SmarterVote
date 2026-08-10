import type { Race, RaceSummary } from "$lib/types";

type TitleRace = Pick<Race | RaceSummary, "id"> &
  Partial<
    Pick<
      Race | RaceSummary,
      "title" | "office" | "state" | "jurisdiction" | "election_date"
    >
  > & { district?: string | null };

const STATE_NAMES: Record<string, string> = {
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

function cycleYear(race: TitleRace, parts: string[]): string | null {
  return (
    parts.find((part) => /^\d{4}$/.test(part)) ??
    race.election_date?.slice(0, 4) ??
    null
  );
}

function stateName(race: TitleRace, parts: string[]): string | null {
  return race.state?.trim() || STATE_NAMES[parts[0]] || null;
}

function ordinal(value: string): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  const mod100 = number % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${number}th`;
  return `${number}${["th", "st", "nd", "rd"][number % 10] ?? "th"}`;
}

function houseDistrict(
  race: TitleRace,
  parts: string[],
  year: string,
): string | null {
  if (!parts.includes("house")) return null;
  const districtLabel = `${race.district ?? ""} ${race.jurisdiction ?? ""}`;
  if (/\bat[- ]large\b/i.test(districtLabel)) return "At-Large";
  const labeledDistrict = districtLabel.match(
    /\b(\d+)(?:st|nd|rd|th)?\s+(?:Congressional\s+)?District\b/i,
  );
  if (labeledDistrict) return ordinal(labeledDistrict[1]);
  if (parts.includes("at") && parts.includes("large")) return "At-Large";
  const numericDistrict = parts.find(
    (part) => /^\d{1,3}$/.test(part) && part !== year,
  );
  return numericDistrict ? ordinal(numericDistrict) : "At-Large";
}

/** A concise, deterministic election name for every public-facing race surface. */
export function raceDisplayTitle(race: TitleRace): string {
  const parts = race.id.toLowerCase().split("-");
  const year = cycleYear(race, parts);
  const state = stateName(race, parts);
  const office = race.office?.toLowerCase() ?? "";
  const special = parts.includes("special") ? " Special" : "";

  if (year && state && office.includes("senate")) {
    return `${year} ${state} U.S. Senate${special} Election`;
  }
  if (
    year &&
    state &&
    (office.includes("house") || office.includes("representative"))
  ) {
    const district = houseDistrict(race, parts, year);
    if (district)
      return `${year} ${state}'s ${district} Congressional District${special} Election`;
  }
  if (
    year &&
    state &&
    (office.includes("governor") || office.includes("gubernatorial"))
  ) {
    if (office.includes("lieutenant governor")) {
      return `${year} ${state} Governor and Lieutenant Governor${special} Election`;
    }
    return `${year} ${state} Governor${special} Election`;
  }

  return race.title ?? race.office ?? "Election";
}

export function racePageTitle(race: TitleRace | null | undefined): string {
  if (!race) return "Loading... | Smarter.vote";
  return `${raceDisplayTitle(race)} | Smarter.vote`;
}

export function raceMetaDescription(
  race: TitleRace | null | undefined,
): string {
  const title = race ? raceDisplayTitle(race) : "this election";
  return `Compare candidates in the ${title} on the issues, with sourced research, polling, and race updates.`;
}
