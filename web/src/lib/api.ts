import type { Race, RaceSummary, ChamberForecasts } from "./types";
import { sampleRaces } from "./sampleData";
import { logger } from "./utils/logger";
import { fetchWithAuth } from "$lib/stores/apiStore";

const API_BASE = import.meta.env.VITE_RACES_API_URL || "http://localhost:8080";
const USE_SAMPLE_FALLBACK = import.meta.env.DEV;

function publicDataBase(): string | undefined {
  return import.meta.env.VITE_PUBLIC_DATA_URL;
}

async function fetchPublicJson<T>(
  staticPath: string,
  apiPath: string,
  fetchFn: typeof fetch
): Promise<T> {
  const dataBase = publicDataBase();
  if (dataBase) {
    const staticResponse = await fetchFn(`${dataBase}/${staticPath}`);
    if (!staticResponse.ok) {
      throw new Error(`Static data request failed: ${staticResponse.status}`);
    }
    return (await staticResponse.json()) as T;
  }

  const apiResponse = await fetchFn(`${API_BASE}${apiPath}`);
  if (!apiResponse.ok) {
    throw new Error(`API request failed: ${apiResponse.status}`);
  }
  return (await apiResponse.json()) as T;
}

export async function getRace(
  id: string,
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = USE_SAMPLE_FALLBACK
): Promise<Race> {
  try {
    return await fetchPublicJson<Race>(
      `${encodeURIComponent(id)}.json`,
      `/races/${encodeURIComponent(id)}`,
      fetchFn
    );
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
    return await fetchPublicJson<RaceSummary[]>(
      "summaries.json",
      "/races/summaries",
      fetchFn
    );
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
    return await fetchPublicJson<Race[]>(
      "summaries.json",
      "/races",
      fetchFn
    );
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

export async function getChamberForecasts(
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = USE_SAMPLE_FALLBACK
): Promise<ChamberForecasts> {
  try {
    return await fetchPublicJson<ChamberForecasts>(
      "chamber_forecasts.json",
      "/races/chamber_forecasts",
      fetchFn
    );
  } catch (error) {
    if (useFallback) {
      logger.warn(
        `API request failed for chamber forecasts, falling back to sample data:`,
        error
      );
      return {
        house: "The Republican party is currently projected to maintain a narrow majority in the US House, though key suburban districts remain highly competitive.",
        senate: "Democrats face a challenging map but have key paths to holding their majority, with crucial toss-up races in key battleground states.",
        governors: "Gubernatorial contests are expected to largely favor incumbents, though open seats present critical opportunities for both parties to gain ground.",
        updated_at: new Date().toISOString(),
      };
    }
    throw error;
  }
}
