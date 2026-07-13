import { render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import ContactCard from "./ContactCard.svelte";

describe("ContactCard", () => {
  it("creates a role-labelled email link", () => {
    render(ContactCard, {
      subject: "Correction: race name",
      label: "Report a correction",
    });
    const link = screen.getByRole("link", { name: "Report a correction" });
    expect(link.getAttribute("href")).toBe(
      "mailto:SmarterDotVote@gmail.com?subject=Correction%3A%20race%20name",
    );
  });
});
