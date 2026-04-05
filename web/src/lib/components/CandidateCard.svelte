<script lang="ts">
  import IssueTable from "./IssueTable.svelte";
  import DonorTable from "./DonorTable.svelte";
  import VotingRecordTable from "./VotingRecordTable.svelte";
  import TabButton from "./TabButton.svelte";
  import Card from "./Card.svelte";
  import type { Candidate } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";
  import { partyAbbr, partyBadgeClass } from "$lib/utils/party";

  export let candidate: Candidate;
  export let raceId: string = "";
  export let draft: boolean = false;

  $: draftQuery = draft ? "?draft=true" : "";

  let expanded = false;
  let imageError = false;
  let activeTab: "issues" | "background" | "donors" | "voting" = "issues";

  function toggleExpanded() {
    expanded = !expanded;
  }

  function setActiveTab(tab: "issues" | "background" | "donors" | "voting") {
    activeTab = tab;
  }

  // Generate a URL-safe ID from candidate name
  function generateCandidateId(name: string): string {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "");
  }

  $: hasCareer =
    candidate.career_history && candidate.career_history.length > 0;
  $: hasEducation = candidate.education && candidate.education.length > 0;
  $: hasBackground = hasCareer || hasEducation;
  $: hasVoting = !!candidate.voting_summary;
  $: hasDonors = !!candidate.donor_summary;
</script>

