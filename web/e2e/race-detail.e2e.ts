import { test, expect } from "./support/test";
import { mockRaceJson, mockRaceNotFound } from "./support/network";
import {
  FIXTURE_RACE_IDS,
  flHouseUncontestedRace,
  ohSenateRace,
  txHouseDiscoveryRace,
} from "./fixtures/races";

test.describe("race detail page", () => {
  test("renders candidates, forecast, polling, validation grade, and AI review", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto(`/races/${FIXTURE_RACE_IDS.senate}/`);

    await expect(
      page.getByRole("heading", { name: "2026 Ohio U.S. Senate Election" }),
    ).toBeVisible();

    // Candidates section
    await expect(
      page.getByRole("heading", { name: "Candidates" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Senator Jordan Ellsworth", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Casey Whitfield", exact: true }),
    ).toBeVisible();

    // Validation grade badge
    await expect(
      page.getByRole("button", { name: "Automated Research Score: A" }),
    ).toBeVisible();

    // Forecast section (rating is "tossup" -> renders as "Toss-up" heading)
    await expect(page.getByRole("heading", { name: "Toss-up" })).toBeVisible();

    // Detailed polling section is visible without any interaction. Use
    // exact text since the "Latest Poll" snapshot widget above it also
    // mentions the pollster name combined with the poll date.
    await expect(
      page.getByText("Fixture Polling Co.", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Second Fixture Insights", { exact: true }),
    ).toBeVisible();

    // AI review panel starts collapsed; expand it and check both reviews
    const reviewToggle = page.getByRole("button", {
      name: /Automated Review Details/,
    });
    await expect(reviewToggle).toContainText("2 reviews");
    await reviewToggle.click();
    await expect(page.getByText("anthropic/claude-haiku-4.5")).toBeVisible();
    await expect(page.getByText("x-ai/grok-4.3")).toBeVisible();
    await expect(page.getByText("approved").first()).toBeVisible();
  });

  test("selecting two candidates and comparing navigates to the compare page", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto(`/races/${FIXTURE_RACE_IDS.senate}/`);

    await page
      .getByRole("checkbox", {
        name: "Select Senator Jordan Ellsworth to compare",
      })
      .check();
    await page
      .getByRole("checkbox", { name: "Select Casey Whitfield to compare" })
      .check();

    await page.getByRole("link", { name: "Compare Now" }).click();

    await expect(page).toHaveURL(/\/races\/e2e-oh-senate-2026\/compare\/\?/);
    const url = new URL(page.url());
    const selected = url.searchParams.get("candidates")?.split(",") ?? [];
    expect(selected.sort()).toEqual(
      ["senator-jordan-ellsworth", "casey-whitfield"].sort(),
    );
  });

  test("shows the discovery-only banner when no issue research has run", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.discovery, txHouseDiscoveryRace);
    await page.goto(`/races/${FIXTURE_RACE_IDS.discovery}/`);

    await expect(page.getByText("Limited Data — Discovery Only")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Request a research run" }),
    ).toBeVisible();
  });

  test("uncontested (single-candidate) race has no compare controls", async ({
    page,
  }) => {
    await mockRaceJson(
      page,
      FIXTURE_RACE_IDS.uncontested,
      flHouseUncontestedRace,
    );
    await page.goto(`/races/${FIXTURE_RACE_IDS.uncontested}/`);

    await expect(
      page.getByRole("heading", {
        name: "2026 Florida's 9th Congressional District Election",
      }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Compare all" })).toHaveCount(
      0,
    );
    await expect(page.getByRole("checkbox")).toHaveCount(0);
  });

  test("renders an error state gracefully when the race cannot be found", async ({
    page,
  }) => {
    await mockRaceNotFound(page, "e2e-does-not-exist");
    await page.goto("/races/e2e-does-not-exist/");

    await expect(
      page.getByRole("heading", { name: "Error loading race" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});
