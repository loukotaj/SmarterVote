import type {
  ChamberForecastDetails,
  ForecastRating,
  RaceSummary,
} from "$lib/types";
import {
  CHAMBER_SEAT_TOTALS,
  CURRENT_CHAMBER_COMPOSITION,
  GOVERNOR_HOLDOVERS,
  SENATE_HOLDOVERS,
} from "./holdovers";

export type ForecastTab = "house" | "senate" | "governors";

export const FORECAST_TABS: ForecastTab[] = ["house", "senate", "governors"];

export interface ForecastRace extends RaceSummary {
  forecast: NonNullable<RaceSummary["forecast"]>;
}

/** Partisan rating display order used for the ratings breakdown grid and race sorting (excludes "other"). */
export const FORECAST_RATING_ORDER: ForecastRating[] = [
  "safe_d",
  "likely_d",
  "lean_d",
  "tilt_d",
  "tossup",
  "tilt_r",
  "lean_r",
  "likely_r",
  "safe_r",
];

export interface ForecastAggregate {
  tab: ForecastTab;
  label: string;
  threshold: number;
  projected: Record<string, number>;
  baseline: Record<string, number>;
  netChange: Record<string, number>;
  ratingCounts: Record<ForecastRating, number>;
  races: ForecastRace[];
  missingForecasts: RaceSummary[];
  totalExpected: number;
  holdovers: {
    state: string;
    party: "Democratic" | "Republican" | "Other";
    count: number;
  }[];
}

const RATINGS: ForecastRating[] = [
  "safe_d",
  "likely_d",
  "lean_d",
  "tilt_d",
  "tossup",
  "tilt_r",
  "lean_r",
  "likely_r",
  "safe_r",
  "other",
];

const ABBR_TO_STATE: Record<string, string> = {
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
};

export function getRaceState(race: RaceSummary): string | null {
  if (race.state) return race.state;
  const id = race.id || "";
  const prefix = id.split("-")[0].toLowerCase();
  return ABBR_TO_STATE[prefix] || null;
}

export const INCUMBENT_FALLBACKS: Record<
  string,
  Record<string, "Democratic" | "Republican">
> = {
  governors: {
    Illinois: "Democratic",
    "New York": "Democratic",
    Vermont: "Republican",
    Wisconsin: "Democratic",
  },
  senate: {
    Virginia: "Democratic",
    "West Virginia": "Republican",
  },
  house: {},
};

// `office` is free text written by the research model, so the same chamber shows
// up as "U.S. Senate", "US Senate", "United States Senate", or bare "Senate".
// Match on the chamber word and rule out state legislatures separately, rather
// than requiring one exact federal spelling — anchoring on a spelling silently
// drops whole races from the forecast page. Mirrors `office_group` in
// `shared/forecast_summary.py`.
const STATE_LEGISLATIVE_OFFICE_MARKERS = [
  "state senate",
  "state senator",
  "state house",
  "state representative",
  "state assembly",
  "state legislature",
  "state legislative",
  "general assembly",
  "house of delegates",
];

export function officeGroup(race: RaceSummary): ForecastTab | null {
  const office = (race.office || "").toLowerCase();
  if (STATE_LEGISLATIVE_OFFICE_MARKERS.some((m) => office.includes(m)))
    return null;
  if (office.includes("senate") || office.includes("senator")) return "senate";
  if (office.includes("governor") || office.includes("gubernatorial"))
    return "governors";
  if (
    office.includes("house") ||
    office.includes("representative") ||
    office.includes("congress")
  )
    return "house";
  return null;
}

export function normalizeForecastParty(
  party?: string | null,
  probs?: Record<string, number> | null,
  candidates?:
    | {
        name?: string;
        party?: string;
        incumbent: boolean;
      }[]
    | null,
): "Democratic" | "Republican" | "Other" {
  const value = (party || "").toLowerCase();
  if (value.includes("democrat") || value === "dfl" || value === "d")
    return "Democratic";
  if (value.includes("republican") || value === "gop" || value === "r")
    return "Republican";

  // If party is not D or R (e.g. it is null, or empty, or Independent/Nonpartisan/Other),
  // but it's a D vs R race, check the win probabilities.
  if (probs) {
    const demProb = probs.Democratic ?? probs.Democrat ?? probs.D ?? 0;
    const repProb = probs.Republican ?? probs.GOP ?? probs.R ?? 0;
    if (demProb > repProb) return "Democratic";
    if (repProb > demProb) return "Republican";
  }

  // Fallback to candidates party count/incumbent
  if (candidates) {
    const incumbent = candidates.find((c) => c.incumbent);
    if (incumbent && incumbent.party) {
      const incParty = incumbent.party.toLowerCase();
      if (incParty.includes("democrat") || incParty === "d")
        return "Democratic";
      if (incParty.includes("republican") || incParty === "r")
        return "Republican";
    }
  }

  return "Other";
}

