import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastOverviewFooter from "./ForecastOverviewFooter.svelte";

describe("ForecastOverviewFooter", () => {
  afterEach(cleanup);

  it("renders the narrative and last-updated date when provided", () => {
    render(ForecastOverviewFooter, {
      narrative: "Republicans are favored to hold the Senate.",
      updatedAt: "2026-07-01T00:00:00Z",
    });

    expect(
      screen.getByText("Republicans are favored to hold the Senate."),
    ).toBeTruthy();
    expect(screen.getByText("Last updated", { exact: false })).toBeTruthy();
  });

  it("falls back to a generic narrative and hides the updated line when absent", () => {
    render(ForecastOverviewFooter, {
      narrative: "",
      updatedAt: undefined,
    });

    expect(
      screen.getByText(
        "Projections indicate a highly competitive cycle for this chamber.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Last updated", { exact: false })).toBeNull();
  });
});
