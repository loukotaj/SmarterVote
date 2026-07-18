<script lang="ts">
  import {
    createSupportCheckout,
    type SupportMode,
  } from "$lib/services/supportService";

  const PRESET_AMOUNTS = [5, 10, 25, 50];

  let mode: SupportMode = "payment";
  let selectedAmount: number | null = 10;
  let customAmount = "";
  let loading = false;
  let error = "";

  $: effectiveAmountCents = (() => {
    if (selectedAmount !== null) return selectedAmount * 100;
    const parsed = parseFloat(customAmount);
    if (!isNaN(parsed) && parsed >= 1 && parsed <= 1000)
      return Math.round(parsed * 100);
    return null;
  })();

  $: canSubmit = effectiveAmountCents !== null && !loading;

  function selectPreset(amount: number) {
    selectedAmount = amount;
    customAmount = "";
  }

  function onCustomInput() {
    selectedAmount = null;
  }

  async function handleCheckout() {
    if (!canSubmit || effectiveAmountCents === null) return;
    loading = true;
    error = "";

    try {
      const url = await createSupportCheckout(effectiveAmountCents, mode);
      window.location.assign(url);
    } catch (caught) {
      error =
        caught instanceof Error
          ? caught.message
          : "Could not connect. Please try again.";
    } finally {
      loading = false;
    }
  }
</script>

<form
  class="space-y-6"
  aria-busy={loading}
  on:submit|preventDefault={handleCheckout}
>
  <!-- One-time / Monthly toggle -->
  <fieldset>
    <legend class="mb-2 text-sm font-semibold text-content">Frequency</legend>
    <div
      class="flex rounded-lg border border-stroke bg-surface-alt p-1 text-sm font-medium"
    >
      <button
        type="button"
        aria-pressed={mode === "payment"}
        class="min-h-11 flex-1 rounded-md py-2 transition-colors {mode ===
        'payment'
          ? 'bg-surface text-content shadow-sm'
          : 'text-content-muted hover:text-content'}"
        on:click={() => (mode = "payment")}
      >
        One-time
      </button>
      <button
        type="button"
        aria-pressed={mode === "subscription"}
        class="min-h-11 flex-1 rounded-md py-2 transition-colors {mode ===
        'subscription'
          ? 'bg-surface text-content shadow-sm'
          : 'text-content-muted hover:text-content'}"
        on:click={() => (mode = "subscription")}
      >
        Monthly
      </button>
    </div>
  </fieldset>

  <!-- Amount presets -->
  <fieldset>
    <legend class="mb-2 text-sm font-semibold text-content">Amount</legend>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {#each PRESET_AMOUNTS as amount}
        <button
          type="button"
          aria-pressed={selectedAmount === amount}
          class="rounded-lg border py-3 text-sm font-semibold transition-colors {selectedAmount ===
          amount
            ? 'border-primary-500 bg-primary-50 text-primary-700 dark:border-primary-500 dark:bg-primary-950 dark:text-primary-300'
            : 'border-stroke bg-surface text-content hover:border-primary-400 hover:bg-surface-alt'}"
          on:click={() => selectPreset(amount)}
        >
          ${amount}
        </button>
      {/each}
    </div>
  </fieldset>

  <!-- Custom amount -->
  <div class="relative">
    <span
      class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-muted text-sm"
      >$</span
    >
    <input
      id="custom-support-amount"
      aria-label="Custom support amount in dollars"
      type="number"
      inputmode="decimal"
      min="1"
      max="1000"
      step="1"
      placeholder="Custom amount"
      class="min-h-11 w-full rounded-lg border border-stroke bg-surface py-2.5 pl-7 pr-3 text-sm text-content placeholder:text-content-muted focus:border-primary-500 focus:outline-none {selectedAmount ===
        null && customAmount
        ? 'border-primary-500'
        : ''}"
      bind:value={customAmount}
      on:input={onCustomInput}
    />
  </div>

  {#if error}
    <p
      role="alert"
      class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
    >
      {error}
    </p>
  {/if}

  <!-- CTA -->
  <button
    type="submit"
    class="inline-flex w-full items-center justify-center rounded-lg bg-primary-600 px-5 py-3 font-semibold text-white transition hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
    disabled={!canSubmit}
  >
    {#if loading}
      <svg
        aria-hidden="true"
        class="mr-2 h-4 w-4 animate-spin"
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle
          class="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          stroke-width="4"
        />
        <path
          class="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      Redirecting…
    {:else if effectiveAmountCents !== null}
      {mode === "subscription" ? "Support" : "Give"} ${(
        effectiveAmountCents / 100
      ).toFixed(effectiveAmountCents % 100 === 0 ? 0 : 2)}{mode ===
      "subscription"
        ? "/mo"
        : ""} →
    {:else}
      Enter an amount to continue
    {/if}
  </button>

  <p class="text-center text-xs text-content-muted">
    Secure checkout via Stripe. Not tax-deductible.
    {#if mode === "subscription"}
      Monthly support renews automatically; contact us to cancel.
    {/if}
  </p>
</form>