export function ratingSortValue(rating: ForecastRating): number {
  const order: Record<ForecastRating, number> = {
    tossup: 0,
    tilt_d: 1,
    tilt_r: 1,
    lean_d: 2,
    lean_r: 2,
    likely_d: 3,
    likely_r: 3,
    safe_d: 4,
    safe_r: 4,
    other: 5,
  };
  return order[rating] ?? 5;
}

function emptyRatingCounts(): Record<ForecastRating, number> {
  return Object.fromEntries(RATINGS.map((rating) => [rating, 0])) as Record<
    ForecastRating,
    number
  >;
}

function currentBaselineFor(tab: ForecastTab): Record<string, number> {
  return { ...CURRENT_CHAMBER_COMPOSITION[tab] };
}

/**
 * A governor race in a holdover state is not on this cycle's ballot — that
 * state's seat is already counted from GOVERNOR_HOLDOVERS, so counting the race
 * too would double-count the state. Deriving this from the holdover table keeps
 * it correct when the table rolls forward to the next cycle; naming individual
 * race IDs does not. Mirrors `is_chamber_control_race` in
 * `shared/forecast_summary.py`.
 */
export function isValidGovernorControlRace(race: RaceSummary): boolean {
  const state = getRaceState(race);
  return !state || !(state in GOVERNOR_HOLDOVERS);
}

export function isForecastTab(
  value: string | null | undefined,
): value is ForecastTab {
  return !!value && (FORECAST_TABS as string[]).includes(value);
}

export function parseForecastTab(
  value: string | null | undefined,
): ForecastTab {
  return isForecastTab(value) ? value : "house";
}

export function isRaceInForecastTab(
  race: RaceSummary,
  tab: ForecastTab,
): boolean {
  if (officeGroup(race) !== tab) return false;
  if (tab === "governors" && !isValidGovernorControlRace(race)) return false;
  return true;
}

export function aggregateForecasts(
  races: RaceSummary[],
  tab: ForecastTab,
): ForecastAggregate {
  const label =
    tab === "house" ? "House" : tab === "senate" ? "Senate" : "Governors";
  const threshold = tab === "governors" ? 26 : tab === "senate" ? 51 : 218;

  const projected: Record<string, number> = {
    Democratic: 0,
    Republican: 0,
    Other: 0,
  };
  const current = currentBaselineFor(tab);
  const ratingCounts = emptyRatingCounts();

  const scoped = races.filter((race) => isRaceInForecastTab(race, tab));

  const activeStates = new Set(
    scoped.map(getRaceState).filter(Boolean) as string[],
  );

  // Initialize baseline holdovers
  if (tab === "governors") {
    for (const party of Object.values(GOVERNOR_HOLDOVERS)) {
      projected[party] = (projected[party] ?? 0) + 1;
    }
  } else if (tab === "senate") {
    for (const [state, parties] of Object.entries(SENATE_HOLDOVERS)) {
      if (activeStates.has(state)) {
        if (parties.length > 0) {
          const party = parties[0];
          projected[party] = (projected[party] ?? 0) + 1;
        }
      } else {
        for (const party of parties) {
          projected[party] = (projected[party] ?? 0) + 1;
        }
      }
    }
  }
  // The House has no holdovers — every seat is up — so `projected` starts at zero
  // and is built entirely from the races themselves.

  const forecasted: ForecastRace[] = [];
  const missingForecasts: RaceSummary[] = [];

  for (const race of scoped) {
    if (!race.forecast) {
      missingForecasts.push(race);
      const stateName = getRaceState(race);
      const fallbackParty = stateName
        ? INCUMBENT_FALLBACKS[tab]?.[stateName]
        : undefined;
      if (fallbackParty) {
        projected[fallbackParty] = (projected[fallbackParty] ?? 0) + 1;
      }
      continue;
    }
    forecasted.push(race as ForecastRace);
    const party = normalizeForecastParty(
      race.forecast.predicted_winner_party,
      race.forecast.party_probabilities,
      race.candidates,
    );
    projected[party] = (projected[party] ?? 0) + 1;
    ratingCounts[race.forecast.rating] =
      (ratingCounts[race.forecast.rating] ?? 0) + 1;
  }

  forecasted.sort((a, b) => {
    const ratingDelta =
      ratingSortValue(a.forecast.rating) - ratingSortValue(b.forecast.rating);
    if (ratingDelta !== 0) return ratingDelta;
    return (
      (a.forecast.win_probability ?? 1) - (b.forecast.win_probability ?? 1)
    );
  });

  const holdoversList: {
    state: string;
    party: "Democratic" | "Republican" | "Other";
    count: number;
  }[] = [];
  if (tab === "governors") {
    for (const [state, party] of Object.entries(GOVERNOR_HOLDOVERS)) {
      holdoversList.push({
        state,
        party: party as "Democratic" | "Republican" | "Other",
        count: 1,
      });
    }
  } else if (tab === "senate") {
    for (const [state, parties] of Object.entries(SENATE_HOLDOVERS)) {
      const isStateActive = activeStates.has(state);
      const seatsToCount = isStateActive ? parties.slice(0, 1) : parties;

      const counts = seatsToCount.reduce(
        (acc, p) => {
          acc[p] = (acc[p] || 0) + 1;
          return acc;
        },
        {} as Record<string, number>,
      );

      for (const [party, count] of Object.entries(counts)) {
        holdoversList.push({
          state,
          party: party as "Democratic" | "Republican" | "Other",
          count,
        });
      }
    }
  }

  return {
    tab,
    label,
    threshold,
    projected,
    baseline: current,
    netChange: {
      Democratic: (projected.Democratic ?? 0) - (current.Democratic ?? 0),
      Republican: (projected.Republican ?? 0) - (current.Republican ?? 0),
      Other: (projected.Other ?? 0) - (current.Other ?? 0),
    },
    ratingCounts,
    races: forecasted,
    missingForecasts,
    totalExpected: CHAMBER_SEAT_TOTALS[tab],
    holdovers: holdoversList,
  };
}

