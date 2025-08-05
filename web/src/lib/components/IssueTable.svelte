<script lang="ts">
  import ConfidenceIndicator from "./ConfidenceIndicator.svelte";
  import SourceLink from "./SourceLink.svelte";
  import type { CanonicalIssue, IssueStance } from "$lib/types";

  export let issues: Record<CanonicalIssue, IssueStance>;

  $: issueEntries = Object.entries(issues) as [CanonicalIssue, IssueStance][];
</script>

<div class="hidden lg:block overflow-x-auto">
  <table class="w-full border-collapse">
    <thead>
      <tr class="border-b border-gray-200">
        <th class="text-left py-3 px-4 font-semibold text-gray-900">Issue</th>
        <th class="text-left py-3 px-4 font-semibold text-gray-900 w-2/5">
          Stance
        </th>
        <th class="text-center py-3 px-4 font-semibold text-gray-900"
          >Confidence</th
        >
        <th class="text-center py-3 px-4 font-semibold text-gray-900"
          >Sources</th
        >
      </tr>
    </thead>
    <tbody>
      {#each issueEntries as [issue, stance]}
        <tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="py-3 px-4 font-medium text-gray-900">{issue}</td>
          <td class="py-3 px-4 text-gray-700 w-2/5 whitespace-normal">
            {stance.stance}
          </td>
          <td class="py-3 px-4 text-center">
            <ConfidenceIndicator confidence={stance.confidence} />
          </td>
          <td class="py-3 px-4 text-center">
            {#if stance.sources.length > 0}
              <button
                class="text-blue-600 hover:text-blue-800 text-sm underline"
                title="View {stance.sources.length} source{stance.sources
                  .length > 1
                  ? 's'
                  : ''}"
              >
                View Sources ({stance.sources.length})
              </button>
            {:else}
              <span class="text-gray-400 text-sm">No sources</span>
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
    <div class="bg-white border border-gray-200 rounded-lg p-4">
      <div class="flex items-center justify-between mb-2">
        <h4 class="font-semibold text-gray-900">{issue}</h4>
        <ConfidenceIndicator confidence={stance.confidence} />
      </div>
      <p class="text-gray-700 mb-3">{stance.stance}</p>
      {#if stance.sources.length > 0}
        <div class="text-sm">
          <span class="text-gray-600">Sources:</span>
          <div class="mt-1 space-y-1">
            {#each stance.sources as source}
              <div>
                <SourceLink {source} />
              </div>
            {/each}
          </div>
        </div>
      {:else}
        <p class="text-gray-400 text-sm">No sources available</p>
      {/if}
    </div>
  {/each}
</div>
