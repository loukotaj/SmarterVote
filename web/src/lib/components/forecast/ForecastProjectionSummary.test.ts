import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastProjectionSummary from "./ForecastProjectionSummary.svelte";

describe("ForecastProjectionSummary", () => {
  afterEach(cleanup);

  it("renders control label, seat totals, outcome probabilities, expected seats and net change", () => {
    render(ForecastProjectionSummary, {
      label: "Senate",
      controlParty: "Republican",
      threshold: 51,
      projectedSeats: { Democratic: 47, Republican: 53, Other: 0 },
      totalExpected: 100,
      outcomeProbabilities: { Democratic: 0.25, Republican: 0.75 },
      expectedSeats: { Democratic: 46.5, Republican: 53.5 },
      netChange: { Democratic: -1, Republican: 1, Other: 0 },
    });

    expect(screen.getByText("Senate Projected Seats")).toBeTruthy();
    expect(screen.getByText("Republican Control")).toBeTruthy();
    expect(screen.getByText("51 seats needed for majority")).toBeTruthy();
    expect(screen.getByText("Democrat: 47")).toBeTruthy();
    expect(screen.getByText("Republican: 53")).toBeTruthy();
    expect(screen.getByText("Total: 100")).toBeTruthy();
    expect(screen.getByText("75%")).toBeTruthy();
    expect(screen.getByText(/Expected seats: D 46\.5, R 53\.5/)).toBeTruthy();
    expect(screen.getByText("+1 net")).toBeTruthy();
    expect(screen.getByText("-1 net")).toBeTruthy();
  });

  it("shows 'No Clear Control' when the control party is Other", () => {
    render(ForecastProjectionSummary, {
      label: "Governors",
      controlParty: "Other",
      threshold: 26,
      projectedSeats: { Democratic: 25, Republican: 25, Other: 0 },
      totalExpected: 50,
      outcomeProbabilities: undefined,
      expectedSeats: undefined,
      netChange: { Democratic: 0, Republican: 0, Other: 0 },
    });

    expect(screen.getByText("No Clear Control")).toBeTruthy();
    expect(screen.queryByText(/Expected seats/)).toBeNull();
  });
});
