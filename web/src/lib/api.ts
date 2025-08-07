import type { Race } from "./types";
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
