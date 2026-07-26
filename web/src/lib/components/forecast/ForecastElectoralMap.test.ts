import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ForecastElectoralMap from "./ForecastElectoralMap.svelte";

// USMap (rendered inside this component) fetches state boundary topology on
// mount; stub it out with an empty-but-valid topology so it mounts cleanly
// without a real network call.
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      json: async () => ({
        type: "Topology",
        objects: { states: { type: "GeometryCollection", geometries: [] } },
        arcs: [],
      }),
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

function baseProps() {
  return {
    activeStates: new Set<string>(),
    selectedState: null as string | null,
    stateRaceCounts: {},
    stateColors: {},
    stateTooltips: {},
    onStateClick: vi.fn(),
    onClearFilter: vi.fn(),
  };
}

describe("ForecastElectoralMap", () => {
  it("renders the map header and legend, including holdover swatches for non-house tabs", () => {
    render(ForecastElectoralMap, { activeTab: "senate", ...baseProps() });

    expect(screen.getByText("Electoral Map")).toBeTruthy();
    expect(screen.getByText("Safe D")).toBeTruthy();
    expect(screen.getByText("Safe R")).toBeTruthy();
    expect(screen.getByText("Dem Holdover")).toBeTruthy();
    expect(screen.getByText("GOP Holdover")).toBeTruthy();
    expect(screen.queryByText(/Clear Map Filter/)).toBeNull();
  });

  it("omits holdover legend entries for the house tab", () => {
    render(ForecastElectoralMap, { activeTab: "house", ...baseProps() });

    expect(screen.queryByText("Dem Holdover")).toBeNull();
    expect(screen.queryByText("GOP Holdover")).toBeNull();
  });

  it("shows a clear-filter button for the selected state and calls onClearFilter", async () => {
    const props = baseProps();
    render(ForecastElectoralMap, {
      activeTab: "house",
      ...props,
      selectedState: "Texas",
    });

    const button = screen.getByText(/Clear Map Filter: Texas/);
    await fireEvent.click(button);

    expect(props.onClearFilter).toHaveBeenCalledTimes(1);
  });
});
