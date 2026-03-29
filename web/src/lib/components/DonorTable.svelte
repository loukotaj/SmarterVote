<script lang="ts">
  import type { TopDonor } from "$lib/types";
  import SourceLink from "./SourceLink.svelte";
  import NoDataFallback from "./NoDataFallback.svelte";

  export let donors: TopDonor[];
  export let raceId: string = "";
  export let candidateName: string = "";

  function formatAmount(amount?: number | null): string | null {
    if (!amount) return null;
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  }
</script>

<div class="donors-container">
  {#if donors.length === 0}
    <NoDataFallback dataType="donors" {raceId} {candidateName} />
  {:else}
    <div class="donors-list">
      {#each donors as donor}
        {@const amount = formatAmount(donor.amount)}
        <div class="donor-item">
          <div class="donor-info">
            <div class="donor-name">{donor.name}</div>
            {#if donor.organization && donor.organization !== donor.name}
              <div class="donor-org">{donor.organization}</div>
            {/if}
            {#if amount}
              <div class="donor-amount">{amount}</div>
            {/if}
          </div>
          <div class="donor-source">
            {#if donor.source}
              <SourceLink source={donor.source} />
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style lang="postcss">
  .donors-container { @apply space-y-4; }
  .donors-list { @apply space-y-3; }

  .donor-item {
    background-color: rgb(var(--sv-surface-alt));
    border: 1px solid rgb(var(--sv-border));
    @apply rounded-lg p-4 flex justify-between items-start;
  }

  .donor-info { @apply flex-1; }

  .donor-name {
    color: rgb(var(--sv-text));
    @apply font-semibold text-sm;
  }

  .donor-org {
    color: rgb(var(--sv-text-muted));
    @apply text-xs mt-1;
  }

  .donor-amount {
    @apply text-green-600 dark:text-green-400 font-medium text-sm mt-1;
  }

  .donor-source { @apply ml-4 flex-shrink-0; }
</style>
