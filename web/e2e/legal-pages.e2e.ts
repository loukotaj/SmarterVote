import { test, expect } from "@playwright/test";

/**
 * Lightweight smoke coverage for the static legal/marketing/support routes
 * that `frontend-smoke.e2e.ts` doesn't already touch. These pages have no
 * data dependencies, so there's nothing to stub — just confirm each one
 * renders its heading.
 */
const STATIC_PAGES: Array<{ path: string; heading: string }> = [
  { path: "/corrections/", heading: "Corrections" },
  {
    path: "/funding-and-editorial-independence/",
    heading: "Funding and editorial independence",
  },
  { path: "/partners/", heading: "Partner with Smarter.Vote" },
  { path: "/privacy/", heading: "Privacy" },
  { path: "/terms/", heading: "Terms of use" },
  { path: "/support/cancel/", heading: "Checkout cancelled" },
];

for (const { path, heading } of STATIC_PAGES) {
  test(`${path} renders its heading`, async ({ page }) => {
    await page.goto(path);
    await expect(
      page.getByRole("heading", { name: heading, level: 1 }),
    ).toBeVisible();
  });
}

test("/support/success/ without a session id shows a verification error, not a crash", async ({
  page,
}) => {
  await page.goto("/support/success/");

  await expect(
    page.getByRole("heading", { name: "Checkout status", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "We could not verify this payment" }),
  ).toBeVisible();
});
