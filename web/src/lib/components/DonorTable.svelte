<script lang="ts">
  import type { TopDonor } from "$lib/types";
  import SourceLink from "./SourceLink.svelte";
  import NoDataFallback from "./NoDataFallback.svelte";

  export let donors: TopDonor[];
  export let donorSourceUrl: string = "";
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
  {#if donorSourceUrl}
    <a href={donorSourceUrl} target="_blank" rel="noopener noreferrer" class="donor-source-btn">
      View all campaign donors →
    </a>
  {/if}

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
            <div class="donor-meta">
              {#if amount}
                <span class="donor-amount">{amount}</span>
              {/if}
              {#if donor.donation_year}
                <span class="donor-year">({donor.donation_year})</span>
              {/if}
            </div>
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

  .donor-source-btn {
    @apply inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors;
    background-color: rgb(var(--sv-primary) / 0.1);
    color: rgb(var(--sv-primary));
    border: 1px solid rgb(var(--sv-primary) / 0.3);
  }
  .donor-source-btn:hover {
    background-color: rgb(var(--sv-primary) / 0.2);
  }

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

  .donor-meta {
    @apply flex items-center gap-2 mt-1;
  }

  .donor-amount {
    @apply text-green-600 dark:text-green-400 font-medium text-sm;
  }

  .donor-year {
    color: rgb(var(--sv-text-muted));
    @apply text-xs;
  }

  .donor-source { @apply ml-4 flex-shrink-0; }
</style>
