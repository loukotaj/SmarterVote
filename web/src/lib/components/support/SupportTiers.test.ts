import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import SupportTiers from "./SupportTiers.svelte";

const { createSupportCheckout } = vi.hoisted(() => ({
  createSupportCheckout: vi.fn(),
}));

vi.mock("$lib/services/supportService", () => ({ createSupportCheckout }));

describe("SupportTiers", () => {
  afterEach(() => {
    createSupportCheckout.mockReset();
    cleanup();
  });

  it("exposes frequency and amount selection state", async () => {
    render(SupportTiers);

    const oneTime = screen.getByRole("button", { name: "One-time" });
    const monthly = screen.getByRole("button", { name: "Monthly" });
    expect(oneTime.getAttribute("aria-pressed")).toBe("true");
    await fireEvent.click(monthly);
    expect(monthly.getAttribute("aria-pressed")).toBe("true");

    await fireEvent.click(screen.getByRole("button", { name: "$25" }));
    expect(
      screen.getByRole("button", { name: "Support $25/mo →" }),
    ).toBeTruthy();
  });

  it("announces checkout failures without losing the selection", async () => {
    createSupportCheckout.mockRejectedValue(
      new Error("Payments are not yet available. Check back soon."),
    );
    render(SupportTiers);

    await fireEvent.click(screen.getByRole("button", { name: "Give $10 →" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "Payments are not yet available",
      ),
    );
    expect(createSupportCheckout).toHaveBeenCalledWith(1000, "payment");
    expect(screen.getByRole("button", { name: "Give $10 →" })).toBeTruthy();
  });
});
