import type { RaceSummary } from "$lib/types";

/**
 * Keep directory and ballot payloads limited to fields their cards, filters,
 * and race picker use. Forecast rationale and pipeline metrics can dominate the
 * published summary index and do not belong in those pages' serialized data.
 */
export function toDirectoryRaceSummaries(races: RaceSummary[]): RaceSummary[] {
  return races.map((race) => ({
    id: race.id,
    title: race.title,
    office: race.office,
    jurisdiction: race.jurisdiction,
    state: race.state,
    contest_stage: race.contest_stage,
    election_date: race.election_date,
    updated_utc: race.updated_utc,
    candidates: race.candidates,
  }));
}

/** Remove internal pipeline cost metadata while preserving public forecasts. */
export function toForecastRaceSummaries(races: RaceSummary[]): RaceSummary[] {
  return races.map(({ agent_metrics: _agentMetrics, ...race }) => race);
}