export function formatRating(rating: ForecastRating): string {
  const labels: Record<ForecastRating, string> = {
    safe_d: "Safe D",
    likely_d: "Likely D",
    lean_d: "Lean D",
    tilt_d: "Tilt D",
    tossup: "Toss-up",
    tilt_r: "Tilt R",
    lean_r: "Lean R",
    likely_r: "Likely R",
    safe_r: "Safe R",
    other: "Other",
  };
  return labels[rating];
}

export function formatNet(value: number): string {
  if (value > 0) return `+${value}`;
  return String(value);
}

export interface SeatOutcome {
  key: string;
  probability: number;
  dSeats: number;
  rSeats: number;
}

export interface GroupedSeatBucket {
  label: string;
  probability: number;
  colorClass: string;
  outcomes: SeatOutcome[];
}

export function parseSeatDistributionKey(key: string): {
  dSeats: number;
  rSeats: number;
} {
  const matchD = key.match(/(\d+)D/);
  const matchR = key.match(/(\d+)R/);
  const dSeats = matchD ? parseInt(matchD[1], 10) : 50;
  const rSeats = matchR ? parseInt(matchR[1], 10) : 50;
  return { dSeats, rSeats };
}

export function groupSeatDistribution(
  dist: Record<string, number>,
  tab: ForecastTab = "senate",
): GroupedSeatBucket[] {
  if (!dist) return [];

  const outcomes: SeatOutcome[] = Object.entries(dist).map(
    ([key, probability]) => {
      const { dSeats, rSeats } = parseSeatDistributionKey(key);
      return { key, probability, dSeats, rSeats };
    },
  );

  outcomes.sort((a, b) => b.dSeats - a.dSeats);

  // Chamber-specific thresholds and labels
  type BucketDef = {
    label: string;
    colorClass: string;
    test: (o: SeatOutcome) => boolean;
  };

  let bucketDefs: BucketDef[];

  if (tab === "senate") {
    bucketDefs = [
      {
        label: "Strong D (53D+)",
        colorClass: "bg-blue-600 dark:bg-blue-700",
        test: (o) => o.dSeats >= 53,
      },
      {
        label: "Narrow D (51-52D)",
        colorClass: "bg-blue-400 dark:bg-blue-500",
        test: (o) => o.dSeats >= 51 && o.dSeats <= 52,
      },
      {
        label: "Tie (50-50)",
        colorClass: "bg-slate-400 dark:bg-slate-500",
        test: (o) => o.dSeats === 50,
      },
      {
        label: "Narrow R (51-52R)",
        colorClass: "bg-red-400 dark:bg-red-500",
        test: (o) => o.rSeats >= 51 && o.rSeats <= 52,
      },
      {
        label: "Strong R (53R+)",
        colorClass: "bg-red-600 dark:bg-red-700",
        test: (o) => o.rSeats >= 53,
      },
    ];
  } else if (tab === "governors") {
    bucketDefs = [
      {
        label: "Strong D (28D+)",
        colorClass: "bg-blue-600 dark:bg-blue-700",
        test: (o) => o.dSeats >= 28,
      },
      {
        label: "Narrow D (26-27D)",
        colorClass: "bg-blue-400 dark:bg-blue-500",
        test: (o) => o.dSeats >= 26 && o.dSeats <= 27,
      },
      {
        label: "Tie (25-25)",
        colorClass: "bg-slate-400 dark:bg-slate-500",
        test: (o) => o.dSeats === 25,
      },
      {
        label: "Narrow R (26-27R)",
        colorClass: "bg-red-400 dark:bg-red-500",
        test: (o) => o.rSeats >= 26 && o.rSeats <= 27,
      },
      {
        label: "Strong R (28R+)",
        colorClass: "bg-red-600 dark:bg-red-700",
        test: (o) => o.rSeats >= 28,
      },
    ];
  } else {
    // house
    bucketDefs = [
      {
        label: "Strong D (225D+)",
        colorClass: "bg-blue-600 dark:bg-blue-700",
        test: (o) => o.dSeats >= 225,
      },
      {
        label: "Narrow D (218-224D)",
        colorClass: "bg-blue-400 dark:bg-blue-500",
        test: (o) => o.dSeats >= 218 && o.dSeats <= 224,
      },
      {
        label: "Near Tie (212-217D)",
        colorClass: "bg-slate-400 dark:bg-slate-500",
        test: (o) => o.dSeats >= 212 && o.dSeats <= 217,
      },
      {
        label: "Narrow R (218-224R)",
        colorClass: "bg-red-400 dark:bg-red-500",
        test: (o) => o.rSeats >= 218 && o.rSeats <= 224,
      },
      {
        label: "Strong R (225R+)",
        colorClass: "bg-red-600 dark:bg-red-700",
        test: (o) => o.rSeats >= 225,
      },
    ];
  }

  const buckets: GroupedSeatBucket[] = bucketDefs.map((def) => ({
    label: def.label,
    probability: 0,
    colorClass: def.colorClass,
    outcomes: [],
  }));

  for (const outcome of outcomes) {
    const idx = bucketDefs.findIndex((def) => def.test(outcome));
    if (idx >= 0) {
      buckets[idx].probability += outcome.probability;
      buckets[idx].outcomes.push(outcome);
    }
  }

  buckets.forEach((b) => {
    b.probability = Math.round(b.probability * 10000) / 10000;
  });

  return buckets;
}

