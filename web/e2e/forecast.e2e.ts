import { test, expect } from "./support/test";
import {
  mockChamberForecasts,
  mockRaceJson,
  mockSummaries,
} from "./support/network";
import {
  FIXTURE_CHAMBER_FORECASTS,
  FIXTURE_SUMMARIES,
} from "./fixtures/summaries";
import { FIXTURE_RACE_IDS, ohSenateRace } from "./fixtures/races";
import { gotoAndSettle } from "./support/interactions";

test.describe("forecast page", () => {
  test.beforeEach(async ({ page }) => {
    await mockSummaries(page, FIXTURE_SUMMARIES);
    await mockChamberForecasts(page, FIXTURE_CHAMBER_FORECASTS);
  });

  test("shows the House forecast by default", async ({ page }) => {
    await gotoAndSettle(page, "/forecast/");

    await expect(
      page.getByRole("heading", { name: "2026 Election Forecast" }),
    ).toBeVisible();
    await expect(
      page.getByText("Republican control projected").first(),
    ).toBeVisible();
    await expect(
      page.getByText(/House control is a nailbiter/).first(),
    ).toBeVisible();
  });

  test("switching tabs shows the Senate and Governors forecasts", async ({
    page,
  }) => {
    await gotoAndSettle(page, "/forecast/");

    await page.getByRole("button", { name: "Senate", exact: true }).click();
    await expect(page).toHaveURL(/tab=senate/);
    await expect(
      page.getByText(/Democrats have a narrow but real path/).first(),
    ).toBeVisible();
    await expect(page.getByText("Ohio U.S. Senate Race 2026")).toBeVisible();
    await expect(page.getByText("Toss-up").first()).toBeVisible();

    await page.getByRole("button", { name: "Governors", exact: true }).click();
    await expect(page).toHaveURL(/tab=governors/);
    await expect(page.getByText("Nevada Governor Race 2026")).toBeVisible();
    await expect(page.getByText("Likely D").first()).toBeVisible();
  });

  test("filtering to a rating with no matches shows a graceful empty state", async ({
    page,
  }) => {
    await gotoAndSettle(page, "/forecast/?tab=governors");
    await expect(page.getByText("Nevada Governor Race 2026")).toBeVisible();

    await page.getByRole("button", { name: "Toss-ups" }).click();

    await expect(
      page.getByText("No forecasts found matching the selected filters."),
    ).toBeVisible();
    await page.getByRole("button", { name: "Clear all filters" }).click();
    await expect(page.getByText("Nevada Governor Race 2026")).toBeVisible();
  });

  test("opening a race's details navigates to its detail page", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await gotoAndSettle(page, "/forecast/?tab=senate");

    await page
      .getByRole("link", { name: "Ohio U.S. Senate Race 2026" })
      .click();

    await expect(
      page.getByRole("heading", { name: "Ohio U.S. Senate Race 2026" }),
    ).toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(`/races/${FIXTURE_RACE_IDS.senate}/?$`),
    );
  });
});
