import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { RaceSummary } from "$lib/types";
import ForecastMissingRaces from "./ForecastMissingRaces.svelte";

describe("ForecastMissingRaces", () => {
  afterEach(cleanup);

  it("renders nothing when there are no missing races", () => {
    const { container } = render(ForecastMissingRaces, {
      races: [],
      activeTab: "house",
    });
    expect(container.querySelector("section")).toBeNull();
  });

  it("lists unforecasted races and resolves an incumbent-fallback party from the state", () => {
    const races: RaceSummary[] = [
      {
        id: "va-senate-2026",
        title: "2026 U.S. Senate election in Virginia",
        state: "Virginia",
        election_date: "2026-11-03",
        updated_utc: "2026-07-01T00:00:00Z",
        candidates: [],
      },
      {
        id: "unknown-senate-2026",
        title: "Unknown Senate Race",
        election_date: "2026-11-03",
        updated_utc: "2026-07-01T00:00:00Z",
        candidates: [],
      },
    ];

    render(ForecastMissingRaces, { races, activeTab: "senate" });

    expect(screen.getByText("Unforecasted Races (2)")).toBeTruthy();
    expect(
      screen.getByText("2026 U.S. Senate election in Virginia"),
    ).toBeTruthy();
    expect(screen.getByText(/Democratic \(Incumbent Fallback\)/)).toBeTruthy();
    expect(screen.getByText("Unknown")).toBeTruthy();
  });
});