export function raceHref(id: string): string {
  return `/races/${id}`;
}

/** Most likely single outcome (e.g. "51D - 49R") from a seat distribution. */
export function getMostLikelySeatOutcome(dist: Record<string, number> = {}): {
  key: string;
  probability: number;
} {
  let best = { key: "", probability: 0 };
  for (const [key, prob] of Object.entries(dist)) {
    if (prob > best.probability) best = { key, probability: prob };
  }
  return best;
}

/**
 * Resolves the projected controlling party for a chamber, preferring the
 * chamber forecast summary's own determination and falling back to the
 * aggregate seat projection (with a Senate 50-50 VP tie-break to Republican).
 */
export function resolveControlParty(
  tab: ForecastTab,
  chamberSummary: ChamberForecastDetails | undefined,
  aggregate: ForecastAggregate,
): "Democratic" | "Republican" | "Other" {
  if (chamberSummary?.control_party) return chamberSummary.control_party;

  if (
    tab === "senate" &&
    (aggregate.projected.Democratic ?? 0) === 50 &&
    (aggregate.projected.Republican ?? 0) === 50
  ) {
    return "Republican";
  }
  if ((aggregate.projected.Democratic ?? 0) >= aggregate.threshold) {
    return "Democratic";
  }
  if ((aggregate.projected.Republican ?? 0) >= aggregate.threshold) {
    return "Republican";
  }
  return "Other";
}

/**
 * Ranks a race by how likely it is to matter for chamber control: named
 * "competitive races" from the chamber summary first, then by closeness of
 * the rating/win probability. Lower scores sort first (most relevant).
 */
