import type { ForecastRating, RaceSummary } from "$lib/types";

export type ForecastTab = "house" | "senate" | "governors";

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

const SENATE_HOLDOVER_BASELINE = { Democratic: 34, Republican: 31, Other: 0 };
const GOVERNOR_NON_UP_BASELINE = { Democratic: 6, Republican: 8, Other: 0 };
const HOUSE_CURRENT_BASELINE = { Democratic: 212, Republican: 218, Other: 1 };

const EXPECTED_TOTALS: Record<ForecastTab, number> = {
  house: 435,
  senate: 100,
  governors: 50,
};

export function officeGroup(race: RaceSummary): ForecastTab | null {
  const office = (race.office || "").toLowerCase();
  if (office.includes("senate")) return "senate";
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
  if (tab === "senate") return { ...SENATE_HOLDOVER_BASELINE };
  if (tab === "governors") return { ...GOVERNOR_NON_UP_BASELINE };
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

export function aggregateForecasts(
  races: RaceSummary[],
  tab: ForecastTab
): ForecastAggregate {
  const label =
    tab === "house" ? "House" : tab === "senate" ? "Senate" : "Governors";
  const threshold = tab === "governors" ? 26 : tab === "senate" ? 51 : 218;
  const projected = baselineFor(tab);
  const current = currentBaselineFor(tab);
  const ratingCounts = emptyRatingCounts();
  const scoped = races.filter((race) => {
    if (officeGroup(race) !== tab) return false;
    if (tab === "governors" && !isValidGovernorControlRace(race)) return false;
    return true;
  });
  const forecasted: ForecastRace[] = [];
  const missingForecasts: RaceSummary[] = [];

  for (const race of scoped) {
    if (!race.forecast) {
      missingForecasts.push(race);
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
