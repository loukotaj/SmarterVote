import { test, expect } from "./support/test";
import { mockRaceJson } from "./support/network";
import { FIXTURE_RACE_IDS, ohSenateRace } from "./fixtures/races";
import { responsiveMatch } from "./support/interactions";

const COMPARE_PATH = `/races/${FIXTURE_RACE_IDS.senate}/compare`;

test.describe("candidate comparison page", () => {
  test("defaults to the first two candidates and expands a long stance", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto(`${COMPARE_PATH}/`);

    await expect(
      page.getByRole("heading", { name: "Compare Candidates" }),
    ).toBeVisible();
    await expect(
      page.getByRole("checkbox", { name: /Senator Jordan Ellsworth/ }),
    ).toBeChecked();
    await expect(
      page.getByRole("checkbox", { name: /Casey Whitfield/ }),
    ).toBeChecked();

    // Long stance text starts truncated with a "Show more" toggle. Both the
    // desktop table and the mobile card list render one, so resolve to
    // whichever copy is actually visible for this viewport.
    const showMore = responsiveMatch(
      page,
      page.getByRole("button", { name: /Show more/ }),
      "mobile-then-desktop",
    );
    await expect(showMore).toBeVisible();
    await showMore.click();
    await expect(
      responsiveMatch(
        page,
        page.getByRole("button", { name: /Show less/ }),
        "mobile-then-desktop",
      ),
    ).toBeVisible();
  });

  test("deselecting a candidate updates the URL and the comparison", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto(
      `${COMPARE_PATH}/?candidates=senator-jordan-ellsworth,casey-whitfield`,
    );

    await page.getByRole("checkbox", { name: /Casey Whitfield/ }).uncheck();

    await expect(page).toHaveURL(
      /candidates=senator-jordan-ellsworth(?!.*casey-whitfield)/,
    );
    await expect(
      page.getByRole("checkbox", { name: /Casey Whitfield/ }),
    ).not.toBeChecked();
    await expect(
      page.getByRole("checkbox", { name: /Senator Jordan Ellsworth/ }),
    ).toBeChecked();
  });

  test("navigating back to the race overview preserves context", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto(`${COMPARE_PATH}/`);

    await page.getByRole("link", { name: "← Back to Race Overview" }).click();

    await expect(page).toHaveURL(
      new RegExp(`/races/${FIXTURE_RACE_IDS.senate}/?$`),
    );
    await expect(
      page.getByRole("heading", { name: "Ohio U.S. Senate Race 2026" }),
    ).toBeVisible();
  });
});
