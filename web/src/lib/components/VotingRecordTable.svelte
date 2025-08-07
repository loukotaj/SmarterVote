<script lang="ts">
  import type { VotingRecord } from "$lib/types";
  import SourceLink from "./SourceLink.svelte";

  export let votingRecord: VotingRecord[] = [];

  function formatDate(dateString: string): string {
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return dateString;
    }
  }

  function getVoteClass(vote: string): string {
    switch (vote.toLowerCase()) {
      case 'yes':
        return 'vote-yes';
      case 'no':
        return 'vote-no';
      case 'abstain':
        return 'vote-abstain';
      case 'absent':
        return 'vote-absent';
      default:
        return 'vote-unknown';
    }
  }

  function getVoteIcon(vote: string): string {
    switch (vote.toLowerCase()) {
      case 'yes':
        return '✓';
      case 'no':
        return '✗';
      case 'abstain':
        return '—';
      case 'absent':
        return '?';
      default:
        return '—';
    }
  }
</script>

<div class="voting-container">
  {#if votingRecord.length === 0}
    <div class="no-data">
      <p class="text-gray-500 text-sm">No voting record available</p>
      <p class="text-gray-400 text-xs mt-2">
        Voting records are only available for incumbent candidates with legislative history.
      </p>
    </div>
  {:else}
    <div class="voting-list">
      {#each votingRecord as record}
        <div class="voting-item">
          <div class="vote-header">
            <div class="bill-name">{record.bill_name}</div>
            <div class="vote-badge {getVoteClass(record.vote)}">
              <span class="vote-icon">{getVoteIcon(record.vote)}</span>
              <span class="vote-text">{record.vote.toUpperCase()}</span>
            </div>
          </div>
          
          {#if record.bill_description}
            <div class="bill-description">{record.bill_description}</div>
          {/if}
          
          <div class="vote-footer">
            <div class="vote-date">{formatDate(record.date)}</div>
            <SourceLink source={record.source} />
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style lang="postcss">
  .voting-container {
    @apply space-y-4;
  }

  .no-data {
    @apply text-center py-8;
  }

  .voting-list {
    @apply space-y-4;
  }

  .voting-item {
    @apply bg-gray-50 rounded-lg p-4 space-y-3;
  }

  .vote-header {
    @apply flex justify-between items-start gap-4;
  }

  .bill-name {
    @apply font-semibold text-gray-900 text-sm flex-1;
  }

  .vote-badge {
    @apply px-2 py-1 rounded-full text-xs font-medium flex items-center gap-1 flex-shrink-0;
  }

  .vote-yes {
    @apply bg-green-100 text-green-800;
  }

  .vote-no {
    @apply bg-red-100 text-red-800;
  }

  .vote-abstain {
    @apply bg-yellow-100 text-yellow-800;
  }

  .vote-absent {
    @apply bg-gray-100 text-gray-800;
  }

  .vote-unknown {
    @apply bg-gray-100 text-gray-600;
  }

  .vote-icon {
    @apply font-bold;
  }

  .vote-text {
    @apply font-medium;
  }

  .bill-description {
    @apply text-gray-600 text-sm leading-relaxed;
  }

  .vote-footer {
    @apply flex justify-between items-center;
  }

  .vote-date {
    @apply text-gray-500 text-xs;
  }
</style>
