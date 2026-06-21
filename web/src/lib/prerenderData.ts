import { candidateSlug } from "$lib/utils/format";
import type { Race, RaceSummary } from "$lib/types";

let summariesCache: Promise<RaceSummary[]> | null = null;
const raceCache = new Map<string, Promise<Race>>();

export function publicApiBase(): string {
  return import.meta.env.VITE_RACES_API_URL || "http://localhost:8080";
}

function publicDataBase(): string | undefined {
  return import.meta.env.VITE_PUBLIC_DATA_URL?.replace(/\/$/, "");
}

function shouldPrerenderDynamicRoutes(): boolean {
  return (
    import.meta.env.MODE === "crawl" ||
    import.meta.env.VITE_PRERENDER_RACES === "true"
  );
}

export async function fetchPublishedRaceSummaries(
  fetchFn: typeof fetch = fetch
): Promise<RaceSummary[]> {
  summariesCache ??= (async () => {
    const staticBase = publicDataBase();
    const url = staticBase
      ? `${staticBase}/summaries.json`
      : `${publicApiBase()}/races/summaries`;
    const res = await fetchFn(url);
    if (!res.ok) {
      throw new Error(`Failed to fetch race summaries: ${res.status}`);
    }
    return (await res.json()) as RaceSummary[];
  })();
  return summariesCache;
}

export async function fetchPublishedRace(
  id: string,
  fetchFn: typeof fetch = fetch
): Promise<Race> {
  const cached = raceCache.get(id);
  if (cached) return cached;

  const racePromise = (async () => {
    const staticBase = publicDataBase();
    const url = staticBase
      ? `${staticBase}/${encodeURIComponent(id)}.json`
      : `${publicApiBase()}/races/${encodeURIComponent(id)}`;
    const res = await fetchFn(url);
    if (!res.ok) {
      throw new Error(`Failed to fetch race ${id}: ${res.status}`);
    }
    return (await res.json()) as Race;
  })();
  raceCache.set(id, racePromise);
  return racePromise;
}

export async function raceEntries(): Promise<Array<{ slug: string }>> {
  if (!shouldPrerenderDynamicRoutes()) return [];
  const summaries = await fetchPublishedRaceSummaries().catch((error) => {
    console.warn("Skipping race prerender entries:", error);
    return [];
  });
  return summaries.map((race) => ({ slug: race.id }));
}

export async function candidateEntries(): Promise<
  Array<{ slug: string; candidate: string }>
> {
  if (!shouldPrerenderDynamicRoutes()) return [];
  const summaries = await fetchPublishedRaceSummaries().catch((error) => {
    console.warn("Skipping candidate prerender entries:", error);
    return [];
  });
  const entries: Array<{ slug: string; candidate: string }> = [];
  for (const race of summaries) {
    for (const candidate of race.candidates ?? []) {
      entries.push({ slug: race.id, candidate: candidateSlug(candidate.name) });
    }
  }
  return entries;
}
