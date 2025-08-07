<script lang="ts">
  import IssueTable from "./IssueTable.svelte";
  import DonorTable from "./DonorTable.svelte";
  import VotingRecordTable from "./VotingRecordTable.svelte";
  import TabButton from "./TabButton.svelte";
  import Card from "./Card.svelte";
  import type { Candidate } from "$lib/types";

  export let candidate: Candidate;
  
  let expanded = false;
  let activeTab: 'issues' | 'donors' | 'voting' = 'issues';
  
  function toggleExpanded() {
    expanded = !expanded;
  }

  function setActiveTab(tab: 'issues' | 'donors' | 'voting') {
    activeTab = tab;
  }
  
  // Generate a URL-safe ID from candidate name
  function generateCandidateId(name: string): string {
    return name.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  }
</script>

<Card class="candidate-card group" id={generateCandidateId(candidate.name)}>
  <!-- Candidate Header -->
  <div class="mb-6">
    <div class="flex items-start justify-between mb-3">
      <h3 class="candidate-name">
        {candidate.name}
        <!-- Permalink anchor -->
        <a 
          href="#{generateCandidateId(candidate.name)}" 
          class="permalink-anchor"
          aria-label="Link to {candidate.name}"
          title="Link to this candidate"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
        </a>
      </h3>
      <div class="flex flex-col items-end gap-1">
        {#if candidate.party}
          <span class="badge party-badge">{candidate.party}</span>
        {/if}
        {#if candidate.incumbent}
          <span class="badge incumbent-badge">Incumbent</span>
        {/if}
      </div>
    </div>

    <!-- Summary -->
    <p class="summary">
      {expanded ? candidate.summary : candidate.summary.slice(0, 150) + (candidate.summary.length > 150 ? '...' : '')}
    </p>

    <!-- Website Link - Only show when expanded -->
    {#if expanded && candidate.website}
      <div class="mt-3">
        <a
          href={candidate.website}
          target="_blank"
          rel="noopener noreferrer"
          class="website-link"
        >
          Official Website
          <svg
            class="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
            />
          </svg>
        </a>
      </div>
    {/if}
    
    <!-- Expand/Collapse Button -->
    <div class="mt-4">
      <button 
        class="expand-button"
        on:click={toggleExpanded}
        aria-expanded={expanded}
        aria-label={expanded ? 'Collapse candidate details' : 'Expand candidate details'}
      >
        <span class="expand-text">
          {expanded ? 'Show Less' : 'Show More'}
        </span>
        <svg 
          class="expand-icon" 
          class:expanded
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path 
            stroke-linecap="round" 
            stroke-linejoin="round" 
            stroke-width="2" 
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>
    </div>
  </div>

  <!-- Expanded Content - Only show when expanded -->
  {#if expanded}
    <div class="expanded-content">
      <!-- Tab Navigation -->
      <div class="tab-navigation">
        <TabButton 
          active={activeTab === 'issues'} 
          onClick={() => setActiveTab('issues')}
        >
          Key Issues
        </TabButton>
        <TabButton 
          active={activeTab === 'donors'} 
          onClick={() => setActiveTab('donors')}
        >
          Top Donors ({candidate.top_donors.length})
        </TabButton>
        <TabButton 
          active={activeTab === 'voting'} 
          onClick={() => setActiveTab('voting')}
          disabled={!candidate.voting_record || candidate.voting_record.length === 0}
        >
          Voting Record
          {#if candidate.voting_record && candidate.voting_record.length > 0}
            ({candidate.voting_record.length})
          {/if}
        </TabButton>
      </div>

      <!-- Tab Content -->
      <div class="tab-content">
        {#if activeTab === 'issues'}
          <IssueTable issues={candidate.issues} />
        {:else if activeTab === 'donors'}
          <DonorTable donors={candidate.top_donors} />
        {:else if activeTab === 'voting'}
          <VotingRecordTable votingRecord={candidate.voting_record || []} />
        {/if}
      </div>
    </div>
  {:else}
    <!-- Condensed Issues Preview -->
    <div class="issues-preview">
      <h4 class="section-title">Key Issues Preview</h4>
      <div class="issues-tags">
        {#each Object.keys(candidate.issues).slice(0, 4) as issue}
          <span class="issue-tag">{issue}</span>
        {/each}
        {#if Object.keys(candidate.issues).length > 4}
          <span class="issue-tag more-tag">+{Object.keys(candidate.issues).length - 4} more</span>
        {/if}
      </div>
    </div>
  {/if}
</Card>

<style lang="postcss">
  :global(.candidate-card) {
    @apply p-3 sm:p-4 lg:p-6 h-full w-full mx-auto shadow-lg;
  }

  .candidate-name {
    @apply text-lg sm:text-xl lg:text-2xl font-bold text-gray-900;
    @apply flex items-center gap-2;
  }

  .permalink-anchor {
    @apply opacity-0 text-gray-400 transition-opacity duration-200;
  }

  .permalink-anchor:hover {
    @apply text-blue-600;
  }

  :global(.candidate-card.group:hover) .permalink-anchor {
    @apply opacity-100;
  }

  .badge {
    @apply px-2 sm:px-3 py-1 rounded-full text-xs sm:text-sm font-medium;
  }

  .party-badge {
    @apply bg-blue-100 text-blue-800;
  }

  .incumbent-badge {
    @apply bg-green-100 text-green-800;
  }

  .summary {
    @apply text-gray-700 leading-relaxed text-xs sm:text-sm lg:text-base;
  }

  .website-link {
    @apply inline-flex items-center gap-1 text-blue-600 font-medium;
  }

  .website-link:hover {
    @apply text-blue-800;
  }

  .section-title {
    @apply text-base sm:text-lg font-semibold text-gray-900 mb-3 sm:mb-4;
  }

  .expand-button {
    @apply flex items-center gap-2 text-blue-600 font-medium;
    @apply transition-colors duration-200;
  }

  .expand-button:hover {
    @apply text-blue-800;
  }

  .expand-text {
    @apply text-xs sm:text-sm font-medium;
  }

  .expand-icon {
    @apply w-4 h-4 transition-transform duration-200;
  }

  .expand-icon.expanded {
    @apply rotate-180;
  }

  .expanded-content {
    @apply border-t border-gray-200 pt-4 sm:pt-6;
  }

  .tab-navigation {
    @apply flex border-b border-gray-200 mb-6;
  }

  .tab-content {
    @apply min-h-32;
  }

  .issues-preview {
    @apply border-t border-gray-200 pt-4 sm:pt-6;
  }

  .issues-tags {
    @apply flex flex-wrap gap-1 sm:gap-2;
  }

  .issue-tag {
    @apply bg-gray-100 text-gray-700 px-2 sm:px-3 py-1 rounded-full;
    @apply text-xs sm:text-sm font-medium;
  }

  .more-tag {
    @apply bg-blue-100 text-blue-700;
  }
</style>
