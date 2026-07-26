import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastControlBar from "./ForecastControlBar.svelte";

describe("ForecastControlBar", () => {
  afterEach(cleanup);

  it("renders the tie callout when a Senate 50-50 tie is not already the projection", () => {
    render(ForecastControlBar, {
      activeTab: "senate",
      outcomeProbabilities: {
        Democratic: 0.3,
        Republican: 0.6,
        tie_50_50: 0.1,
      },
      projectedSeats: { Democratic: 47, Republican: 53, Other: 0 },
    });

    expect(screen.getByText("50-50 Tie: 10%")).toBeTruthy();
    expect(screen.getByText(/Democratic 30%/)).toBeTruthy();
    expect(screen.getByText(/Republican 60%/)).toBeTruthy();
    expect(
      screen.getByText(/counted as Republican control via VP tie-break/),
    ).toBeTruthy();
  });

  it("omits the tie callout once the projection is already a 50-50 split", () => {
    render(ForecastControlBar, {
      activeTab: "senate",
      outcomeProbabilities: {
        Democratic: 0.45,
        Republican: 0.45,
        tie_50_50: 0.1,
      },
      projectedSeats: { Democratic: 50, Republican: 50, Other: 0 },
    });

    expect(
      screen.queryByText(/counted as Republican control via VP tie-break/),
    ).toBeNull();
  });

  it("uses the chamber label for governors and skips rendering when no data is available", () => {
    const { container } = render(ForecastControlBar, {
      activeTab: "governors",
      outcomeProbabilities: undefined,
      projectedSeats: { Democratic: 24, Republican: 26, Other: 0 },
    });

    expect(screen.getByText("Control Probabilities")).toBeTruthy();
    expect(container.querySelector(".h-8")).toBeNull();
  });
});
