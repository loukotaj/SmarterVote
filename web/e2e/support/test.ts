import { test as base, expect, type Page } from "@playwright/test";

/**
 * Every focused (non-smoke) spec in this suite imports `test`/`expect` from
 * here instead of `@playwright/test` directly.
 *
 * It wraps the `page` fixture with a blanket network guard: any request to a
 * different origin than the app itself is aborted unless a spec has already
 * stubbed it (e.g. the Census geocoder JSONP endpoint via
 * `mockCensusGeocoder`, registered *after* this guard so it takes priority).
 * That makes "no real network calls" a structural guarantee for the whole
 * suite rather than something every spec has to remember to set up.
 */
export const test = base.extend<{ page: Page }>({
  page: async ({ page, baseURL }, use) => {
    const appOrigin = new URL(baseURL ?? "http://127.0.0.1:4173").origin;
    await page.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.origin === appOrigin) {
        await route.continue();
        return;
      }
      // Anything not served by our own dev server (Census geocoder, Google
      // Maps, etc.) is blocked by default. Specs that need one of these must
      // explicitly stub it with a more specific route registered afterward.
      await route.abort("blockedbyclient");
    });
    await use(page);
  },
});

export { expect };
