import { describe, expect, it } from "vitest";
import type { RaceSummary } from "$lib/types";
import {
  aggregateForecasts,
  isRaceInForecastTab,
  officeGroup,
  parseForecastTab,
  groupSeatDistribution,
  normalizeForecastParty,
} from "./forecast";

const baseRace = {
  election_date: "2026-11-03",
  updated_utc: "2026-06-20T00:00:00Z",
  candidates: [],
};

describe("forecast utilities", () => {
  it("normalizes forecast parties correctly including fallbacks", () => {
    expect(normalizeForecastParty("Democratic")).toBe("Democratic");
    expect(normalizeForecastParty("Republican")).toBe("Republican");

    // Null party with probabilities
    expect(
      normalizeForecastParty(null, { Democratic: 0.53, Republican: 0.47 }),
    ).toBe("Democratic");
    expect(
      normalizeForecastParty(null, { Democratic: 0.45, Republican: 0.55 }),
    ).toBe("Republican");

    // Null party with candidate incumbent fallback
    expect(
      normalizeForecastParty(null, null, [
        { name: "Alice", party: "Democratic", incumbent: true },
      ]),
    ).toBe("Democratic");
    expect(
      normalizeForecastParty(null, null, [
        { name: "Bob", party: "Republican", incumbent: true },
      ]),
    ).toBe("Republican");

    // No probabilities, no incumbent, should fallback to Other
    expect(normalizeForecastParty(null)).toBe("Other");
  });

  it("classifies race offices", () => {
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-senate-2026",
        office: "United States Senate",
      }),
    ).toBe("senate");
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-governor-2026",
        office: "Governor of Georgia",
      }),
    ).toBe("governors");
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-house-01-2026",
        office: "United States House",
      }),
    ).toBe("house");
  });

  it("parses URL tab parameters with a house default", () => {
    expect(parseForecastTab("senate")).toBe("senate");
    expect(parseForecastTab("governors")).toBe("governors");
    expect(parseForecastTab("bad-value")).toBe("house");
    expect(parseForecastTab(null)).toBe("house");
  });

  it("aggregates senate forecasts with holdover baseline", () => {
    const races: RaceSummary[] = [
      {
        ...baseRace,
        id: "ga-senate-2026",
        office: "United States Senate",
        forecast: {
          predicted_winner_name: "Alice",
          predicted_winner_party: "Democratic",
          win_probability: 0.57,
          party_probabilities: { Democratic: 0.57, Republican: 0.43 },
          margin_estimate: 1.2,
          rating: "tilt_d",
          confidence: "medium",
          rationale: "Narrow advantage.",
          based_on_poll_count: 1,
          generated_at: "2026-06-20T00:00:00Z",
          model: "openai/gpt-5.4",
          source_urls: [],
        },
      },
    ];

    const aggregate = aggregateForecasts(races, "senate");
    expect(aggregate.projected.Democratic).toBe(36);
    expect(aggregate.projected.Republican).toBe(32);
    expect(aggregate.ratingCounts.tilt_d).toBe(1);
  });

  it("excludes Indiana governor from 2026 governor control aggregation", () => {
    const races: RaceSummary[] = [
      {
        ...baseRace,
        id: "in-governor-2026",
        office: "Governor of Indiana",
        forecast: {
          predicted_winner_party: "Republican",
          party_probabilities: { Republican: 0.9 },
          rating: "safe_r",
          confidence: "low",
          rationale: "Invalid cycle fixture.",
          based_on_poll_count: 0,
          generated_at: "2026-06-20T00:00:00Z",
          model: "openai/gpt-5.4",
          source_urls: [],
        },
      },
    ];

    const aggregate = aggregateForecasts(races, "governors");
    expect(aggregate.races).toHaveLength(0);
    expect(aggregate.projected.Republican).toBe(8);
    expect(isRaceInForecastTab(races[0], "governors")).toBe(false);
  });

  it("groups seat distribution into buckets correctly", () => {
    const dist = {
      "54D-46R": 0.05,
      "53D-47R": 0.1,
      "52D-48R": 0.15,
      "51D-49R": 0.2,
      "50R-50D": 0.25,
      "51R-49D": 0.15,
      "52R-48D": 0.08,
      "53R-47D": 0.02,
    };
    const buckets = groupSeatDistribution(dist, "senate");
    expect(buckets).toHaveLength(5);

    // Strong D (53D+) should sum 54D and 53D: 0.05 + 0.10 = 0.15
    expect(buckets[0].label).toBe("Strong D (53D+)");
    expect(buckets[0].probability).toBe(0.15);

    // Narrow D (51-52D) should sum 52D and 51D: 0.15 + 0.20 = 0.35
    expect(buckets[1].label).toBe("Narrow D (51-52D)");
    expect(buckets[1].probability).toBe(0.35);

    // Tie (50-50): 0.25
    expect(buckets[2].label).toBe("Tie (50-50)");
    expect(buckets[2].probability).toBe(0.25);

    // Narrow R (51-52R) should sum 51R (49D) and 52R (48D): 0.15 + 0.08 = 0.23
    expect(buckets[3].label).toBe("Narrow R (51-52R)");
    expect(buckets[3].probability).toBe(0.23);

    // Strong R (53R+) should sum 53R (47D): 0.02
    expect(buckets[4].label).toBe("Strong R (53R+)");
    expect(buckets[4].probability).toBe(0.02);
  });

  it("uses House-specific distribution labels", () => {
    const buckets = groupSeatDistribution(
      {
        "218R-217D": 0.6,
        "223D-212R": 0.4,
      },
      "house",
    );

    expect(buckets[1].label).toBe("Narrow D (218-224D)");
    expect(buckets[1].probability).toBe(0.4);
    expect(buckets[2].label).toBe("Near Tie (212-217D)");
    expect(buckets[2].probability).toBe(0.6);
  });
});
