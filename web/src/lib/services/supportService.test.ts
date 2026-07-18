import { afterEach, describe, expect, it, vi } from "vitest";
import { createSupportCheckout, getCheckoutStatus } from "./supportService";

describe("supportService", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts only the server-validated amount and mode", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ url: "https://checkout.stripe.com/c/pay/test" }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    await expect(
      createSupportCheckout(2500, "subscription", fetcher),
    ).resolves.toBe("https://checkout.stripe.com/c/pay/test");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      amount_cents: 2500,
      mode: "subscription",
    });
  });

  it("rejects a non-Stripe redirect returned by the API", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ url: "https://example.com/checkout" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(
      createSupportCheckout(1000, "payment", fetcher),
    ).rejects.toThrow("invalid redirect");
  });

  it("returns a verified checkout status and preserves API errors", async () => {
    const confirmed = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "confirmed" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(getCheckoutStatus("cs_test_example", confirmed)).resolves.toBe(
      "confirmed",
    );

    const unavailable = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "not configured" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(
      getCheckoutStatus("cs_test_example", unavailable),
    ).rejects.toThrow("Payments are not yet available");
  });
});
