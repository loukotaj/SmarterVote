<script lang="ts">
  import type { VotingRecord } from "$lib/types";
  import SourceLink from "./SourceLink.svelte";
  import NoDataFallback from "./NoDataFallback.svelte";

  export let votingRecord: VotingRecord[] = [];
  export let votingSummary: string = "";
  export let votingSourceUrl: string = "";
  export let raceId: string = "";
  export let candidateName: string = "";

  let showIndividualVotes = false;

  // The agent sometimes produces {bill, position} instead of {bill_name, vote}
  function billName(r: any): string {
    return r.bill_name ?? r.bill ?? "Unknown Bill";
  }

  function normalizeVote(r: any): string {
    const raw: string = r.vote ?? r.position ?? "";
    if (!raw) return "";
    const v = raw.toLowerCase();
    if (v === "yes" || v === "yea") return "yes";
    if (v === "no" || v === "nay") return "no";
    if (v.includes("against") || v.includes("oppose")) return "no";
    if (v.includes("for") && !v.includes("before")) return "yes";
    if (v.includes("abstain") || v.includes("present")) return "abstain";
    if (v.includes("absent") || v.includes("not voting") || v.includes("did not")) return "absent";
    return raw;
  }

  function getVoteClass(vote: string): string {
    switch (vote) {
      case "yes":    return "vote-yes";
      case "no":     return "vote-no";
      case "abstain": return "vote-abstain";
      case "absent": return "vote-absent";
      default:       return "vote-unknown";
    }
  }

  function getVoteIcon(vote: string): string {
    switch (vote) {
      case "yes":    return "✓";
      case "no":     return "✗";
      case "abstain": return "—";
      case "absent": return "?";
      default:       return "•";
    }
  }

  function billDescription(r: any): string | null {
    return r.bill_description ?? null;
  }

  function formatDate(dateString: string): string {
    try {
      return new Date(dateString).toLocaleDateString("en-US", {
        year: "numeric", month: "short", day: "numeric",
      });
    } catch {
      return dateString;
    }
  }

  $: hasData = votingSummary || votingRecord.length > 0;
</script>

<div class="voting-container">
  {#if !hasData}
    <NoDataFallback dataType="voting" {raceId} {candidateName} />
  {:else}
    <!-- Summary + source link (primary display) -->
    {#if votingSummary}
      <div class="voting-summary">
        <p class="summary-text">{votingSummary}</p>
      </div>
    {/if}

    {#if votingSourceUrl}
      <a href={votingSourceUrl} target="_blank" rel="noopener noreferrer" class="source-link-btn">
        View full voting record →
      </a>
    {/if}

    <!-- Expandable individual votes -->
    {#if votingRecord.length > 0}
      <button
        class="expand-toggle"
        on:click={() => (showIndividualVotes = !showIndividualVotes)}
      >
        {showIndividualVotes ? "Hide" : "Show"} individual votes ({votingRecord.length})
      </button>

      {#if showIndividualVotes}
        <div class="voting-list">
          {#each votingRecord as record}
            {@const vote = normalizeVote(record)}
            <div class="voting-item">
              <div class="vote-header">
                <div class="bill-name">{billName(record)}</div>
                <div class="vote-badge {getVoteClass(vote)}">
                  <span class="vote-icon">{getVoteIcon(vote)}</span>
                  <span class="vote-text">{vote.toUpperCase()}</span>
                </div>
              </div>

              {#if billDescription(record)}
                <div class="bill-description">{billDescription(record)}</div>
              {/if}

              <div class="vote-footer">
                <div class="vote-date">{record.date ? formatDate(record.date) : ""}</div>
                {#if record.source}
                  <SourceLink source={record.source} />
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
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

  .expand-toggle {
    color: rgb(var(--sv-text-muted));
    @apply text-xs underline cursor-pointer bg-transparent border-0 p-0;
  }
  .expand-toggle:hover {
    color: rgb(var(--sv-text));
  }

  .voting-list { @apply space-y-4 mt-2; }

  .voting-item {
    background-color: rgb(var(--sv-surface-alt));
    border: 1px solid rgb(var(--sv-border));
    @apply rounded-lg p-4 space-y-3;
  }

  .vote-header { @apply flex justify-between items-start gap-4; }

  .bill-name {
    color: rgb(var(--sv-text));
    @apply font-semibold text-sm flex-1;
  }

  .vote-badge {
    @apply px-2 py-1 rounded-full text-xs font-medium flex items-center gap-1 flex-shrink-0;
  }

  .vote-yes    { @apply bg-green-100  text-green-800  dark:bg-green-900  dark:text-green-200; }
  .vote-no     { @apply bg-red-100    text-red-800    dark:bg-red-900    dark:text-red-200; }
  .vote-abstain { @apply bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200; }
  .vote-absent { @apply bg-gray-100   text-gray-700   dark:bg-gray-700   dark:text-gray-300; }
  .vote-unknown { @apply bg-gray-100  text-gray-600   dark:bg-gray-700   dark:text-gray-400; }

  .vote-icon { @apply font-bold; }
  .vote-text { @apply font-medium; }

  .bill-description {
    color: rgb(var(--sv-text-muted));
    @apply text-sm leading-relaxed;
  }

  .vote-footer { @apply flex justify-between items-center; }

  .vote-date {
    color: rgb(var(--sv-text-subtle));
    @apply text-xs;
  }
</style>
