import { test, expect } from "./support/test";
import { mockRaceJson, mockSummaries } from "./support/network";
import { FIXTURE_SUMMARIES } from "./fixtures/summaries";
import { FIXTURE_RACE_IDS, ohSenateRace } from "./fixtures/races";
import { gotoAndSettle } from "./support/interactions";

test.describe("elections directory", () => {
  test.beforeEach(async ({ page }) => {
    await mockSummaries(page, FIXTURE_SUMMARIES);
  });

  test("lists all published national races by default", async ({ page }) => {
    await gotoAndSettle(page, "/elections/");

    await expect(
      page.getByRole("heading", { name: "Explore elections." }),
    ).toBeVisible();
    await expect(page.getByText("Showing 4 of 4 races").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Ohio U.S. Senate Race 2026" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Nevada Governor Race 2026" }),
    ).toBeVisible();
  });

  test("a shared search URL filters down to the matching race", async ({
    page,
  }) => {
    // The directory's search box writes its query to `?q=`, making a search
    // a shareable/bookmarkable link — exercise that contract directly rather
    // than simulating keystrokes, which races the debounce timer under this
    // dev server's slower first-paint.
    await gotoAndSettle(page, "/elections/?q=Whitfield");

    await expect(page.getByText("1 race found").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Ohio U.S. Senate Race 2026" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Nevada Governor Race 2026" }),
    ).toHaveCount(0);

    // The hero search box reflects the active query from the URL.
    await expect(
      page.getByPlaceholder("Search by candidate name, office, or state..."),
    ).toHaveValue("Whitfield");
  });

  test("filtering by office narrows results and the count updates", async ({
    page,
  }) => {
    await gotoAndSettle(page, "/elections/");

    await page.getByRole("button", { name: "Governor", exact: true }).click();

    await expect(page.getByText("1 race found").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Nevada Governor Race 2026" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Ohio U.S. Senate Race 2026" }),
    ).toHaveCount(0);
  });

  test("shows a graceful empty state when a search matches nothing", async ({
    page,
  }) => {
    await gotoAndSettle(page, "/elections/?q=no-such-candidate-xyz");

    await expect(page.getByText("No races found").first()).toBeVisible();
    await expect(
      page.getByText("Try adjusting your filters.").first(),
    ).toBeVisible();

    await page.getByRole("button", { name: "Clear all filters" }).click();
    await expect(page.getByText("Showing 4 of 4 races").first()).toBeVisible();
  });

  test("navigating into a race from the directory reaches its detail page", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await gotoAndSettle(page, "/elections/");

    await page
      .getByRole("link", { name: /Ohio U\.S\. Senate Race 2026/ })
      .click();

    await expect(
      page.getByRole("heading", { name: "Ohio U.S. Senate Race 2026" }),
    ).toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(`/races/${FIXTURE_RACE_IDS.senate}/?$`),
    );
  });
});
