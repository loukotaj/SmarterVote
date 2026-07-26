import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { RaceForecast, RaceSummary } from "$lib/types";
import ForecastKeyRaces from "./ForecastKeyRaces.svelte";

function forecast(overrides: Partial<RaceForecast> = {}): RaceForecast {
  return {
    party_probabilities: { Democratic: 0.4, Republican: 0.6 },
    rating: "tilt_r",
    confidence: "medium",
    rationale: "A close race in a swing district. Turnout will decide it.",
    based_on_poll_count: 3,
    generated_at: "2026-07-01T00:00:00Z",
    model: "test-model",
    source_urls: [],
    ...overrides,
  };
}

const race: RaceSummary = {
  id: "az-senate-2026",
  title: "2026 U.S. Senate election in Arizona",
  state: "Arizona",
  election_date: "2026-11-03",
  updated_utc: "2026-07-01T00:00:00Z",
  candidates: [],
  forecast: forecast({ win_probability: 0.58, margin_estimate: 2.4 }),
};

describe("ForecastKeyRaces", () => {
  afterEach(cleanup);

  it("renders nothing when there are no key races", () => {
    const { container } = render(ForecastKeyRaces, { races: [] });
    expect(container.querySelector("section")).toBeNull();
  });

  it("renders each race's rating, win probability and margin", () => {
    render(ForecastKeyRaces, { races: [race] });

    expect(screen.getByText("Races That Matter Most")).toBeTruthy();
    expect(screen.getByText("Arizona")).toBeTruthy();
    expect(screen.getByText("Tilt R")).toBeTruthy();
    expect(screen.getByText(/58% win/)).toBeTruthy();
    expect(screen.getByText(/\+2\.4% margin/)).toBeTruthy();
  });

  it("falls back to the first sentence of the rationale when no takeaway is set", () => {
    render(ForecastKeyRaces, { races: [race] });

    expect(screen.getByText("A close race in a swing district.")).toBeTruthy();
  });
});
