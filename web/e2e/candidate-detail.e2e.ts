import { test, expect } from "./support/test";
import { mockRaceJson } from "./support/network";
import {
  FIXTURE_RACE_IDS,
  ohSenateRace,
  txHouseDiscoveryRace,
} from "./fixtures/races";
import { responsiveMatch } from "./support/interactions";

test.describe("candidate detail page", () => {
  test("renders biography, issues, background, donors, and voting record", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto(
      `/races/${FIXTURE_RACE_IDS.senate}/senator-jordan-ellsworth/`,
    );

    await expect(
      page.getByRole("heading", { name: "Senator Jordan Ellsworth" }),
    ).toBeVisible();
    await expect(page.getByText("Democratic").first()).toBeVisible();
    await expect(page.getByText("Incumbent").first()).toBeVisible();
    await expect(page.getByText(/Two-term incumbent senator/)).toBeVisible();

    // IssueTable renders a full desktop table AND a full mobile card list at
    // once (Tailwind responsive classes toggle which is shown), so resolve
    // to whichever copy is actually visible for this viewport.
    await expect(
      page.getByRole("heading", { name: "Positions on Key Issues" }),
    ).toBeVisible();
    await expect(
      responsiveMatch(
        page,
        page.getByText("Healthcare"),
        "desktop-then-mobile",
      ),
    ).toBeVisible();

    // Background section
    await expect(
      page.getByRole("heading", { name: "Background" }),
    ).toBeVisible();
    await expect(page.getByText("U.S. Senator")).toBeVisible();
    await expect(page.getByText("Ohio State University")).toBeVisible();

    // Donors + voting record sections
    await expect(
      page.getByRole("heading", { name: "Top Donors" }),
    ).toBeVisible();
    await expect(page.getByText(/Machinists Union PAC/)).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Voting Record" }),
    ).toBeVisible();
    await expect(
      page.getByText(/bipartisan infrastructure package/),
    ).toBeVisible();

    // Other candidates collapsible
    const otherToggle = page.getByRole("button", {
      name: "Other Candidates (1)",
    });
    await expect(otherToggle).toBeVisible();
    await otherToggle.click();
    await expect(
      page.getByRole("link", { name: /Casey Whitfield/ }),
    ).toBeVisible();
  });

  test("omits the voting record section for a candidate with no voting summary", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto(`/races/${FIXTURE_RACE_IDS.senate}/casey-whitfield/`);

    await expect(
      page.getByRole("heading", { name: "Casey Whitfield" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Top Donors" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Voting Record" }),
    ).toHaveCount(0);
  });

  test("shows the discovery-only banner for a candidate with no researched issues", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.discovery, txHouseDiscoveryRace);
    await page.goto(`/races/${FIXTURE_RACE_IDS.discovery}/devon-marsh/`);

    await expect(
      page.getByRole("heading", { name: "Devon Marsh" }),
    ).toBeVisible();
    await expect(page.getByText("Limited Data — Discovery Only")).toBeVisible();
  });

  test("shows a not-found state for an unknown candidate slug", async ({
    page,
  }) => {
    await mockRaceJson(page, FIXTURE_RACE_IDS.senate, ohSenateRace);
    await page.goto(`/races/${FIXTURE_RACE_IDS.senate}/nobody-here/`);

    await expect(
      page.getByRole("heading", { name: "Candidate not found" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Back to race overview/ }),
    ).toBeVisible();
  });
});
