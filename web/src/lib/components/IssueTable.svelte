<script lang="ts">
  import ConfidenceIndicator from "./ConfidenceIndicator.svelte";
  import SourceLink from "./SourceLink.svelte";
  import NoDataFallback from "./NoDataFallback.svelte";
  import type { IssueKey, IssueStance } from "$lib/types";
  import { RENAMED_ISSUE_NOTES, getIssueDisplayName } from "$lib/types";

  export let issues: Partial<Record<IssueKey, IssueStance>>;
  export let raceId: string = "";
  export let candidateName: string = "";

  const INITIAL_SOURCE_LIMIT = 3;

  $: issueEntries = Object.entries(issues) as [IssueKey, IssueStance][];
  $: hasIssues = issueEntries.length > 0;

  let expandedSources: Set<string> = new Set();
  let visibleTooltip: string | null = null;

  function toggleSources(issue: string) {
    const next = new Set(expandedSources);
    if (next.has(issue)) {
      next.delete(issue);
    } else {
      next.add(issue);
    }
    expandedSources = next;
  }

  function toggleTooltip(issue: string) {
    visibleTooltip = visibleTooltip === issue ? null : issue;
  }

  function visibleSources(stance: IssueStance, expanded: boolean) {
    const sources = stance.sources ?? [];
    return expanded ? sources : sources.slice(0, INITIAL_SOURCE_LIMIT);
  }
</script>

