<script lang="ts">
  import ConfidenceIndicator from "./ConfidenceIndicator.svelte";
  import SourceLink from "./SourceLink.svelte";
  import NoDataFallback from "./NoDataFallback.svelte";
  import type { CanonicalIssue, IssueStance } from "$lib/types";

  export let issues: Record<CanonicalIssue, IssueStance>;
  export let raceId: string = "";
  export let candidateName: string = "";

  $: issueEntries = Object.entries(issues) as [CanonicalIssue, IssueStance][];
  $: hasIssues = issueEntries.length > 0;

  let expandedSources: Set<string> = new Set();

  function toggleSources(issue: string) {
    const next = new Set(expandedSources);
    if (next.has(issue)) {
      next.delete(issue);
    } else {
      next.add(issue);
    }
    expandedSources = next;
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
            <td class="py-3 px-4 font-medium text-content">{issue}</td>
            <td class="py-3 px-4 text-content-muted w-2/5 whitespace-normal">
              {stance.stance}
            </td>
            <td class="py-3 px-4 text-center">
              <ConfidenceIndicator confidence={stance.confidence} />
            </td>
            <td class="py-3 px-4 text-center">
              {#if stance.sources.length > 0}
                <button
                  class="text-blue-600 hover:text-blue-500 dark:hover:text-blue-400 text-sm underline"
                  title="{expandedSources.has(issue) ? 'Hide' : 'View'} {stance.sources.length} source{stance.sources.length > 1 ? 's' : ''}"
                  on:click={() => toggleSources(issue)}
                >
                  {expandedSources.has(issue) ? "Hide" : "View"} Sources ({stance.sources.length})
                </button>
                {#if expandedSources.has(issue)}
                  <div class="mt-2 text-left space-y-1">
                    {#each stance.sources as source}
                      <div>
                        <SourceLink {source} />
                      </div>
                    {/each}
                  </div>
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
          <h4 class="font-semibold text-content">{issue}</h4>
          <ConfidenceIndicator confidence={stance.confidence} />
        </div>
        <p class="text-content-muted mb-3">{stance.stance}</p>
        {#if stance.sources.length > 0}
          <div class="text-sm">
            <span class="text-content-muted">Sources:</span>
            <div class="mt-1 space-y-1">
              {#each stance.sources as source}
                <div>
                  <SourceLink {source} />
                </div>
              {/each}
            </div>
          </div>
        {:else}
          <p class="text-content-faint text-sm">No sources available</p>
        {/if}
      </div>
    {/each}
  </div>
{/if}
