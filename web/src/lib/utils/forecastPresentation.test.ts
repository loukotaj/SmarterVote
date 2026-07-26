import { describe, expect, it } from "vitest";
import type { RaceSummary } from "$lib/types";
import {
  buildSeatOutcomeChart,
  buildStateMapData,
  getHostname,
  marketAsOf,
  marketSignalTarget,
  marketSpread,
  probability,
  summarizeStateForecast,
} from "./forecastPresentation";

describe("forecast presentation utilities", () => {
  it("builds a stable seat-outcome chart including an empty state", () => {
    const empty = buildSeatOutcomeChart({});
    expect(empty.outcomes).toEqual([]);
    expect(empty.svgData.tieX).toBe(150);

    const chart = buildSeatOutcomeChart({ "52D-48R": 0.6, "51D-49R": 0.4 }, 51);
    expect(chart.outcomes.map((outcome) => outcome.dSeats)).toEqual([52, 51]);
    expect(chart.maxProbability).toBe(0.6);
    expect(chart.svgData.fillPath).toContain("Z");
    expect(chart.svgData.tieX).toBe(15);
  });

  it("formats probabilities and market annotations", () => {
    expect(probability(null)).toBe("n/a");
    expect(probability(0)).toBe("<1%");
    expect(probability(1)).toBe(">99%");
    expect(probability(0.534)).toBe("53%");
    expect(
      marketSignalTarget({ matched_to: "Alice", matched_party: "D" }),
    ).toBe("Alice (D)");
    expect(marketSpread({ yes_bid: 0.48, yes_ask: 0.52 })).toBe(
      "48.0% bid / 52.0% ask",
    );
    expect(marketSpread({ yes_bid: null, yes_ask: 0.52 })).toBeNull();
    expect(marketAsOf("not-a-date")).toBe("");
  });

  it("selects the most competitive state race for map summaries", () => {
    const races: RaceSummary[] = [
      {
        id: "tx-house-01-2026",
        title: "Texas House 1",
        office: "U.S. House",
        election_date: "2026-11-03",
        updated_utc: "2026-07-01T00:00:00Z",
        candidates: [],
        forecast: {
          predicted_winner_party: "Republican",
          party_probabilities: { Republican: 0.8, Democratic: 0.2 },
          win_probability: 0.8,
          rating: "likely_r",
          confidence: "medium",
          rationale: "Clear advantage.",
          based_on_poll_count: 1,
          generated_at: "2026-07-01T00:00:00Z",
          model: "test",
          source_urls: [],
        },
      },
      {
        id: "tx-house-02-2026",
        title: "Texas House 2",
        office: "U.S. House",
        election_date: "2026-11-03",
        updated_utc: "2026-07-01T00:00:00Z",
        candidates: [],
        forecast: {
          predicted_winner_party: "Democratic",
          party_probabilities: { Republican: 0.49, Democratic: 0.51 },
          win_probability: 0.51,
          rating: "tossup",
          confidence: "low",
          rationale: "Close race.",
          based_on_poll_count: 1,
          generated_at: "2026-07-01T00:00:00Z",
          model: "test",
          source_urls: [],
        },
      },
    ];

    const summary = summarizeStateForecast(races);
    expect(summary.primary?.id).toBe("tx-house-02-2026");
    expect(summary.competitiveCount).toBe(1);
    expect(summary.details[0]).toContain("Toss-up");
  });

  it("extracts a hostname from a URL, without a leading www., and falls back on invalid input", () => {
    expect(getHostname("https://www.example.com/report")).toBe("example.com");
    expect(getHostname("not a url")).toBe("Source Link");
  });

  it("builds map colors and tooltips for governor holdovers and active races", () => {
    // Kentucky is intentionally absent from the race list: it's a holdover
    // (GOVERNOR_HOLDOVERS), with no 2026 race at all, so it should only be
    // populated by the holdover pass below, not the active-race pass.
    const races: RaceSummary[] = [
      {
        id: "tx-governor-2026",
        title: "Texas Governor",
        office: "Governor of Texas",
        state: "Texas",
        election_date: "2026-11-03",
        updated_utc: "2026-07-01T00:00:00Z",
        candidates: [],
        forecast: {
          predicted_winner_party: "Republican",
          party_probabilities: { Republican: 0.8, Democratic: 0.2 },
          win_probability: 0.8,
          margin_estimate: 12,
          rating: "safe_r",
          confidence: "high",
          rationale: "Strong Republican lean statewide.",
          based_on_poll_count: 2,
          generated_at: "2026-07-01T00:00:00Z",
          model: "test",
          source_urls: [],
        },
      },
    ];

    const { colors, tooltips } = buildStateMapData(races, "governors");

    // Kentucky is a holdover (no 2026 election) per GOVERNOR_HOLDOVERS
    expect(tooltips.Kentucky.subtitle).toBe("No election in 2026");
    expect(colors.Kentucky).toBe("var(--color-holdover-d)");

    // Texas has an active forecasted race
    expect(colors.Texas).toBe("var(--color-safe-r)");
    expect(tooltips.Texas.badge).toBe("Safe R");
    expect(tooltips.Texas.details?.[0]).toContain("Projected: Republican");
  });

  it("builds a tossup placeholder for house races without a forecast", () => {
    const races: RaceSummary[] = [
      {
        id: "ca-house-01-2026",
        title: "California House 1",
        office: "U.S. House",
        state: "California",
        election_date: "2026-11-03",
        updated_utc: "2026-07-01T00:00:00Z",
        candidates: [],
      },
    ];

    const { colors, tooltips } = buildStateMapData(races, "house");
    expect(colors.California).toBe("var(--color-tossup)");
    expect(tooltips.California.badge).toBe("0/1 Forecasted");
  });
});
