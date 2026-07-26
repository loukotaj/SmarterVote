import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ForecastRace } from "$lib/utils/forecast";
import ForecastRaceList from "./ForecastRaceList.svelte";

function makeRace(
  id: string,
  rating: ForecastRace["forecast"]["rating"],
  party: "Democratic" | "Republican",
  state: string,
): ForecastRace {
  return {
    id,
    title: `${state} race ${id}`,
    state,
    election_date: "2026-11-03",
    updated_utc: "2026-07-01T00:00:00Z",
    candidates: [],
    forecast: {
      predicted_winner_party: party,
      win_probability: party === "Democratic" ? 0.6 : 0.55,
      party_probabilities:
        party === "Democratic"
          ? { Democratic: 0.6, Republican: 0.4 }
          : { Democratic: 0.45, Republican: 0.55 },
      rating,
      confidence: "medium",
      rationale: "Test rationale sentence. More detail follows.",
      based_on_poll_count: 2,
      generated_at: "2026-07-01T00:00:00Z",
      model: "test-model",
      source_urls: [],
    },
  };
}

const tossupDem = makeRace("r1", "tossup", "Democratic", "Nevada");
const safeRep = makeRace("r2", "safe_r", "Republican", "Alabama");

describe("ForecastRaceList", () => {
  afterEach(cleanup);

  it("filters races by rating and party pills", async () => {
    render(ForecastRaceList, {
      races: [tossupDem, safeRep],
      activeTab: "senate",
      selectedState: null,
      chamberSummary: undefined,
      onClearStateFilter: vi.fn(),
    });

    expect(screen.getByText("2 races")).toBeTruthy();
    expect(screen.getByText("Nevada race r1")).toBeTruthy();
    expect(screen.getByText("Alabama race r2")).toBeTruthy();

    await fireEvent.click(screen.getByText("Toss-ups"));

    expect(screen.getByText("1 races")).toBeTruthy();
    expect(screen.getByText("Nevada race r1")).toBeTruthy();
    expect(screen.queryByText("Alabama race r2")).toBeNull();
  });

  it("shows an empty state with a clear-filters action when nothing matches, and calls onClearStateFilter", async () => {
    const onClear = vi.fn();
    render(ForecastRaceList, {
      races: [tossupDem, safeRep],
      activeTab: "senate",
      selectedState: "Ohio",
      chamberSummary: undefined,
      onClearStateFilter: onClear,
    });

    expect(
      screen.getByText("No forecasts found matching the selected filters."),
    ).toBeTruthy();

    await fireEvent.click(screen.getByText("Clear all filters"));

    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("paginates beyond the initial 9 races via the Show More button", async () => {
    const races = Array.from({ length: 12 }, (_, i) =>
      makeRace(`race-${i}`, "tossup", "Democratic", `State${i}`),
    );

    render(ForecastRaceList, {
      races,
      activeTab: "senate",
      selectedState: null,
      chamberSummary: undefined,
      onClearStateFilter: vi.fn(),
    });

    expect(screen.getByText("State0 race race-0")).toBeTruthy();
    expect(screen.queryByText("State9 race race-9")).toBeNull();
    expect(screen.getByText(/Show More Races \(3 remaining\)/)).toBeTruthy();

    await fireEvent.click(screen.getByText(/Show More Races/));

    expect(screen.getByText("State9 race race-9")).toBeTruthy();
    expect(screen.queryByText(/Show More Races/)).toBeNull();
  });
});
