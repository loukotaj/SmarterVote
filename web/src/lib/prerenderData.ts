import { candidateSlug } from "$lib/utils/format";
import type { Race, RaceSummary } from "$lib/types";

const DEFAULT_API_BASE = "https://races-api-dev-ddsvfazica-uc.a.run.app";

export function publicApiBase(): string {
  return import.meta.env.VITE_RACES_API_URL || DEFAULT_API_BASE;
}

export async function fetchPublishedRaceSummaries(fetchFn: typeof fetch = fetch): Promise<RaceSummary[]> {
  const res = await fetchFn(`${publicApiBase()}/races/summaries`);
  if (!res.ok) {
    throw new Error(`Failed to fetch race summaries: ${res.status}`);
  }
  return (await res.json()) as RaceSummary[];
}

export async function fetchPublishedRace(id: string, fetchFn: typeof fetch = fetch): Promise<Race> {
  const res = await fetchFn(`${publicApiBase()}/races/${encodeURIComponent(id)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch race ${id}: ${res.status}`);
  }
  return (await res.json()) as Race;
}

export async function raceEntries(): Promise<Array<{ slug: string }>> {
  const summaries = await fetchPublishedRaceSummaries();
  return summaries.map((race) => ({ slug: race.id }));
}

export async function candidateEntries(): Promise<Array<{ slug: string; candidate: string }>> {
  const summaries = await fetchPublishedRaceSummaries();
  const entries: Array<{ slug: string; candidate: string }> = [];
  for (const race of summaries) {
    for (const candidate of race.candidates ?? []) {
      entries.push({ slug: race.id, candidate: candidateSlug(candidate.name) });
    }
  }
  return entries;
}
