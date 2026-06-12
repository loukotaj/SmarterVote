import type { Race, RaceSummary } from "./types";
import { sampleRaces } from "./sampleData";
import { logger } from "./utils/logger";
import { fetchWithAuth } from "$lib/stores/apiStore";

const API_BASE = import.meta.env.VITE_RACES_API_URL || "http://localhost:8080";
const DATA_BASE = import.meta.env.VITE_PUBLIC_DATA_URL; // If set, pull statically from GCS (.json suffix)
const USE_SAMPLE_FALLBACK = import.meta.env.DEV;

export async function getRace(
  id: string,
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = USE_SAMPLE_FALLBACK
): Promise<Race> {
  try {
    const url = DATA_BASE ? `${DATA_BASE}/${id}.json` : `${API_BASE}/races/${id}`;
    const res = await fetchFn(url);
    if (!res.ok) {
      throw new Error(`Failed to fetch race: ${res.status}`);
    }
    return (await res.json()) as Race;
  } catch (error) {
    // If fallback is enabled and we have sample data for this race, use it
    if (useFallback && sampleRaces[id]) {
      logger.warn(
        `API request failed for race ${id}, falling back to sample data:`,
        error
      );
      return sampleRaces[id];
    }

    // If no specific sample data exists but fallback is enabled, use generic sample
    if (useFallback) {
      logger.warn(
        `API request failed for race ${id}, falling back to generic sample data:`,
        error
      );
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
  useFallback: boolean = USE_SAMPLE_FALLBACK
): Promise<RaceSummary[]> {
  try {
    const url = DATA_BASE ? `${DATA_BASE}/summaries.json` : `${API_BASE}/races/summaries`;
    const res = await fetchFn(url);
    if (!res.ok) {
      throw new Error(`Failed to fetch race summaries: ${res.status}`);
    }
    return (await res.json()) as RaceSummary[];
  } catch (error) {
    // If fallback is enabled, create summaries from sample races
    if (useFallback) {
      logger.warn(
        `API request failed for race summaries, falling back to sample data:`,
        error
      );
      return Object.values(sampleRaces).map((race) => ({
        id: race.id,
        title: race.title,
        office: race.office,
        jurisdiction: race.jurisdiction,
        state: race.state,
        election_date: race.election_date,
        updated_utc: race.updated_utc,
        candidates: race.candidates.map((candidate) => ({
          name: candidate.name,
          party: candidate.party,
          incumbent: candidate.incumbent,
          image_url: candidate.image_url,
        })),
      }));
    }

    // Re-throw the error if fallback is disabled
    throw error;
  }
}

// Keep the old function for backward compatibility but deprecated
export async function getAllRaces(
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = USE_SAMPLE_FALLBACK
): Promise<Race[]> {
  logger.warn("getAllRaces is deprecated, use getRaceSummaries instead");
  try {
    const url = DATA_BASE ? `${DATA_BASE}/summaries.json` : `${API_BASE}/races`;
    const res = await fetchFn(url);
    if (!res.ok) {
      throw new Error(`Failed to fetch races: ${res.status}`);
    }
    return (await res.json()) as Race[];
  } catch (error) {
    // If fallback is enabled, return all sample races
    if (useFallback) {
      logger.warn(
        `API request failed for all races, falling back to sample data:`,
        error
      );
      return Object.values(sampleRaces);
    }

    // Re-throw the error if fallback is disabled
    throw error;
  }
}

/**
 * Fetch draft race data from the races-api backend (admin-only, requires auth).
 * Used for admin preview of un-published races via ?draft=true query param.
 */
export async function getDraftRace(id: string): Promise<Race> {
  const res = await fetchWithAuth(`${API_BASE}/api/races/${encodeURIComponent(id)}/data?draft=true`, {}, 15000);
  if (!res.ok) {
    throw new Error(`Failed to fetch draft race: ${res.status}`);
  }
  return (await res.json()) as Race;
}
