import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastSummaryStats from "./ForecastSummaryStats.svelte";

describe("ForecastSummaryStats", () => {
  afterEach(cleanup);

  it("renders the control badge, probability and most-likely-split stats", () => {
    render(ForecastSummaryStats, {
      activeTab: "senate",
      controlParty: "Republican",
      controlProbability: 0.72,
      vpTiebreakParty: "Republican",
      mostLikelyOutcome: { key: "51D - 49R", probability: 0.23 },
      tossupCount: 4,
      competitiveRaceCount: 9,
    });

    expect(screen.getByText("2026 Senate Election Summary")).toBeTruthy();
    expect(screen.getByText(/Republican control projected/)).toBeTruthy();
    expect(screen.getByText(/\(72%\)/)).toBeTruthy();
    expect(screen.getByText("Includes 50-50 tie-break via VP")).toBeTruthy();
    expect(screen.getByText("51D - 49R")).toBeTruthy();
    expect(screen.getByText(/23\.0% chance of this split/)).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByText(/9 competitive/)).toBeTruthy();
  });

  it("shows the 'no clear control' message when the control party is Other", () => {
    render(ForecastSummaryStats, {
      activeTab: "house",
      controlParty: "Other",
      controlProbability: undefined,
      vpTiebreakParty: undefined,
      mostLikelyOutcome: { key: "", probability: 0 },
      tossupCount: 0,
      competitiveRaceCount: 0,
    });

    expect(screen.getByText("No clear control projected")).toBeTruthy();
    expect(screen.queryByText("Includes 50-50 tie-break via VP")).toBeNull();
    expect(screen.getByText("—")).toBeTruthy();
  });
});
