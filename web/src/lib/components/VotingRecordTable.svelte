<script lang="ts">
  import NoDataFallback from "./NoDataFallback.svelte";

  export let votingSummary: string = "";
  export let votingSourceUrl: string = "";
  export let raceId: string = "";
  export let candidateName: string = "";
</script>

<div class="voting-container">
  {#if !votingSummary}
    <NoDataFallback dataType="voting" {raceId} {candidateName} />
  {:else}
    <div class="voting-summary">
      <p class="summary-text">{votingSummary}</p>
    </div>

    {#if votingSourceUrl}
      <a href={votingSourceUrl} target="_blank" rel="noopener noreferrer" class="source-link-btn">
        View full voting record →
      </a>
    {/if}
  {/if}
</div>

<style lang="postcss">
  .voting-container { @apply space-y-4; }

  .voting-summary {
    background-color: rgb(var(--sv-surface-alt));
    border: 1px solid rgb(var(--sv-border));
    @apply rounded-lg p-4;
  }

  .summary-text {
    color: rgb(var(--sv-text));
    @apply text-sm leading-relaxed;
  }

  .source-link-btn {
    @apply inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors;
    background-color: rgb(var(--sv-primary) / 0.1);
    color: rgb(var(--sv-primary));
    border: 1px solid rgb(var(--sv-primary) / 0.3);
  }
  .source-link-btn:hover {
    background-color: rgb(var(--sv-primary) / 0.2);
  }
</style>
