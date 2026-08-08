export const GOVERNOR_HOLDOVERS: Record<string, "Democratic" | "Republican"> = {
  Delaware: "Democratic",
  Kentucky: "Democratic",
  "North Carolina": "Democratic",
  "New Jersey": "Democratic",
  Washington: "Democratic",
  Virginia: "Democratic",
  Indiana: "Republican",
  Louisiana: "Republican",
  Mississippi: "Republican",
  Missouri: "Republican",
  Montana: "Republican",
  "North Dakota": "Republican",
  Utah: "Republican",
  "West Virginia": "Republican",
};

export const SENATE_HOLDOVERS: Record<string, ("Democratic" | "Republican")[]> =
  {
    // 15 States with no Senate races in 2026 (2 holdover seats each)
    Arizona: ["Democratic", "Democratic"],
    California: ["Democratic", "Democratic"],
    Connecticut: ["Democratic", "Democratic"],
    Hawaii: ["Democratic", "Democratic"],
    Indiana: ["Republican", "Republican"],
    Maryland: ["Democratic", "Democratic"],
    Missouri: ["Republican", "Republican"],
    Nevada: ["Democratic", "Democratic"],
    "New York": ["Democratic", "Democratic"],
    "North Dakota": ["Republican", "Republican"],
    Pennsylvania: ["Democratic", "Republican"],
    Utah: ["Republican", "Republican"],
    Vermont: ["Democratic", "Democratic"],
    Washington: ["Democratic", "Democratic"],
    Wisconsin: ["Democratic", "Republican"],

    // 2 States where both senators share the same party; race is in 2026 but listed here
    // so the non-contested holdover seat is counted when the race is active (1 seat counted),
    // or both seats are counted if no forecast exists (2 seats counted as baseline fallback).
    Virginia: ["Democratic", "Democratic"],
    "West Virginia": ["Republican", "Republican"],

    // 33 States with forecasted Senate races in 2026 (1 holdover seat each)
    Colorado: ["Democratic"],
    Delaware: ["Democratic"],
    Georgia: ["Democratic"],
    Illinois: ["Democratic"],
    Maine: ["Democratic"],
    Massachusetts: ["Democratic"],
    Michigan: ["Democratic"],
    Minnesota: ["Democratic"],
    "New Hampshire": ["Democratic"],
    "New Jersey": ["Democratic"],
    "New Mexico": ["Democratic"],
    Oregon: ["Democratic"],
    "Rhode Island": ["Democratic"],

    Alabama: ["Republican"],
    Alaska: ["Republican"],
    Arkansas: ["Republican"],
    Florida: ["Republican"],
    Idaho: ["Republican"],
    Iowa: ["Republican"],
    Kansas: ["Republican"],
    Kentucky: ["Republican"],
    Louisiana: ["Republican"],
    Mississippi: ["Republican"],
    Montana: ["Republican"],
    Nebraska: ["Republican"],
    "North Carolina": ["Republican"],
    Ohio: ["Republican"],
    Oklahoma: ["Republican"],
    "South Carolina": ["Republican"],
    "South Dakota": ["Republican"],
    Tennessee: ["Republican"],
    Texas: ["Republican"],
    Wyoming: ["Republican"],
  };

/**
 * Each chamber's composition going into this election, used as the baseline the
 * projection is compared against ("net change: D +3").
 *
 * This is cycle data and it moves with the holdover tables above: seats not up
 * this cycle carry over, so `composition − holdovers` is exactly the set of
 * seats on the ballot. Rolling the site to a new cycle means editing both, and
 * `holdovers.test.ts` fails if only one of them is updated.
 */
export const CURRENT_CHAMBER_COMPOSITION: Record<
  "house" | "senate" | "governors",
  Record<"Democratic" | "Republican" | "Other", number>
> = {
  house: { Democratic: 212, Republican: 218, Other: 1 },
  senate: { Democratic: 47, Republican: 53, Other: 0 },
  governors: { Democratic: 24, Republican: 26, Other: 0 },
};

/** Total seats in each chamber. */
export const CHAMBER_SEAT_TOTALS: Record<
  "house" | "senate" | "governors",
  number
> = {
  house: 435,
  senate: 100,
  governors: 50,
};

/**
 * Seats currently held by nobody, so that `CURRENT_CHAMBER_COMPOSITION` plus
 * these adds up to `CHAMBER_SEAT_TOTALS`.
 *
 * Recorded explicitly rather than left as the difference: a composition that
 * silently falls short of the chamber total looks identical to one where
 * somebody mistyped a party count, and the forecast page renders either without
 * complaint. Vacancies do move between elections — update this alongside the
 * composition above.
 */
export const CHAMBER_VACANCIES: Record<
  "house" | "senate" | "governors",
  number
> = {
  house: 4,
  senate: 0,
  governors: 0,
};
