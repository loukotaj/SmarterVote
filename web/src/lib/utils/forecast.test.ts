import { describe, expect, it } from "vitest";
import type { RaceSummary } from "$lib/types";
import {
  aggregateForecasts,
  isRaceInForecastTab,
  officeGroup,
  parseForecastTab,
} from "./forecast";

const baseRace = {
  election_date: "2026-11-03",
  updated_utc: "2026-06-20T00:00:00Z",
  candidates: [],
};

describe("forecast utilities", () => {
  it("classifies race offices", () => {
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-senate-2026",
        office: "United States Senate",
      })
    ).toBe("senate");
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-governor-2026",
        office: "Governor of Georgia",
      })
    ).toBe("governors");
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-house-01-2026",
        office: "United States House",
      })
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
    expect(aggregate.projected.Democratic).toBe(35);
    expect(aggregate.projected.Republican).toBe(31);
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
});
