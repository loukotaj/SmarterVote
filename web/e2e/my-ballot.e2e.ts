import { test, expect } from "./support/test";
import {
  mockCensusGeocoder,
  mockCensusGeocoderError,
  mockRaceJson,
  mockSummaries,
} from "./support/network";
import { FIXTURE_SUMMARIES } from "./fixtures/summaries";
import { FIXTURE_RACE_IDS, ohSenateRace } from "./fixtures/races";
import {
  NO_RACES_CENSUS_RESPONSE,
  OHIO_DISTRICT_05_CENSUS_RESPONSE,
} from "./fixtures/census";

const SAMPLE_ADDRESS = "100 Fixture Ave, Columbus, OH 43215";

test.describe("my-ballot address lookup", () => {
  test.beforeEach(async ({ page }) => {
    await mockSummaries(page, FIXTURE_SUMMARIES);
  });

  test("finds and displays races matching the resolved district", async ({
    page,
  }) => {
    await mockCensusGeocoder(page, OHIO_DISTRICT_05_CENSUS_RESPONSE);
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto("/my-ballot/");

    await page.getByLabel("Home address").fill(SAMPLE_ADDRESS);
    await page.getByRole("button", { name: "Show my elections" }).click();

    await expect(
      page.getByRole("heading", { name: "Your election guide" }),
    ).toBeVisible();
    await expect(page.getByText("Ohio · U.S. House District 5")).toBeVisible();

    // Both matched races (statewide Senate + the district's House race) show
    // up as tabs in the ballot explorer.
    await expect(page.getByRole("tab", { name: "U.S. Senate" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "U.S. House" })).toBeVisible();

    // The default-selected race (Senate) loads its full comparison.
    await expect(
      page.getByText("Senator Jordan Ellsworth").first(),
    ).toBeVisible();
    await expect(page.getByText("Casey Whitfield").first()).toBeVisible();

    await page
      .getByRole("button", { name: "← Search another address" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Where are you registered to vote?" }),
    ).toBeVisible();
  });

  test("explains clearly when the district has no published guide yet", async ({
    page,
  }) => {
    await mockCensusGeocoder(page, NO_RACES_CENSUS_RESPONSE);
    await page.goto("/my-ballot/");

    await page.getByLabel("Home address").fill(SAMPLE_ADDRESS);
    await page.getByRole("button", { name: "Show my elections" }).click();

    await expect(
      page.getByRole("heading", { name: "Your election guide" }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "We identified your district, but no matching Smarter.Vote guide is available yet.",
      ),
    ).toBeVisible();
  });

  test("shows a friendly error when the geocoder is unreachable", async ({
    page,
  }) => {
    await mockCensusGeocoderError(page);
    await page.goto("/my-ballot/");

    await page.getByLabel("Home address").fill(SAMPLE_ADDRESS);
    await page.getByRole("button", { name: "Show my elections" }).click();

    await expect(
      page.getByText(/We couldn.t complete the lookup\./),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Your election guide" }),
    ).toHaveCount(0);
  });
});
