<script lang="ts">
  import IssueTable from './IssueTable.svelte';
  import type { Candidate } from '$lib/types';
  
  export let candidate: Candidate;
</script>

<div class="bg-white rounded-lg shadow-lg p-6 h-full">
  <!-- Candidate Header -->
  <div class="mb-6">
    <div class="flex items-start justify-between mb-3">
      <h3 class="text-2xl font-bold text-gray-900">{candidate.name}</h3>
      <div class="flex flex-col items-end gap-1">
        {#if candidate.party}
          <span class="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-medium">
            {candidate.party}
          </span>
        {/if}
        {#if candidate.incumbent}
          <span class="bg-green-100 text-green-800 px-3 py-1 rounded-full text-sm font-medium">
            Incumbent
          </span>
        {/if}
      </div>
    </div>
    
    <!-- Summary -->
    <p class="text-gray-700 leading-relaxed">{candidate.summary}</p>
    
    <!-- Website Link -->
    {#if candidate.website}
      <div class="mt-3">
        <a 
          href={candidate.website} 
          target="_blank" 
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 font-medium"
        >
          Official Website
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      </div>
    {/if}
  </div>
  
  <!-- Issues Section -->
  <div>
    <h4 class="text-lg font-semibold text-gray-900 mb-4">Issue Positions</h4>
    <IssueTable issues={candidate.issues} />
  </div>
</div>
