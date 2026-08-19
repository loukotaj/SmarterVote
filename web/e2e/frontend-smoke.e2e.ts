import { expect, test } from "@playwright/test";

test("global navigation and search stay accessible and within the viewport", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const search = page.getByRole("combobox", {
    name: "Search elections and candidates",
  });
  if ((page.viewportSize()?.width ?? 0) < 640) {
    await page.getByRole("button", { name: "Open search" }).click();
  }
  await expect(search).toBeVisible();
  await expect(search).toHaveAttribute("aria-autocomplete", "list");

  const primaryNavigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  if ((page.viewportSize()?.width ?? 0) < 640) {
    await expect(primaryNavigation).toBeHidden();
    const menuButton = page.getByRole("button", {
      name: "Open navigation menu",
    });
    await expect(menuButton).toHaveAttribute("aria-expanded", "false");
    await menuButton.click();
    await expect(primaryNavigation).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Close navigation menu" }),
    ).toHaveAttribute("aria-expanded", "true");
  } else {
    await expect(primaryNavigation).toBeVisible();
  }

  const themeToggle = page.getByRole("button", {
    name: /switch to (light|dark) mode/i,
  });
  const box = await themeToggle.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);

  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("election directory and ballot lookup render their primary controls", async ({
  page,
}) => {
  await page.goto("/elections/");
  await expect(
    page.getByRole("heading", { name: /explore elections/i }),
  ).toBeVisible();

  await page.goto("/my-ballot/");
  const address = page.getByRole("combobox", { name: /home address/i });
  await expect(address).toBeVisible();
  await expect(address).toHaveAttribute("aria-autocomplete", "list");
});

test("forecast and trust surfaces expose their primary content", async ({
  page,
}) => {
  await page.goto("/forecast/");
  await expect(
    page.getByRole("heading", { name: "2026 Election Forecast" }),
  ).toBeVisible();

  await page.goto("/about/");
  await expect(
    page.getByRole("heading", { name: "About Smarter.Vote" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "This site uses AI-generated content" }),
  ).toBeVisible();

  await page.goto("/support/");
  await expect(
    page.getByRole("heading", { name: "Support Smarter.Vote" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Support terms" }),
  ).toBeVisible();
});

test("race detail and comparison routes render structured fallback data", async ({
  page,
}) => {
  await page.goto("/races/sample-race/");
  await expect(
    page.getByRole("heading", {
      name: "2025 Sample State U.S. Senate Election",
    }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Candidates" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Senator Sarah Johnson", exact: true }),
  ).toBeVisible();

  await page.goto("/races/sample-race/compare/");
  await expect(
    page.getByRole("heading", { name: "Compare Candidates" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: /Senator Sarah Johnson/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: /Representative Maria Rodriguez/ }),
  ).toBeVisible();
});

test("admin entry point is explicitly excluded from indexing", async ({
  page,
}) => {
  await page.goto("/admin/");
  await expect(page).toHaveTitle("Admin Sign In | Smarter.Vote");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
    "content",
    "noindex,nofollow",
  );
});
