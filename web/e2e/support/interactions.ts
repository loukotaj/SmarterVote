import type { Locator, Page } from "@playwright/test";

/**
 * Several components (IssueTable, CandidateComparison) render two full
 * copies of the same content — one for desktop, one for mobile — and use
 * Tailwind responsive classes (`hidden lg:block` / `lg:hidden`) to show only
 * one at a time. Both copies exist in the DOM regardless of viewport, so a
 * bare `.first()`/`.last()` picks whichever happens to be first in document
 * order — which is only reliably the *visible* one if that order matches the
 * current viewport. This resolves a locator matching duplicated responsive
 * markup to whichever copy is actually visible for the page's current
 * viewport, given the known DOM order.
 */
export function responsiveMatch(
  page: Page,
  locator: Locator,
  domOrder: "desktop-then-mobile" | "mobile-then-desktop",
): Locator {
  const isWideViewport = (page.viewportSize()?.width ?? 0) >= 1024;
  const wantsFirstMatch =
    domOrder === "desktop-then-mobile" ? isWideViewport : !isWideViewport;
  return wantsFirstMatch ? locator.first() : locator.last();
}

/**
 * Navigates and waits for the page's own client-side data fetching (race
 * summaries, chamber forecasts, etc. via `+page.ts` load functions) to
 * settle before returning. Plain `page.goto()` only waits for the `load`
 * event, which can resolve slightly before a heavier route (e.g.
 * `/forecast`) has finished fetching and rendering its data — so an
 * immediate click right after `goto()` can land before listeners for that
 * data-dependent content exist. Waiting for the network to go idle avoids
 * that gap without resorting to a fixed sleep.
 */
export async function gotoAndSettle(page: Page, url: string): Promise<void> {
  await page.goto(url, { waitUntil: "networkidle" });
}
