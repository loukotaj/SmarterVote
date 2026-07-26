import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastSeatsBar from "./ForecastSeatsBar.svelte";

describe("ForecastSeatsBar", () => {
  afterEach(cleanup);

  it("renders the majority threshold and the Senate 50-50 marker", () => {
    render(ForecastSeatsBar, {
      activeTab: "senate",
      projectedSeats: { Democratic: 48, Republican: 52, Other: 0 },
      totalSeats: 100,
      threshold: 51,
    });

    expect(screen.getByText("Majority (51)")).toBeTruthy();
    expect(screen.getByText("50-50 Split")).toBeTruthy();
    expect(screen.getByText("R: 52")).toBeTruthy();
  });

  it("omits the Senate marker for other chambers", () => {
    render(ForecastSeatsBar, {
      activeTab: "house",
      projectedSeats: { Democratic: 210, Republican: 224, Other: 1 },
      totalSeats: 435,
      threshold: 218,
    });

    expect(screen.queryByText("50-50 Split")).toBeNull();
    expect(screen.getByText("Majority (218)")).toBeTruthy();
  });
});
