import type { Race, RaceSummary, ChamberForecasts } from "./types";
import { sampleRaces } from "./sampleData";
import { logger } from "./utils/logger";
import { aggregateForecasts, type ForecastTab } from "./utils/forecast";
import { fetchWithAuth } from "$lib/stores/apiStore";
import { publicDataBase, racesApiBase } from "$lib/config/api";

const API_BASE = racesApiBase();
const USE_SAMPLE_FALLBACK = import.meta.env.DEV;

async function fetchPublicJson<T>(
  staticPath: string,
  apiPath: string,
  fetchFn: typeof fetch,
): Promise<T> {
  const dataBase = publicDataBase() || "";
  const url = dataBase ? `${dataBase}/${staticPath}` : `/${staticPath}`;
  const response = await fetchFn(url);
  if (!response.ok) {
    throw new Error(`Static data request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getRace(
  id: string,
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = USE_SAMPLE_FALLBACK,
): Promise<Race> {
  try {
    return await fetchPublicJson<Race>(
      `${encodeURIComponent(id)}.json`,
      `/races/${encodeURIComponent(id)}`,
      fetchFn,
    );
  } catch (error) {
    // If fallback is enabled and we have sample data for this race, use it
    if (useFallback && sampleRaces[id]) {
      logger.warn(
        `API request failed for race ${id}, falling back to sample data:`,
        error,
      );
      return sampleRaces[id];
    }

    // Unknown race IDs must fail explicitly. Showing an unrelated generic race
    // under a real slug is misleading and can be mistaken for published data.
    throw error;
  }
}

export async function getRaceSummaries(
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = USE_SAMPLE_FALLBACK,
): Promise<RaceSummary[]> {
  try {
    return await fetchPublicJson<RaceSummary[]>(
      "summaries.json",
      "/races/summaries",
      fetchFn,
    );
  } catch (error) {
    // If fallback is enabled, create summaries from sample races
    if (useFallback) {
      logger.warn(
        `API request failed for race summaries, falling back to sample data:`,
        error,
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

/**
 * Fetch draft race data from the races-api backend (admin-only, requires auth).
 * Used for admin preview of un-published races via ?draft=true query param.
 */
export async function getDraftRace(id: string): Promise<Race> {
  const res = await fetchWithAuth(
    `${API_BASE}/api/races/${encodeURIComponent(id)}/data?draft=true`,
    {},
    15000,
  );
  if (!res.ok) {
    throw new Error(`Failed to fetch draft race: ${res.status}`);
  }
  return (await res.json()) as Race;
}

export async function getChamberForecasts(
  fetchFn: typeof fetch = fetch,
  useFallback: boolean = USE_SAMPLE_FALLBACK,
): Promise<ChamberForecasts> {
  try {
    const forecasts = await fetchPublicJson<ChamberForecasts>(
      "chamber_forecasts.json",
      "/races/chamber_forecasts",
      fetchFn,
    );
    const summaries = await getRaceSummaries(fetchFn, false);
    return normalizeChamberForecasts(forecasts, summaries);
  } catch (error) {
    if (useFallback) {
      logger.warn(
        `API request failed for chamber forecasts, falling back to sample data:`,
        error,
      );
      return {
        house:
          "The Republican party is currently projected to maintain a narrow majority in the US House, though key suburban districts remain highly competitive.",
        senate:
          "Democrats face a challenging map but have key paths to holding their majority, with crucial toss-up races in key battleground states.",
        governors:
          "Gubernatorial contests are expected to largely favor incumbents, though open seats present critical opportunities for both parties to gain ground.",
        updated_at: new Date().toISOString(),
      };
    }
    throw error;
  }
}

function normalizeChamberForecasts(
  forecasts: ChamberForecasts,
  summaries: RaceSummary[],
): ChamberForecasts {
  if (forecasts.chambers) return forecasts;

  const chambers = Object.fromEntries(
    (["house", "senate", "governors"] as ForecastTab[]).map((tab) => {
      const aggregate = aggregateForecasts(summaries, tab);
      const controlParty =
        controlPartyFromProjected(aggregate.projected, aggregate.threshold) ||
        controlPartyFromNarrative(forecasts[tab]);
      const competitiveRaces = aggregate.races
        .filter((race) =>
          ["tossup", "tilt_d", "tilt_r", "lean_d", "lean_r"].includes(
            race.forecast.rating,
          ),
        )
        .map((race) => race.id);

      return [
        tab,
        {
          narrative: forecasts[tab],
          control_party: controlParty,
          control_probability:
            controlParty === "Other"
              ? 0
              : Math.min(
                  1,
                  (aggregate.projected[controlParty] ?? 0) /
                    aggregate.threshold,
                ),
          outcome_probabilities:
            controlParty === "Other" ? {} : { [controlParty]: 1 },
          projected_seats: aggregate.projected,
          expected_seats: aggregate.projected,
          threshold: aggregate.threshold,
          total_seats: aggregate.totalExpected,
          tossup_count: aggregate.ratingCounts.tossup ?? 0,
          competitive_race_count: competitiveRaces.length,
          competitive_races: competitiveRaces,
          method: "derived_from_race_summaries",
        },
      ];
    }),
  ) as NonNullable<ChamberForecasts["chambers"]>;

  return { ...forecasts, chambers };
}

function controlPartyFromProjected(
  projected: Record<string, number>,
  threshold: number,
): "Democratic" | "Republican" | null {
  if ((projected.Democratic ?? 0) >= threshold) return "Democratic";
  if ((projected.Republican ?? 0) >= threshold) return "Republican";
  return null;
}

function controlPartyFromNarrative(
  narrative: string,
): "Democratic" | "Republican" | "Other" {
  const normalized = narrative.toLowerCase();
  const republicanIndex = normalized.search(/republican|republicans|gop/);
  const democraticIndex = normalized.search(/democratic|democrats|democrat/);
  if (republicanIndex >= 0 && democraticIndex >= 0) {
    return republicanIndex < democraticIndex ? "Republican" : "Democratic";
  }
  if (republicanIndex >= 0) return "Republican";
  if (democraticIndex >= 0) return "Democratic";
  return "Other";
}
