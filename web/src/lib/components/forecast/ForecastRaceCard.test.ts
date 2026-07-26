import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ForecastRace } from "$lib/utils/forecast";
import ForecastRaceCard from "./ForecastRaceCard.svelte";

const race: ForecastRace = {
  id: "mi-senate-2026",
  title: "2026 U.S. Senate election in Michigan",
  state: "Michigan",
  election_date: "2026-11-03",
  updated_utc: "2026-07-01T00:00:00Z",
  candidates: [],
  forecast: {
    predicted_winner_name: "Jamie Rivera",
    predicted_winner_party: "Democratic",
    win_probability: 0.63,
    party_probabilities: { Democratic: 0.63, Republican: 0.37 },
    margin_estimate: 5.2,
    rating: "lean_d",
    confidence: "medium",
    rationale:
      "Rivera leads in most polling. Fundraising has also outpaced the opponent.",
    takeaway: "Rivera holds a mid-single-digit lead heading into the fall.",
    key_reasons: ["Polling advantage", "Fundraising edge"],
    uncertainty: "Late undecideds could tighten the race.",
    based_on_poll_count: 5,
    generated_at: "2026-07-01T00:00:00Z",
    model: "test-model",
    source_urls: ["https://example.com/poll-report"],
  },
};

describe("ForecastRaceCard", () => {
  afterEach(cleanup);

  it("renders the collapsed summary with rating, projected winner and metrics", () => {
    render(ForecastRaceCard, {
      race,
      isExpanded: false,
      onToggleExpand: vi.fn(),
    });

    expect(
      screen.getByText("2026 U.S. Senate election in Michigan"),
    ).toBeTruthy();
    expect(screen.getByText("Lean D")).toBeTruthy();
    expect(screen.getByText("Jamie Rivera")).toBeTruthy();
    expect(screen.getByText("63%")).toBeTruthy();
    expect(screen.getByText("+5.2%")).toBeTruthy();
    expect(
      screen.getByText(
        "Rivera holds a mid-single-digit lead heading into the fall.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Full Assessment")).toBeNull();
  });

  it("calls onToggleExpand when the expand button is clicked", async () => {
    const onToggleExpand = vi.fn();
    render(ForecastRaceCard, { race, isExpanded: false, onToggleExpand });

    await fireEvent.click(screen.getByText("Expand Analysis"));

    expect(onToggleExpand).toHaveBeenCalledTimes(1);
  });

  it("shows the full drawer content, including key drivers and sources, when expanded", () => {
    render(ForecastRaceCard, {
      race,
      isExpanded: true,
      onToggleExpand: vi.fn(),
    });

    expect(screen.getByText("Hide Analysis")).toBeTruthy();
    expect(screen.getByText("Full Assessment")).toBeTruthy();
    expect(screen.getByText("Polling advantage")).toBeTruthy();
    expect(
      screen.getByText("Late undecideds could tighten the race."),
    ).toBeTruthy();
    expect(screen.getByText(/example\.com/)).toBeTruthy();
  });
});
