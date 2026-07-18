import type { RaceSummary } from "$lib/types";

export interface ElectionGeography {
  state: string;
  congressionalDistrict: string;
}

interface CensusAddressMatch {
  geographies?: Record<string, Array<Record<string, unknown>>>;
}

interface CensusResponse {
  result?: { addressMatches?: CensusAddressMatch[] };
}

const CENSUS_ENDPOINT =
  "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress";

export function parseCensusGeography(
  response: CensusResponse,
): ElectionGeography | null {
  const match = response.result?.addressMatches?.[0];
  if (!match?.geographies) return null;

  const state = match.geographies.States?.[0]?.NAME;
  const congressionalEntry = Object.entries(match.geographies).find(([name]) =>
    name.endsWith("Congressional Districts"),
  )?.[1]?.[0];
  const district = congressionalEntry?.CD119 ?? congressionalEntry?.BASENAME;

  if (typeof state !== "string" || district == null) return null;
  const normalizedDistrict = String(district).padStart(2, "0");
  return {
    state,
    // Census uses 98 for non-voting delegate districts such as Washington,
    // D.C. Treat it like the other at-large districts throughout the UI and
    // race matcher rather than exposing the internal Census code to voters.
    congressionalDistrict:
      normalizedDistrict === "98" ? "00" : normalizedDistrict,
  };
}

export function lookupElectionGeography(
  address: string,
  timeoutMs = 12000,
): Promise<ElectionGeography> {
  return new Promise((resolve, reject) => {
    const callbackName = `smarterVoteCensus_${Date.now()}_${Math.random()
      .toString(36)
      .slice(2)}`;
    const script = document.createElement("script");
    const cleanup = () => {
      window.clearTimeout(timer);
      script.remove();
      delete (window as unknown as Record<string, unknown>)[callbackName];
    };
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("The address service took too long to respond."));
    }, timeoutMs);

    (window as unknown as Record<string, unknown>)[callbackName] = (
      response: CensusResponse,
    ) => {
      const geography = parseCensusGeography(response);
      cleanup();
      if (geography) resolve(geography);
      else reject(new Error("We could not match that address."));
    };
    script.onerror = () => {
      cleanup();
      reject(new Error("The address service is unavailable right now."));
    };

    const params = new URLSearchParams({
      address,
      benchmark: "Public_AR_Current",
      vintage: "Current_Current",
      format: "jsonp",
      callback: callbackName,
    });
    script.src = `${CENSUS_ENDPOINT}?${params.toString()}`;
    document.head.appendChild(script);
  });
}

function raceMatchesState(race: RaceSummary, state: string): boolean {
  const normalizedState = state.toLocaleLowerCase();
  if (race.state) {
    return race.state.toLocaleLowerCase() === normalizedState;
  }

  const jurisdiction = (race.jurisdiction || "").toLocaleLowerCase();
  return (
    jurisdiction === normalizedState ||
    jurisdiction.startsWith(`${normalizedState}'s `) ||
    jurisdiction.startsWith(`${normalizedState} `)
  );
}

function districtFromRace(race: RaceSummary): string | null {
  const text = `${race.jurisdiction ?? ""} ${race.title ?? ""}`;
  if (/\bat[- ]large\b/i.test(text)) return "00";
  const match = text.match(/(\d+)(?:st|nd|rd|th)? congressional district/i);
  return match ? match[1].padStart(2, "0") : null;
}

export function matchingNationalRaces(
  races: RaceSummary[],
  geography: ElectionGeography,
  now = new Date(),
): RaceSummary[] {
  const state = geography.state.toLocaleLowerCase();
  return races.filter((race) => {
    if (Date.parse(race.election_date) < now.getTime()) return false;
    const office = race.office?.toLocaleLowerCase() ?? "";
    const sameState = raceMatchesState(race, state);
    if (office.includes("president")) return true;
    if (office.includes("senate")) return sameState;
    if (office.includes("governor") || office.includes("gubernatorial"))
      return sameState;
    if (office.includes("house") || office.includes("representative")) {
      return (
        sameState && districtFromRace(race) === geography.congressionalDistrict
      );
    }
    return false;
  });
}
