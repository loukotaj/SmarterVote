import { cleanup, render, screen, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Page from "./+page.svelte";

const { getCheckoutStatus } = vi.hoisted(() => ({
  getCheckoutStatus: vi.fn(),
}));

vi.mock("$lib/services/supportService", () => ({ getCheckoutStatus }));

describe("support success page", () => {
  beforeEach(() => {
    getCheckoutStatus.mockReset();
    window.history.replaceState({}, "", "/support/success/");
  });
  afterEach(cleanup);

  it("does not claim success without a checkout session", async () => {
    render(Page);
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "could not verify",
      ),
    );
    expect(screen.queryByText("Payment confirmed")).toBeNull();
    expect(getCheckoutStatus).not.toHaveBeenCalled();
  });

  it("shows confirmation only after the API verifies the session", async () => {
    window.history.replaceState(
      {},
      "",
      "/support/success/?session_id=cs_test_example",
    );
    getCheckoutStatus.mockResolvedValue("confirmed");
    render(Page);

    await waitFor(() =>
      expect(screen.getByText("Payment confirmed")).toBeTruthy(),
    );
    expect(getCheckoutStatus).toHaveBeenCalledWith("cs_test_example");
  });
});
