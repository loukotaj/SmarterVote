<script lang="ts">
  import { onMount } from "svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
  import {
    getCheckoutStatus,
    type CheckoutStatus,
  } from "$lib/services/supportService";

  let status: CheckoutStatus | "checking" | "error" = "checking";

  onMount(async () => {
    const sessionId = new URL(window.location.href).searchParams.get(
      "session_id",
    );
    if (!sessionId) {
      status = "error";
      return;
    }
    try {
      status = await getCheckoutStatus(sessionId);
    } catch {
      status = "error";
    }
  });
</script>

<TrustPage
  title="Checkout status"
  description="Confirm the status of your Smarter.Vote support payment."
  path="/support/success/"
>
  <div aria-live="polite" aria-busy={status === "checking"}>
    {#if status === "confirmed"}
      <div
        class="rounded-xl border border-green-300 bg-green-50 p-6 text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100"
        role="status"
      >
        <h2 class="mb-2 text-lg font-semibold">Payment confirmed</h2>
        <p>
          Thank you — your support goes directly toward election research and
          broader coverage. Stripe will send a receipt to the email provided at
          checkout.
        </p>
      </div>
    {:else if status === "pending"}
      <div
        class="rounded-xl border border-amber-300 bg-amber-50 p-6 text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
        role="status"
      >
        <h2 class="mb-2 text-lg font-semibold">Payment processing</h2>
        <p>
          Stripe has not confirmed the payment yet. Check your receipt or return
          to this page shortly.
        </p>
      </div>
    {:else if status === "error"}
      <div
        class="rounded-xl border border-stroke bg-surface-alt p-6 text-content"
        role="alert"
      >
        <h2 class="mb-2 text-lg font-semibold">
          We could not verify this payment
        </h2>
        <p>
          Do not submit another payment solely because of this message. Check
          for a Stripe receipt or contact us for help.
        </p>
      </div>
    {:else}
      <p
        class="rounded-xl border border-stroke bg-surface-alt p-6 text-content"
        role="status"
      >
        Confirming your payment with Stripe…
      </p>
    {/if}
  </div>
  <p class="text-content-muted">
    If you have any questions about your support payment, <a
      href="/support/"
      class="text-primary-600 underline hover:text-primary-700 dark:text-primary-400"
      >contact us</a
    >.
  </p>
</TrustPage>
