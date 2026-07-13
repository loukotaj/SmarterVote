import type { Race, RaceSummary } from "$lib/types";

export interface HomepageMetrics {
  guides: number;
  candidateProfiles: number;
  statesRepresented: number;
  lastUpdated: string;
  snapshotDate: string;
}

export function nationalElectionRaces(races: RaceSummary[]): RaceSummary[] {
  return races.filter((race) => {
    const office = race.office?.toLocaleLowerCase() ?? "";
    return (
      office.includes("united states") ||
      office.includes("u.s.") ||
      office.includes("president") ||
      office.includes("governor") ||
      office.includes("gubernatorial")
    );
  });
}

export function rotateByDate<T>(items: T[], date: Date): T[] {
  if (!items.length) return [];
  const day = Math.floor(date.getTime() / 86_400_000);
  const offset = ((day % items.length) + items.length) % items.length;
  return [...items.slice(offset), ...items.slice(0, offset)];
}

export function recentlyUpdated(
  races: RaceSummary[],
  limit = 6
): RaceSummary[] {
  return [...races]
    .filter((race) => Boolean(race.id && race.updated_utc))
    .sort((a, b) => {
      const updated = Date.parse(b.updated_utc) - Date.parse(a.updated_utc);
      return updated || a.id.localeCompare(b.id);
    })
    .slice(0, limit);
}

export function homepageMetrics(
  races: RaceSummary[],
  snapshotDate: string
): HomepageMetrics | null {
  if (!races.length) return null;
  const timestamps = races
    .map((race) => Date.parse(race.updated_utc))
    .filter(Number.isFinite);
  if (!timestamps.length) return null;

  return {
    guides: races.length,
    candidateProfiles: races.reduce((count, race) => {
      const names = new Set(
        race.candidates
          .map((candidate) => candidate.name.trim().toLocaleLowerCase())
          .filter(Boolean)
      );
      return count + names.size;
    }, 0),
    statesRepresented: new Set(
      races.map((race) => race.state?.trim()).filter(Boolean)
    ).size,
    lastUpdated: new Date(Math.max(...timestamps)).toISOString(),
    snapshotDate,
  };
}

export function isPreviewEligible(race: Race, now = new Date()): boolean {
  const candidates = race.candidates.filter(
    (candidate) => !candidate.withdrawn
  );
  if (Date.parse(race.election_date) <= now.getTime()) return false;
  if (candidates.length < 2 || candidates.length > 3) return false;
  if (!race.validation_grade?.passed) return false;

  return candidates.slice(0, 2).every((candidate) => {
    const positions = Object.values(candidate.issues).filter(Boolean);
    if (!candidate.summary.trim() || positions.length < 6) return false;
    const sourced = positions.filter(
      (position) => position && position.sources.length > 0
    ).length;
    return (
      sourced / positions.length >= 0.8 &&
      positions.every(
        (position) =>
          position &&
          position.confidence !== "low" &&
          position.confidence !== "unknown"
      )
    );
  });
}
