import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import ForecastTabNav from "./ForecastTabNav.svelte";

const tabs = [
  { id: "house" as const, label: "House" },
  { id: "senate" as const, label: "Senate" },
  { id: "governors" as const, label: "Governors" },
];

describe("ForecastTabNav", () => {
  afterEach(cleanup);

  it("marks the active tab and calls onSelect on click", async () => {
    const onSelect = vi.fn();
    render(ForecastTabNav, {
      tabs,
      activeTab: "house",
      onSelect,
    });

    expect(screen.getByText("House").closest("button")?.className).toContain(
      "active",
    );

    await fireEvent.click(screen.getByText("Senate"));

    expect(onSelect).toHaveBeenCalledWith("senate");
  });
});
