import type { Race, RaceSummary } from "./types";
import { sampleRaces } from "./sampleData";

const API_BASE = import.meta.env.VITE_RACES_API_URL || "http://localhost:8080";

export async function getRace(
  id: string,
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = true
): Promise<Race> {
  try {
    const res = await fetchFn(`${API_BASE}/races/${id}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch race: ${res.status}`);
    }
    return (await res.json()) as Race;
  } catch (error) {
    // If fallback is enabled and we have sample data for this race, use it
    if (useFallback && sampleRaces[id]) {
      console.warn(`API request failed for race ${id}, falling back to sample data:`, error);
      return sampleRaces[id];
    }

    // If no specific sample data exists but fallback is enabled, use generic sample
    if (useFallback) {
      console.warn(`API request failed for race ${id}, falling back to generic sample data:`, error);
      return {
        ...sampleRaces["sample-race"],
        id,
        title: `Sample Race Data (${id})`,
      };
    }

    // Re-throw the error if fallback is disabled
    throw error;
  }
}

export async function getRaceSummaries(
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = true
): Promise<RaceSummary[]> {
  try {
    const res = await fetchFn(`${API_BASE}/races/summaries`);
    if (!res.ok) {
      throw new Error(`Failed to fetch race summaries: ${res.status}`);
    }
    return (await res.json()) as RaceSummary[];
  } catch (error) {
    // If fallback is enabled, create summaries from sample races
    if (useFallback) {
      console.warn(`API request failed for race summaries, falling back to sample data:`, error);
      return Object.values(sampleRaces).map(race => ({
        id: race.id,
        title: race.title,
        office: race.office,
        jurisdiction: race.jurisdiction,
        election_date: race.election_date,
        updated_utc: race.updated_utc,
        candidates: race.candidates.map(candidate => ({
          name: candidate.name,
          party: candidate.party,
          incumbent: candidate.incumbent
        }))
      }));
    }

    // Re-throw the error if fallback is disabled
    throw error;
  }
}

// Keep the old function for backward compatibility but deprecated
export async function getAllRaces(
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = true
): Promise<Race[]> {
  console.warn('getAllRaces is deprecated, use getRaceSummaries instead');
  try {
    const res = await fetchFn(`${API_BASE}/races`);
    if (!res.ok) {
      throw new Error(`Failed to fetch races: ${res.status}`);
    }
    return (await res.json()) as Race[];
  } catch (error) {
    // If fallback is enabled, return all sample races
    if (useFallback) {
      console.warn(`API request failed for all races, falling back to sample data:`, error);
      return Object.values(sampleRaces);
    }

    // Re-throw the error if fallback is disabled
    throw error;
  }
}
