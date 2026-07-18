import { expect, test } from "@playwright/test";

test("global navigation and search stay accessible and within the viewport", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const search = page.getByRole("combobox", {
    name: "Search elections and candidates",
  });
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
