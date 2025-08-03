import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import CardTestWrapper from "./CardTestWrapper.svelte";

describe("Card", () => {
  it("renders slot content and merges classes", () => {
    const { getByText } = render(CardTestWrapper);
    const card = getByText("Content").parentElement as HTMLElement;
    expect(card.classList.contains("card")).toBe(true);
    expect(card.classList.contains("extra")).toBe(true);
  });
});
