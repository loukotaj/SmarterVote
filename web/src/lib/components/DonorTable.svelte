<script lang="ts">
  import NoDataFallback from "./NoDataFallback.svelte";

  export let donorSummary: string = "";
  export let donorSourceUrl: string = "";
  export let raceId: string = "";
  export let candidateName: string = "";
</script>

<div class="donors-container">
  {#if !donorSummary}
    <NoDataFallback dataType="donors" {raceId} {candidateName} />
  {:else}
    <div class="donor-summary">
      <p class="summary-text">{donorSummary}</p>
    </div>

    {#if donorSourceUrl}
      <a href={donorSourceUrl} target="_blank" rel="noopener noreferrer" class="donor-source-btn">
        View full campaign finance data →
      </a>
    {/if}
  {/if}
</div>

<style lang="postcss">
  .donors-container { @apply space-y-4; }

  .donor-summary {
    background-color: rgb(var(--sv-surface-alt));
    border: 1px solid rgb(var(--sv-border));
    @apply rounded-lg p-4;
  }

  .summary-text {
    color: rgb(var(--sv-text));
    @apply text-sm leading-relaxed;
  }

  .donor-source-btn {
    @apply inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors;
    background-color: rgb(var(--sv-primary) / 0.1);
    color: rgb(var(--sv-primary));
    border: 1px solid rgb(var(--sv-primary) / 0.3);
  }
  .donor-source-btn:hover {
    background-color: rgb(var(--sv-primary) / 0.2);
  }
</style>
