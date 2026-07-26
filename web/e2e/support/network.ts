import type { Page } from "@playwright/test";
import type { ChamberForecasts, Race, RaceSummary } from "../../src/lib/types";

/**
 * Stubs `summaries.json` (src/lib/prerenderData.ts / src/lib/api.ts), which
 * backs the elections directory, ballot lookup, forecast page, and homepage.
 * Playwright's route interception reaches this even though SvelteKit's
 * `+page.ts` load functions run during SSR on first navigation — the dev
 * server's self-fetch for relative URLs still goes through the page's
 * network stack, so a single `page.route` stub covers both SSR and any later
 * client-side re-fetch.
 */
export async function mockSummaries(
  page: Page,
  summaries: RaceSummary[],
): Promise<void> {
  await page.route("**/summaries.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(summaries),
    });
  });
}

/** Stubs `chamber_forecasts.json`, used only by the forecast page. */
export async function mockChamberForecasts(
  page: Page,
  forecasts: ChamberForecasts,
): Promise<void> {
  await page.route("**/chamber_forecasts.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(forecasts),
    });
  });
}

/**
 * Stubs the client-side race-detail fetch (`getRace`/`fetchPublishedRace` in
 * src/lib/api.ts and src/lib/prerenderData.ts) for a single race id, so race
 * detail, candidate detail, and compare specs get deterministic data instead
 * of falling back to the built-in sample data.
 */
export async function mockRaceJson(
  page: Page,
  raceId: string,
  race: Race,
): Promise<void> {
  await page.route(`**/${raceId}.json`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(race),
    });
  });
}

/** Forces the race JSON fetch to fail, so specs can exercise the error path. */
export async function mockRaceNotFound(
  page: Page,
  raceId: string,
): Promise<void> {
  await page.route(`**/${raceId}.json`, async (route) => {
    await route.fulfill({ status: 404, body: "not found" });
  });
}

/**
 * Stubs the Census geocoder JSONP endpoint used by the my-ballot address
 * lookup (src/lib/services/electionLookup.ts). The endpoint is called via a
 * dynamically inserted `<script>` tag rather than `fetch`, so the callback
 * name must be read from the request URL and invoked in the response body.
 */
export async function mockCensusGeocoder(
  page: Page,
  response: unknown,
): Promise<void> {
  await page.route(
    "**/geocoder/geographies/onelineaddress**",
    async (route) => {
      const url = new URL(route.request().url());
      const callback = url.searchParams.get("callback") ?? "callback";
      await route.fulfill({
        status: 200,
        contentType: "application/javascript",
        body: `${callback}(${JSON.stringify(response)});`,
      });
    },
  );
}

/** Simulates the Census geocoder being unreachable. */
export async function mockCensusGeocoderError(page: Page): Promise<void> {
  await page.route(
    "**/geocoder/geographies/onelineaddress**",
    async (route) => {
      await route.abort("failed");
    },
  );
}
