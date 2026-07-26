import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastRatingsBreakdown from "./ForecastRatingsBreakdown.svelte";
import { FORECAST_RATING_ORDER } from "$lib/utils/forecast";

describe("ForecastRatingsBreakdown", () => {
  afterEach(cleanup);

  it("renders every partisan rating with its count, defaulting to zero when absent", () => {
    render(ForecastRatingsBreakdown, {
      ratingOrder: FORECAST_RATING_ORDER,
      ratingCounts: { tossup: 12, safe_d: 40 },
    });

    expect(screen.getByText("Forecast Ratings Breakdown")).toBeTruthy();
    expect(screen.getByText("Toss-up")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText("Safe D")).toBeTruthy();
    expect(screen.getByText("40")).toBeTruthy();
    // Rating with no entry in ratingCounts still renders as 0
    expect(screen.getByText("Lean D")).toBeTruthy();
  });
});
