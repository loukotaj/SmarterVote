import type { ForecastRating, RaceSummary } from "$lib/types";
import { GOVERNOR_HOLDOVERS, SENATE_HOLDOVERS } from "./holdovers";

export type ForecastTab = "house" | "senate" | "governors";

export const FORECAST_TABS: ForecastTab[] = ["house", "senate", "governors"];

export interface ForecastRace extends RaceSummary {
  forecast: NonNullable<RaceSummary["forecast"]>;
}

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

const HOUSE_CURRENT_BASELINE = { Democratic: 212, Republican: 218, Other: 1 };

const EXPECTED_TOTALS: Record<ForecastTab, number> = {
  house: 435,
  senate: 100,
  governors: 50,
};

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

export function officeGroup(race: RaceSummary): ForecastTab | null {
  const office = (race.office || "").toLowerCase();
  if (office.includes("state senate") || office.includes("state senator"))
    return null;
  if (office.includes("united states senate") || office.includes("u.s. senate"))
    return "senate";
  if (office.includes("governor") || office.includes("gubernatorial"))
    return "governors";
  if (office.includes("house") || office.includes("representative"))
    return "house";
  return null;
}

export function normalizeForecastParty(
  party?: string | null
): "Democratic" | "Republican" | "Other" {
  const value = (party || "").toLowerCase();
  if (value.includes("democrat") || value === "dfl") return "Democratic";
  if (value.includes("republican") || value === "gop") return "Republican";
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

function baselineFor(tab: ForecastTab): Record<string, number> {
  if (tab === "senate") return { Democratic: 34, Republican: 31, Other: 0 };
  if (tab === "governors") return { Democratic: 6, Republican: 8, Other: 0 };
  return { Democratic: 0, Republican: 0, Other: 0 };
}

function currentBaselineFor(tab: ForecastTab): Record<string, number> {
  if (tab === "senate") return { Democratic: 47, Republican: 53, Other: 0 };
  if (tab === "governors") return { Democratic: 24, Republican: 26, Other: 0 };
  return { ...HOUSE_CURRENT_BASELINE };
}

export function isValidGovernorControlRace(race: RaceSummary): boolean {
  return race.id !== "in-governor-2026";
}

export function isForecastTab(
  value: string | null | undefined
): value is ForecastTab {
  return !!value && (FORECAST_TABS as string[]).includes(value);
}

export function parseForecastTab(
  value: string | null | undefined
): ForecastTab {
  return isForecastTab(value) ? value : "house";
}

export function isRaceInForecastTab(
  race: RaceSummary,
  tab: ForecastTab
): boolean {
  if (officeGroup(race) !== tab) return false;
  if (tab === "governors" && !isValidGovernorControlRace(race)) return false;
  return true;
}

export function aggregateForecasts(
  races: RaceSummary[],
  tab: ForecastTab
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
    scoped.map(getRaceState).filter(Boolean) as string[]
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
  } else {
    const base = baselineFor(tab);
    for (const [party, count] of Object.entries(base)) {
      projected[party] = count;
    }
  }

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
    const party = normalizeForecastParty(race.forecast.predicted_winner_party);
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

      const counts = seatsToCount.reduce((acc, p) => {
        acc[p] = (acc[p] || 0) + 1;
        return acc;
      }, {} as Record<string, number>);

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
    totalExpected: EXPECTED_TOTALS[tab],
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
  tab: ForecastTab = "senate"
): GroupedSeatBucket[] {
  if (!dist) return [];

  const outcomes: SeatOutcome[] = Object.entries(dist).map(
    ([key, probability]) => {
      const { dSeats, rSeats } = parseSeatDistributionKey(key);
      return { key, probability, dSeats, rSeats };
    }
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
        label: "Near Tie (215-217)",
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
