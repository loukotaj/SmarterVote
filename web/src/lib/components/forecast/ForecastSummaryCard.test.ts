import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastSummaryCard from "./ForecastSummaryCard.svelte";

describe("ForecastSummaryCard", () => {
  afterEach(cleanup);

  it("composes the summary stats, control bar, seats bar and overview footer", () => {
    render(ForecastSummaryCard, {
      activeTab: "house",
      controlParty: "Democratic",
      controlProbability: 0.55,
      vpTiebreakParty: undefined,
      mostLikelyOutcome: { key: "220D - 215R", probability: 0.12 },
      tossupCount: 12,
      competitiveRaceCount: 30,
      outcomeProbabilities: { Democratic: 0.55, Republican: 0.45 },
      projectedSeats: { Democratic: 220, Republican: 214, Other: 1 },
      totalSeats: 435,
      threshold: 218,
      narrative: "A competitive cycle for the House.",
      updatedAt: "2026-06-01T00:00:00Z",
    });

    // Left column (ForecastSummaryStats)
    expect(screen.getByText("2026 House Election Summary")).toBeTruthy();
    // Right column top (ForecastControlBar)
    expect(screen.getByText("Chamber Control Probabilities")).toBeTruthy();
    // Right column bottom (ForecastSeatsBar)
    expect(screen.getByText("Majority (218)")).toBeTruthy();
    // Bottom row (ForecastOverviewFooter)
    expect(screen.getByText("A competitive cycle for the House.")).toBeTruthy();
  });
});
