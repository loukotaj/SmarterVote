<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { RunHistoryItem } from '$lib/types';
  import { getStatusClass } from '$lib/utils/pipelineUtils';
  
  export let runHistory: RunHistoryItem[] = [];
  export let selectedRunId = '';
  export let isRefreshing = false;
  
  const dispatch = createEventDispatcher<{
    'run-select': RunHistoryItem;
    'run-details': RunHistoryItem;
    'refresh': void;
  }>();
  
  function handleRunSelect(run: RunHistoryItem) {
    dispatch('run-select', run);
  }
  
  function handleRunDetails(run: RunHistoryItem, event: Event) {
    event.stopPropagation();
    dispatch('run-details', run);
  }
  
  function handleRefresh() {
    dispatch('refresh');
  }
</script>

<div class="card p-0">
  <div class="p-4 border-b border-gray-200 flex items-center justify-between">
    <h3 class="text-lg font-semibold text-gray-900">Recent Runs</h3>
    <button
      on:click={handleRefresh}
      disabled={isRefreshing}
      class="text-sm text-blue-600 hover:text-blue-800 disabled:text-gray-400 flex items-center space-x-1"
    >
      {#if isRefreshing}
        <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      {/if}
      <span>Refresh</span>
    </button>
  </div>
  
  <div class="divide-y divide-gray-200 max-h-64 overflow-auto custom-scrollbar">
    {#each runHistory.slice(0, 10) as run}
      <button
        type="button"
        class="w-full text-left p-4 transition-colors duration-200 {selectedRunId === run.run_id
          ? 'bg-blue-50 border-l-4 border-l-blue-500'
          : 'hover:bg-gray-50'}"
        on:click={() => handleRunSelect(run)}
      >
        <div class="flex items-center justify-between">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <div class="text-sm font-medium text-gray-900">
                Run {run.display_id}
              </div>
              {#if selectedRunId === run.run_id}
                <div class="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0" title="Currently selected"></div>
              {/if}
            </div>
            <div class="text-xs text-gray-600 truncate">
              {run.last_step || "Unknown Step"}
            </div>
            <div class="text-xs text-gray-500">
              {new Date(run.started_at).toLocaleString()}
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span
              class="px-2 py-1 rounded-full text-xs font-medium flex-shrink-0 {getStatusClass(run.status || 'unknown')}"
            >
              {(run.status || "unknown").charAt(0).toUpperCase() +
                (run.status || "unknown").slice(1)}
            </span>
            <button
              type="button"
              class="px-2 py-1 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
              on:click={(event) => handleRunDetails(run, event)}
              title="View run details"
            >
              Details
            </button>
          </div>
        </div>
      </button>
    {:else}
      <div class="p-4 text-center text-gray-500 text-sm">No runs yet</div>
    {/each}
  </div>
</div>

<style>
  .custom-scrollbar::-webkit-scrollbar { 
    width: 6px; 
  }
  
  .custom-scrollbar::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 3px;
  }
  
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;
  }
  
  .custom-scrollbar::-webkit-scrollbar-thumb:hover { 
    background: #94a3b8; 
  }
</style>