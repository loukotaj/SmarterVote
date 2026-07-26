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
    render(ForecastHoldovers, { activeTab: "senate", holdovers });

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
    render(ForecastHoldovers, { activeTab: "governors", holdovers });
    expect(screen.getByText("Governor Seats Not Up in 2026")).toBeTruthy();
  });
});
