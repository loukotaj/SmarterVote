import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastSeatOutcomeChart from "./ForecastSeatOutcomeChart.svelte";
import { buildSeatOutcomeChart } from "$lib/utils/forecastPresentation";
import { groupSeatDistribution } from "$lib/utils/forecast";

const distribution = { "51D - 49R": 0.4, "50D - 50R": 0.35, "49D - 51R": 0.25 };

function props() {
  const seatBuckets = groupSeatDistribution(distribution, "senate");
  const chart = buildSeatOutcomeChart(distribution, 51);
  return {
    seatBuckets,
    sortedOutcomes: chart.outcomes,
    maxProbability: chart.maxProbability,
    svgData: chart.svgData,
  };
}

describe("ForecastSeatOutcomeChart", () => {
  afterEach(cleanup);

  it("defaults to the grouped buckets view", () => {
    render(ForecastSeatOutcomeChart, props());

    expect(screen.getByText("Seat Outcome Distribution")).toBeTruthy();
    expect(screen.getAllByText("Tie (50-50)").length).toBeGreaterThan(0);
    expect(screen.getByText("35.0%")).toBeTruthy();
  });

  it("switches to the histogram view and shows individual outcomes", async () => {
    render(ForecastSeatOutcomeChart, props());

    await fireEvent.click(screen.getByText("Histogram"));

    expect(screen.getByText("51D - 49R")).toBeTruthy();
    expect(screen.getByText("40.0%")).toBeTruthy();
  });

  it("switches to the curve view and shows the seat-range axis labels", async () => {
    render(ForecastSeatOutcomeChart, props());

    await fireEvent.click(screen.getByText("Curve"));

    expect(screen.getByText("49D (Min)")).toBeTruthy();
    expect(screen.getByText("51D (Max)")).toBeTruthy();
    expect(screen.getByText("50-50 Tie Threshold")).toBeTruthy();
  });
});
