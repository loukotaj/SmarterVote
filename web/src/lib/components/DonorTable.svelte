<script lang="ts">
  import type { TopDonor } from "$lib/types";
  import SourceLink from "./SourceLink.svelte";
  import NoDataFallback from "./NoDataFallback.svelte";

  export let donors: TopDonor[];
  export let raceId: string = "";
  export let candidateName: string = "";

  function formatAmount(amount?: number): string {
    if (!amount) return "Amount not disclosed";
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
        <div class="donor-item">
          <div class="donor-info">
            <div class="donor-name">{donor.name}</div>
            {#if donor.organization}
              <div class="donor-org">{donor.organization}</div>
            {/if}
            <div class="donor-amount">{formatAmount(donor.amount)}</div>
          </div>
          <div class="donor-source">
            <SourceLink source={donor.source} />
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style lang="postcss">
  .donors-container {
    @apply space-y-4;
  }

  .donors-list {
    @apply space-y-3;
  }

  .donor-item {
    @apply bg-gray-50 rounded-lg p-4 flex justify-between items-start;
  }

  .donor-info {
    @apply flex-1;
  }

  .donor-name {
    @apply font-semibold text-gray-900 text-sm;
  }

  .donor-org {
    @apply text-gray-600 text-xs mt-1;
  }

  .donor-amount {
    @apply text-green-600 font-medium text-sm mt-1;
  }

  .donor-source {
    @apply ml-4 flex-shrink-0;
  }
</style>
