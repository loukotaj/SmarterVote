import { describe, expect, it } from "vitest";
import type { RaceSummary } from "$lib/types";
import {
  toDirectoryRaceSummaries,
  toForecastRaceSummaries,
} from "./publicRaceSummaries";

const summary: RaceSummary = {
  id: "tx-senate-2026",
  title: "Texas Senate",
  office: "U.S. Senate",
  jurisdiction: "Texas",
  state: "Texas",
  election_date: "2026-11-03",
  updated_utc: "2026-07-01T00:00:00Z",
  candidates: [{ name: "Alex Example", incumbent: false }],
  quality_grade: "A",
  agent_metrics: { estimated_usd: 1.23 },
  forecast: {
    rating: "tossup",
    party_probabilities: { Democratic: 0.5, Republican: 0.5 },
    confidence: "low",
    rationale: "A deliberately large forecast explanation.",
    based_on_poll_count: 0,
    generated_at: "2026-07-01T00:00:00Z",
    model: "example-model",
    source_urls: [],
    key_reasons: [],
    market_signals: [],
  },
};

describe("public race summary payloads", () => {
  it("omits forecast and internal metadata from directory payloads", () => {
    expect(toDirectoryRaceSummaries([summary])).toEqual([
      {
        id: summary.id,
        title: summary.title,
        office: summary.office,
        jurisdiction: summary.jurisdiction,
        state: summary.state,
        contest_stage: undefined,
        election_date: summary.election_date,
        updated_utc: summary.updated_utc,
        candidates: summary.candidates,
      },
    ]);
  });

  it("keeps forecasts but omits pipeline cost metadata on forecast pages", () => {
    const [race] = toForecastRaceSummaries([summary]);
    expect(race.forecast).toEqual(summary.forecast);
    expect(race).not.toHaveProperty("agent_metrics");
  });
});