export function getControlRelevanceScore(
  race: RaceSummary,
  chamberSummary: ChamberForecastDetails | undefined,
): number {
  const title = race.title || "";
  const id = race.id || "";
  const isKey = chamberSummary?.competitive_races?.some(
    (t) => t === title || title.includes(t) || id.includes(t),
  );

  let ratingPriority = 4;
  if (race.forecast) {
    const r = race.forecast.rating.toLowerCase();
    if (r.includes("tossup") || r.includes("toss-up")) {
      ratingPriority = 0;
    } else if (r.includes("tilt")) {
      ratingPriority = 1;
    } else if (r.includes("lean")) {
      ratingPriority = 2;
    } else if (r.includes("likely")) {
      ratingPriority = 3;
    } else if (r.includes("safe")) {
      ratingPriority = 4;
    }
  }

  const winProb = race.forecast?.win_probability ?? 0.5;
  const closeness = Math.abs(winProb - 0.5);

  const keyWeight = isKey ? 0 : 1000;
  const ratingWeight = ratingPriority * 100;
  const closenessWeight = closeness * 10;

  return keyWeight + ratingWeight + closenessWeight;
}

export type ForecastRaceSortBy =
  | "control_relevance"
  | "competitiveness"
  | "dem_pickup"
  | "gop_pickup"
  | "probability"
  | "margin"
  | "state"
  | "rating";

/** Pure sort of forecasted races per the "Sort by" dropdown on the forecast page. */
export function sortForecastRaces(
  races: ForecastRace[],
  sortBy: ForecastRaceSortBy | string,
  chamberSummary: ChamberForecastDetails | undefined,
): ForecastRace[] {
  const sorted = [...races];
  sorted.sort((a, b) => {
    if (sortBy === "state") {
      const stateA = getRaceState(a) || "";
      const stateB = getRaceState(b) || "";
      return stateA.localeCompare(stateB);
    }
    if (sortBy === "rating") {
      const indexA = FORECAST_RATING_ORDER.indexOf(a.forecast.rating);
      const indexB = FORECAST_RATING_ORDER.indexOf(b.forecast.rating);
      return indexA - indexB;
    }
    if (sortBy === "probability") {
      const probA = a.forecast.win_probability ?? 0;
      const probB = b.forecast.win_probability ?? 0;
      return probB - probA;
    }
    if (sortBy === "margin") {
      const marginA = Math.abs(a.forecast.margin_estimate ?? 0);
      const marginB = Math.abs(b.forecast.margin_estimate ?? 0);
      return marginB - marginA;
    }
    if (sortBy === "dem_pickup") {
      const demProbA = a.forecast.party_probabilities?.Democratic ?? 0;
      const demProbB = b.forecast.party_probabilities?.Democratic ?? 0;
      return demProbB - demProbA;
    }
    if (sortBy === "gop_pickup") {
      const gopProbA = a.forecast.party_probabilities?.Republican ?? 0;
      const gopProbB = b.forecast.party_probabilities?.Republican ?? 0;
      return gopProbB - gopProbA;
    }
    if (sortBy === "competitiveness") {
      const diffA = Math.abs((a.forecast.win_probability ?? 0.5) - 0.5);
      const diffB = Math.abs((b.forecast.win_probability ?? 0.5) - 0.5);
      return diffA - diffB;
    }
    return (
      getControlRelevanceScore(a, chamberSummary) -
      getControlRelevanceScore(b, chamberSummary)
    );
  });
  return sorted;
}

export interface ForecastRaceFilterOptions {
  selectedState: string | null;
  filterRating: string;
  filterParty: string;
}

/** Pure filter of forecasted races per the state map selection and filter pills. */
export function filterForecastRaces(
  races: ForecastRace[],
  { selectedState, filterRating, filterParty }: ForecastRaceFilterOptions,
): ForecastRace[] {
  return races.filter((race) => {
    if (selectedState && getRaceState(race) !== selectedState) return false;

    if (filterRating !== "all") {
      const rating = race.forecast.rating.toLowerCase();
      if (filterRating === "tossup" && !rating.includes("tossup")) return false;
      if (filterRating === "tilt" && !rating.startsWith("tilt_")) return false;
      if (filterRating === "lean" && !rating.startsWith("lean_")) return false;
      if (
        filterRating === "likely_safe" &&
        !rating.startsWith("likely_") &&
        !rating.startsWith("safe_")
      )
        return false;
    }
    if (filterParty !== "all") {
      const party = normalizeForecastParty(
        race.forecast.predicted_winner_party,
        race.forecast.party_probabilities,
        race.candidates,
      );
      if (filterParty !== party) return false;
    }

    return true;
  });
}
