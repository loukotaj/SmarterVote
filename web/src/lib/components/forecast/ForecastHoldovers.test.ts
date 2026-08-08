import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastHoldovers from "./ForecastHoldovers.svelte";

const holdovers = [
  { state: "California", party: "Democratic" as const, count: 1 },
  { state: "Texas", party: "Republican" as const, count: 2 },
];

describe("ForecastHoldovers", () => {
  afterEach(cleanup);

  it("renders nothing for the house tab", () => {
    const { container } = render(ForecastHoldovers, {
      activeTab: "house",
      holdovers,
    });
    expect(container.querySelector("section")).toBeNull();
  });

  it("toggles the holdover list open and closed for senate/governors tabs", async () => {
    render(ForecastHoldovers, {
      activeTab: "senate",
      holdovers,
      cycleYear: "2026",
    });

    expect(screen.getByText("Senate Seats Not Up in 2026")).toBeTruthy();
    expect(screen.getByText(/2\s+seats/)).toBeTruthy();
    expect(screen.queryByText("California")).toBeNull();

    await fireEvent.click(screen.getByText("Show List v"));

    expect(screen.getByText("California")).toBeTruthy();
    expect(screen.getByText("Texas")).toBeTruthy();
    expect(screen.getByText("R x2")).toBeTruthy();

    await fireEvent.click(screen.getByText("Hide List ^"));
    expect(screen.queryByText("California")).toBeNull();
  });

  it("uses the governor-specific heading for the governors tab", () => {
    render(ForecastHoldovers, {
      activeTab: "governors",
      holdovers,
      cycleYear: "2026",
    });
    expect(screen.getByText("Governor Seats Not Up in 2026")).toBeTruthy();
  });

  it("says 'this cycle' rather than a wrong year when the races carry none", () => {
    // The year is derived from the races, so a catalog that cannot say which
    // cycle it describes must not fall back to a hardcoded one.
    render(ForecastHoldovers, {
      activeTab: "senate",
      holdovers,
      cycleYear: null,
    });
    expect(screen.getByText("Senate Seats Not Up in this cycle")).toBeTruthy();
  });
});
