<script lang="ts">
  import IssueTable from "./IssueTable.svelte";
  import DonorTable from "./DonorTable.svelte";
  import VotingRecordTable from "./VotingRecordTable.svelte";
  import TabButton from "./TabButton.svelte";
  import Card from "./Card.svelte";
  import type { Candidate } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";

  export let candidate: Candidate;
  export let raceId: string = "";

  let expanded = false;
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
  $: hasVoting =
    candidate.voting_record && candidate.voting_record.length > 0;
</script>

<Card class="candidate-card group" id={generateCandidateId(candidate.name)}>
  <!-- Candidate Header -->
  <div class="mb-6">
    <div class="flex items-start justify-between mb-3">
      <div class="flex items-start gap-4">
        <!-- Candidate Image -->
        {#if candidate.image_url}
          <img
            src={candidate.image_url}
            alt={candidate.name}
            class="candidate-image"
            on:error={(e) => {
              const target = e.currentTarget;
              if (target instanceof HTMLImageElement) {
                target.style.display = "none";
              }
            }}
          />
        {:else}
          <div class="candidate-image-placeholder">
            <svg
              class="w-8 h-8 text-gray-400"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"
              />
            </svg>
          </div>
        {/if}
        <div>
          <h3 class="candidate-name">
            <a
              href="/races/{raceId}/{candidateSlug(candidate.name)}"
              class="candidate-name-link"
            >
              {candidate.name}
            </a>
          </h3>
          <div class="flex flex-wrap items-center gap-1 mt-1">
            {#if candidate.party}
              <span class="badge party-badge">{candidate.party}</span>
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
        : candidate.summary.slice(0, 150) +
          (candidate.summary.length > 150 ? "..." : "")}
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
        >
          Top Donors ({candidate.top_donors?.length ?? 0})
        </TabButton>
        <TabButton
          active={activeTab === "voting"}
          onClick={() => setActiveTab("voting")}
          disabled={!hasVoting}
        >
          Voting Record
          {#if hasVoting}
            ({candidate.voting_record.length})
          {/if}
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
                    </div>
                  {/each}
                </div>
              </div>
            {/if}
            {#if !hasBackground}
              <p class="text-gray-500 text-sm">
                No background information available yet.
              </p>
            {/if}
          </div>
        {:else if activeTab === "donors"}
          <DonorTable
            donors={candidate.top_donors}
            {raceId}
            candidateName={candidate.name}
          />
        {:else if activeTab === "voting"}
          <VotingRecordTable
            votingRecord={candidate.voting_record || []}
            {raceId}
            candidateName={candidate.name}
          />
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
          <span class="issue-tag more-tag"
            >+{Object.keys(candidate.issues).length - 4} more</span
          >
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
    @apply w-16 h-16 sm:w-20 sm:h-20 rounded-full object-cover border-2 border-gray-200 flex-shrink-0;
  }

  .candidate-image-placeholder {
    @apply w-16 h-16 sm:w-20 sm:h-20 rounded-full bg-gray-100 border-2 border-gray-200 flex items-center justify-center flex-shrink-0;
  }

  .candidate-name {
    @apply text-lg sm:text-xl lg:text-2xl font-bold text-gray-900;
    @apply flex items-center gap-2;
  }

  .candidate-name-link {
    @apply text-gray-900 hover:text-blue-600 transition-colors duration-200 no-underline;
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
    @apply flex border-b border-gray-200 mb-6 overflow-x-auto;
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

  /* Background / Career / Education styles */
  .background-section {
    @apply space-y-4;
  }

  .timeline {
    @apply space-y-3;
  }

  .timeline-entry {
    @apply border-l-2 border-blue-200 pl-4 py-1;
  }

  .timeline-header {
    @apply flex flex-wrap items-baseline gap-2;
  }

  .timeline-title {
    @apply font-medium text-gray-900 text-sm;
  }

  .timeline-years {
    @apply text-xs text-gray-500;
  }

  .timeline-org {
    @apply text-sm text-gray-600 block;
  }

  .timeline-desc {
    @apply text-xs text-gray-500 mt-1;
  }

  .education-list {
    @apply space-y-2;
  }

  .education-entry {
    @apply flex flex-col;
  }

  .edu-institution {
    @apply font-medium text-gray-900 text-sm;
  }

  .edu-degree {
    @apply text-xs text-gray-600;
  }
</style>
