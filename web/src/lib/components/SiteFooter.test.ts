import { render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import SiteFooter from "./SiteFooter.svelte";

describe("SiteFooter", () => {
  it("links to the public trust and organization pages", () => {
    render(SiteFooter);

    expect(
      screen.getByRole("link", { name: "Partners" }).getAttribute("href"),
    ).toBe("/partners/");
    expect(
      screen
        .getByRole("link", { name: "Funding & independence" })
        .getAttribute("href"),
    ).toBe("/funding-and-editorial-independence/");
    expect(
      screen.getByRole("link", { name: "Privacy" }).getAttribute("href"),
    ).toBe("/privacy/");
    expect(
      screen.getByRole("link", { name: "Terms" }).getAttribute("href"),
    ).toBe("/terms/");
  });
});
