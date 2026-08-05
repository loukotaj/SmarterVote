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
    market_signals: [],
    uncertainty: "Late undecideds could tighten the race.",
    based_on_poll_count: 5,
    generated_at: "2026-07-01T00:00:00Z",
    model: "test-model",
    source_urls: ["https://example.com/poll-report"],
  },
};

const withLineage: ForecastRace = {
  ...race,
  forecast: {
    ...race.forecast,
    evidence_lineage: [
      {
        claim:
          "Prediction markets imply roughly an 87% Democratic win probability in NV-3",
        source_url: "https://kalshi.com/markets/HOUSENV3-26-D",
        kind: "market",
        inferred: false,
      },
      {
        claim: "Finance input used by the forecast",
        source_url: "https://www.fec.gov/data/candidate/H6NV03204/",
        kind: "finance",
        inferred: true,
      },
    ],
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

  it("renders evidence lineage in the drawer, distinguishing inferred claims", () => {
    render(ForecastRaceCard, {
      race: withLineage,
      isExpanded: true,
      onToggleExpand: vi.fn(),
    });

    expect(screen.getByTestId("evidence-lineage")).toBeTruthy();
    expect(screen.getByText("2 claims - 1 inferred")).toBeTruthy();
    expect(
      screen.getByText(
        "Prediction markets imply roughly an 87% Democratic win probability in NV-3",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Finance input used by the forecast")).toBeTruthy();

    const stated = screen.getByText("Stated in source");
    const inferred = screen.getByText("Inferred");
    expect(stated.className).toContain("emerald");
    expect(inferred.className).toContain("amber");
    expect(stated.closest("li")?.className).not.toBe(
      inferred.closest("li")?.className,
    );

    const link = screen.getByText(/kalshi\.com/).closest("a");
    expect(link?.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link?.getAttribute("target")).toBe("_blank");
  });

  it("omits the lineage section when the forecast has none", () => {
    render(ForecastRaceCard, {
      race,
      isExpanded: true,
      onToggleExpand: vi.fn(),
    });
    expect(screen.queryByTestId("evidence-lineage")).toBeNull();
    expect(screen.queryByText("Evidence Lineage")).toBeNull();
    cleanup();

    render(ForecastRaceCard, {
      race: { ...race, forecast: { ...race.forecast, evidence_lineage: [] } },
      isExpanded: true,
      onToggleExpand: vi.fn(),
    });
    expect(screen.queryByTestId("evidence-lineage")).toBeNull();
  });

  it("keeps evidence lineage hidden until the drawer is expanded", () => {
    render(ForecastRaceCard, {
      race: withLineage,
      isExpanded: false,
      onToggleExpand: vi.fn(),
    });

    expect(screen.queryByTestId("evidence-lineage")).toBeNull();
  });
});
