import { racesApiBase } from "$lib/config/api";

export type SupportMode = "payment" | "subscription";
export type CheckoutStatus = "confirmed" | "pending";

async function responseError(
  response: Response,
  fallback: string,
): Promise<Error> {
  if (response.status === 503)
    return new Error("Payments are not yet available. Check back soon.");

  const payload = (await response.json().catch(() => ({}))) as {
    detail?: unknown;
  };
  return new Error(
    typeof payload.detail === "string" ? payload.detail : fallback,
  );
}

export async function createSupportCheckout(
  amountCents: number,
  mode: SupportMode,
  fetcher: typeof fetch = fetch,
): Promise<string> {
  const response = await fetcher(`${racesApiBase()}/payments/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount_cents: amountCents, mode }),
  });
  if (!response.ok)
    throw await responseError(
      response,
      "Something went wrong. Please try again.",
    );

  const payload = (await response.json()) as { url?: unknown };
  if (typeof payload.url !== "string")
    throw new Error("Checkout returned an invalid redirect. Please try again.");

  let redirect: URL;
  try {
    redirect = new URL(payload.url);
  } catch {
    throw new Error("Checkout returned an invalid redirect. Please try again.");
  }
  if (
    redirect.protocol !== "https:" ||
    redirect.hostname !== "checkout.stripe.com"
  )
    throw new Error("Checkout returned an invalid redirect. Please try again.");
  return redirect.href;
}

export async function getCheckoutStatus(
  sessionId: string,
  fetcher: typeof fetch = fetch,
): Promise<CheckoutStatus> {
  const response = await fetcher(
    `${racesApiBase()}/payments/session/${encodeURIComponent(sessionId)}`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok)
    throw await responseError(response, "We could not verify this checkout.");

  const payload = (await response.json()) as { status?: unknown };
  if (payload.status !== "confirmed" && payload.status !== "pending")
    throw new Error("We could not verify this checkout.");
  return payload.status;
}
