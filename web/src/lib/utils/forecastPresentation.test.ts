import { describe, expect, it } from "vitest";
import type { RaceSummary } from "$lib/types";
import {
  buildSeatOutcomeChart,
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
          key_reasons: [],
          market_signals: [],
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
          key_reasons: [],
          market_signals: [],
        },
      },
    ];

    const summary = summarizeStateForecast(races);
    expect(summary.primary?.id).toBe("tx-house-02-2026");
    expect(summary.competitiveCount).toBe(1);
    expect(summary.details[0]).toContain("Toss-up");
  });
});