{#if !hasIssues}
  <NoDataFallback dataType="issues" {raceId} {candidateName} />
{:else}
  <div class="hidden lg:block overflow-x-auto">
    <table class="w-full border-collapse">
      <thead>
        <tr class="border-b border-stroke">
          <th class="text-left py-3 px-4 font-semibold text-content">Issue</th>
          <th class="text-left py-3 px-4 font-semibold text-content w-2/5">
            Stance
          </th>
          <th class="text-center py-3 px-4 font-semibold text-content"
            >Confidence</th
          >
          <th class="text-center py-3 px-4 font-semibold text-content"
            >Sources</th
          >
        </tr>
      </thead>
      <tbody>
        {#each issueEntries as [issue, stance]}
          <tr class="border-b border-stroke hover:bg-surface-alt">
            <td class="py-3 px-4 font-medium text-content">
              <span class="inline-flex items-center gap-1">
                {getIssueDisplayName(issue)}
                {#if RENAMED_ISSUE_NOTES[issue]}
                  <span class="relative inline-block">
                    <button
                      class="inline-flex min-h-11 min-w-11 items-center justify-center text-blue-500 hover:text-blue-400 focus:outline-none leading-none"
                      aria-label="About this issue name"
                      title="About this issue name"
                      on:click|stopPropagation={() => toggleTooltip(issue)}
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        class="w-4 h-4"
                      >
                        <path
                          fill-rule="evenodd"
                          d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                          clip-rule="evenodd"
                        />
                      </svg>
                    </button>
                    {#if visibleTooltip === issue}
                      <div
                        class="absolute z-10 left-0 top-11 w-72 rounded-lg border border-stroke bg-surface p-3 shadow-lg text-sm text-content-muted"
                        role="tooltip"
                      >
                        <p>{RENAMED_ISSUE_NOTES[issue]}</p>
                        <button
                          class="mt-2 inline-flex min-h-11 items-center text-xs text-content-faint hover:text-content underline"
                          on:click|stopPropagation={() => {
                            visibleTooltip = null;
                          }}>Dismiss</button
                        >
                      </div>
                    {/if}
                  </span>
                {/if}
              </span>
            </td>
            <td class="py-3 px-4 text-content-muted w-2/5 whitespace-normal">
              {stance.stance}
            </td>
            <td class="py-3 px-4 text-center">
              <ConfidenceIndicator confidence={stance.confidence} />
            </td>
            <td class="py-3 px-4 text-center">
              {#if stance.sources?.length > 0}
                <div class="text-left space-y-1">
                  {#each visibleSources(stance, expandedSources.has(issue)) as source}
                    <div>
                      <SourceLink {source} />
                    </div>
                  {/each}
                </div>
                {#if stance.sources.length > INITIAL_SOURCE_LIMIT}
                  <button
                    class="mt-2 inline-flex min-h-11 items-center text-blue-600 hover:text-blue-500 dark:hover:text-blue-400 text-sm underline"
                    aria-label={expandedSources.has(issue)
                      ? `Show fewer sources for ${getIssueDisplayName(issue)}`
                      : `Show ${
                          stance.sources.length - INITIAL_SOURCE_LIMIT
                        } more sources for ${getIssueDisplayName(issue)}`}
                    title={expandedSources.has(issue)
                      ? "Show fewer sources"
                      : `Show ${
                          stance.sources.length - INITIAL_SOURCE_LIMIT
                        } more sources`}
                    on:click={() => toggleSources(issue)}
                  >
                    {expandedSources.has(issue)
                      ? "Show fewer"
                      : `Show ${
                          stance.sources.length - INITIAL_SOURCE_LIMIT
                        } more`}
                  </button>
                {/if}
              {:else}
                <span class="text-content-faint text-sm">No sources</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <!-- Mobile-friendly view for smaller screens -->
  <div class="lg:hidden space-y-4">
    {#each issueEntries as [issue, stance]}
      <div class="bg-surface border border-stroke rounded-lg p-4">
        <div class="flex items-center justify-between mb-2">
          <h3 class="font-semibold text-content inline-flex items-center gap-1">
            {getIssueDisplayName(issue)}
            {#if RENAMED_ISSUE_NOTES[issue]}
              <span class="relative inline-block">
                <button
                  class="inline-flex min-h-11 min-w-11 items-center justify-center text-blue-500 hover:text-blue-400 focus:outline-none leading-none"
                  aria-label="About this issue name"
                  on:click|stopPropagation={() =>
                    toggleTooltip(issue + "-mobile")}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    class="w-4 h-4"
                  >
                    <path
                      fill-rule="evenodd"
                      d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                      clip-rule="evenodd"
                    />
                  </svg>
                </button>
                {#if visibleTooltip === issue + "-mobile"}
                  <div
                    class="absolute z-10 left-0 top-11 w-64 rounded-lg border border-stroke bg-surface p-3 shadow-lg text-sm text-content-muted"
                    role="tooltip"
                  >
                    <p>{RENAMED_ISSUE_NOTES[issue]}</p>

                    <button
                      class="mt-2 inline-flex min-h-11 items-center text-xs text-content-faint hover:text-content underline"
                      on:click|stopPropagation={() => {
                        visibleTooltip = null;
                      }}>Dismiss</button
                    >
                  </div>
                {/if}
              </span>
            {/if}
          </h3>
          <ConfidenceIndicator confidence={stance.confidence} />
        </div>
        <p class="text-content-muted mb-3">{stance.stance}</p>
        {#if stance.sources?.length > 0}
          <div class="text-sm">
            <span class="text-content-muted">Sources:</span>
            <div class="mt-1 space-y-1">
              {#each visibleSources(stance, expandedSources.has(issue + "-mobile")) as source}
                <div>
                  <SourceLink {source} />
                </div>
              {/each}
            </div>
            {#if stance.sources.length > INITIAL_SOURCE_LIMIT}
              <button
                class="mt-2 inline-flex min-h-11 items-center text-blue-600 hover:text-blue-500 dark:hover:text-blue-400 text-sm underline"
                aria-label={expandedSources.has(issue + "-mobile")
                  ? `Show fewer sources for ${getIssueDisplayName(issue)}`
                  : `Show ${
                      stance.sources.length - INITIAL_SOURCE_LIMIT
                    } more sources for ${getIssueDisplayName(issue)}`}
                on:click={() => toggleSources(issue + "-mobile")}
              >
                {expandedSources.has(issue + "-mobile")
                  ? "Show fewer"
                  : `Show ${stance.sources.length - INITIAL_SOURCE_LIMIT} more`}
              </button>
            {/if}
          </div>
        {:else}
          <p class="text-content-faint text-sm">No sources available</p>
        {/if}
      </div>
    {/each}
  </div>
{/if}