<Card class="candidate-card group" id={generateCandidateId(candidate.name)}>
  <!-- Candidate Header -->
  <div class="mb-6">
    <div class="flex items-start justify-between mb-3">
      <div class="flex items-start gap-4">
        <!-- Candidate Image -->
        {#if candidate.image_url && !imageError}
          <img
            src={candidate.image_url}
            alt={candidate.name}
            class="candidate-image"
            on:error={() => { imageError = true; }}
          />
        {:else}
          <div class="candidate-image-placeholder">
            <span class="candidate-initials">
              {candidate.name.split(' ').filter(n => n.length > 0).map(n => n[0].toUpperCase()).slice(0, 2).join('')}
            </span>
          </div>
        {/if}
        <div>
          <h3 class="candidate-name">
            <a
              href="/races/{raceId}/{candidateSlug(candidate.name)}{draftQuery}"
              class="candidate-name-link"
            >
              {candidate.name}
              <svg class="inline w-4 h-4 ml-1 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </h3>
          <div class="flex flex-wrap items-center gap-1 mt-1">
            {#if candidate.party}
              <span class="badge {partyBadgeClass(candidate.party)}" title={candidate.party}>{partyAbbr(candidate.party)}</span>
            {/if}
            {#if candidate.incumbent}
              <span class="badge incumbent-badge">Incumbent</span>
            {/if}
          </div>
        </div>
      </div>
    </div>

    <!-- Summary -->
    <p class="summary">
      {expanded
        ? candidate.summary
        : candidate.summary.slice(0, 600) +
          (candidate.summary.length > 600 ? "..." : "")}
    </p>

    <!-- Website Link -->
    {#if candidate.website}
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
        aria-label={expanded
          ? "Collapse candidate details"
          : "Expand candidate details"}
      >
        <span class="expand-text">
          {expanded ? "Show Less" : "Show More"}
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
          active={activeTab === "issues"}
          onClick={() => setActiveTab("issues")}
        >
          Key Issues
        </TabButton>
        <TabButton
          active={activeTab === "background"}
          onClick={() => setActiveTab("background")}
          disabled={!hasBackground}
        >
          Background
        </TabButton>
        <TabButton
          active={activeTab === "donors"}
          onClick={() => setActiveTab("donors")}
          disabled={!hasDonors}
        >
          Donors
        </TabButton>
        <TabButton
          active={activeTab === "voting"}
          onClick={() => setActiveTab("voting")}
          disabled={!hasVoting}
        >
          Voting Record
        </TabButton>
      </div>

      <!-- Tab Content -->
      <div class="tab-content">
        {#if activeTab === "issues"}
          <IssueTable
            issues={candidate.issues}
            {raceId}
            candidateName={candidate.name}
          />
        {:else if activeTab === "background"}
          <div class="background-section">
            {#if hasCareer}
              <div class="mb-6">
                <h4 class="section-title">Career History</h4>
                <div class="timeline">
                  {#each candidate.career_history as entry}
                    <div class="timeline-entry">
                      <div class="timeline-header">
                        <span class="timeline-title">{entry.title}</span>
                        {#if entry.start_year}
                          <span class="timeline-years">
                            {entry.start_year}{entry.end_year
                              ? ` – ${entry.end_year}`
                              : " – Present"}
                          </span>
                        {/if}
                      </div>
                      {#if entry.organization}
                        <span class="timeline-org">{entry.organization}</span>
                      {/if}
                      {#if entry.description}
                        <p class="timeline-desc">{entry.description}</p>
                      {/if}
                      {#if entry.source}
                        <a href={entry.source.url} target="_blank" rel="noopener noreferrer" class="entry-source-link">
                          <svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                          {entry.source.title ?? 'Source'}
                        </a>
                      {/if}
                    </div>
                  {/each}
                </div>
              </div>
            {/if}
            {#if hasEducation}
              <div>
                <h4 class="section-title">Education</h4>
                <div class="education-list">
                  {#each candidate.education as edu}
                    <div class="education-entry">
                      <span class="edu-institution">{edu.institution}</span>
                      {#if edu.degree || edu.field}
                        <span class="edu-degree">
                          {[edu.degree, edu.field]
                            .filter(Boolean)
                            .join(" in ")}
                          {#if edu.year}
                            ({edu.year})
                          {/if}
                        </span>
                      {/if}
                      {#if edu.source}
                        <a href={edu.source.url} target="_blank" rel="noopener noreferrer" class="entry-source-link">
                          <svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                          {edu.source.title ?? 'Source'}
                        </a>
                      {/if}
                    </div>
                  {/each}
                </div>
              </div>
            {/if}
            {#if !hasBackground}
              <p class="text-content-subtle text-sm">
                No background information available yet.
              </p>
            {/if}
          </div>
        {:else if activeTab === "donors"}
          <DonorTable
            donorSummary={candidate.donor_summary || ''}
            donorSourceUrl={candidate.donor_source_url || ''}
            {raceId}
            candidateName={candidate.name}
          />
        {:else if activeTab === "voting"}
          <VotingRecordTable
            votingSummary={candidate.voting_summary || ''}
            votingSourceUrl={candidate.voting_source_url || ''}
            {raceId}
            candidateName={candidate.name}
          />
        {/if}
      </div>
    </div>
  {/if}
</Card>

<style lang="postcss">
  :global(.candidate-card) {
    @apply p-3 sm:p-4 lg:p-6 h-full w-full mx-auto shadow-lg;
  }

  .candidate-image {
    @apply w-16 h-16 sm:w-20 sm:h-20 rounded-full object-cover border-2 border-stroke flex-shrink-0;
  }

  .candidate-image-placeholder {
    @apply w-16 h-16 sm:w-20 sm:h-20 rounded-full bg-blue-100 dark:bg-blue-900 border-2 border-blue-200 dark:border-blue-700 flex items-center justify-center flex-shrink-0;
  }

  .candidate-initials {
    @apply text-blue-700 dark:text-blue-300 font-bold text-lg sm:text-xl select-none;
  }

  .candidate-name {
    @apply text-lg sm:text-xl lg:text-2xl font-bold text-content;
    @apply flex items-center gap-2;
  }

  .candidate-name-link {
    @apply text-blue-600 hover:text-blue-500 dark:hover:text-blue-400 hover:underline transition-colors duration-200 no-underline;
  }

  .badge {
    @apply px-2 sm:px-3 py-1 rounded-full text-xs sm:text-sm font-medium;
  }

  .party-badge {
    @apply bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300;
  }

  .incumbent-badge {
    @apply bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200;
  }

  .summary {
    @apply text-content-muted leading-relaxed text-xs sm:text-sm lg:text-base;
  }

  .website-link {
    @apply inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 font-medium;
  }

  .website-link:hover {
    @apply text-blue-500 dark:text-blue-300;
  }

  .section-title {
    @apply text-base sm:text-lg font-semibold text-content mb-3 sm:mb-4;
  }

  .expand-button {
    @apply flex items-center gap-2 text-blue-600 dark:text-blue-400 font-medium;
    @apply transition-colors duration-200;
  }

  .expand-button:hover {
    @apply text-blue-500 dark:text-blue-300;
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
    @apply border-t border-stroke pt-4 sm:pt-6;
  }

  .tab-navigation {
    @apply flex border-b border-stroke mb-6 overflow-x-auto;
  }

  .tab-content {
    @apply min-h-32;
  }

  .issues-preview {
    @apply border-t border-stroke pt-4 sm:pt-6;
  }

  .issues-tags {
    @apply flex flex-wrap gap-1 sm:gap-2;
  }

  .issue-tag {
    @apply bg-surface-alt text-content-muted px-2 sm:px-3 py-1 rounded-full;
    @apply text-xs sm:text-sm font-medium;
  }

  .more-tag {
    @apply bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300;
  }

  /* Background / Career / Education styles */
  .background-section {
    @apply space-y-4;
  }

  .timeline {
    @apply space-y-3;
  }

  .timeline-entry {
    @apply border-l-2 border-blue-200 dark:border-blue-700 pl-4 py-1;
  }

  .timeline-header {
    @apply flex flex-wrap items-baseline gap-2;
  }

  .timeline-title {
    @apply font-medium text-content text-sm;
  }

  .timeline-years {
    @apply text-xs text-content-subtle;
  }

  .timeline-org {
    @apply text-sm text-content-muted block;
  }

  .timeline-desc {
    @apply text-xs text-content-subtle mt-1;
  }

  .entry-source-link {
    @apply inline-flex items-center gap-1 mt-2 text-xs text-blue-600 dark:text-blue-400 hover:underline;
  }

  .education-list {
    @apply space-y-2;
  }

  .education-entry {
    @apply flex flex-col;
  }

  .edu-institution {
    @apply font-medium text-content text-sm;
  }

  .edu-degree {
    @apply text-xs text-content-muted;
  }
</style>
