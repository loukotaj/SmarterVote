<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { RunHistoryItem } from "$lib/types";
  import { getStatusClass } from "$lib/utils/pipelineUtils";

  export let runHistory: RunHistoryItem[] = [];
  export let selectedRunId = "";
  export let isRefreshing = false;

  const dispatch = createEventDispatcher<{
    "run-select": RunHistoryItem;
    "run-details": RunHistoryItem;
    refresh: void;
  }>();

  function handleRunSelect(run: RunHistoryItem) {
    dispatch("run-select", run);
  }

  function handleRunDetails(run: RunHistoryItem, event: Event) {
    event.stopPropagation();
    dispatch("run-details", run);
  }

  function handleRefresh() {
    dispatch("refresh");
  }

  function raceId(run: RunHistoryItem): string {
    return (run.payload?.race_id as string) ?? `run-${run.display_id}`;
  }

  function modelLabel(run: RunHistoryItem): string {
    if (run.options?.research_model) return String(run.options.research_model);
    if (run.options?.cheap_mode === false) return "full";
    return "mini";
  }

  function formatDuration(ms?: number): string {
    if (!ms) return "";
    if (ms < 60000) return `${Math.round(ms / 1000)}s`;
    const m = Math.floor(ms / 60000);
    const s = Math.round((ms % 60000) / 1000);
    return s ? `${m}m ${s}s` : `${m}m`;
  }

  function timeAgo(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 90000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }
</script>

<div class="card p-0">
  <div class="px-4 py-3 border-b border-stroke flex items-center justify-between">
    <h3 class="text-sm font-semibold text-content">Recent Runs</h3>
    <button
      on:click={handleRefresh}
      disabled={isRefreshing}
      class="text-xs text-blue-600 hover:text-blue-500 disabled:text-content-faint flex items-center gap-1"
    >
      {#if isRefreshing}
        <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      {/if}
      <span>Refresh</span>
    </button>
  </div>

  <div class="divide-y divide-stroke max-h-72 overflow-auto custom-scrollbar">
    {#each runHistory.slice(0, 20) as run}
      <button
        type="button"
        class="w-full text-left px-4 py-2.5 transition-colors duration-150 {selectedRunId === run.run_id
          ? 'bg-blue-100 dark:bg-blue-900/20 border-l-2 border-l-blue-500'
          : 'hover:bg-surface-alt'}"
        on:click={() => handleRunSelect(run)}
      >
        <div class="flex items-center gap-2">
          <span class="text-xs font-mono font-medium text-content flex-1 truncate" title={raceId(run)}>
            {raceId(run)}
          </span>
          <span class="text-xs px-1.5 py-0.5 rounded-full flex-shrink-0 {getStatusClass(run.status || 'unknown')}">
            {run.status ?? "unknown"}
          </span>
          <button
            type="button"
            class="text-content-faint hover:text-content-muted flex-shrink-0 text-xs"
            on:click={(e) => handleRunDetails(run, e)}
            title="View run details"
          >↗</button>
        </div>
        <div class="flex items-center gap-2 mt-0.5 text-xs text-content-faint">
          <span>{timeAgo(run.started_at)}</span>
          {#if run.duration_ms}
            <span>· {formatDuration(run.duration_ms)}</span>
          {/if}
          <span class="ml-auto font-mono">{modelLabel(run)}</span>
        </div>
      </button>
    {:else}
      <div class="p-4 text-center text-content-subtle text-sm">No runs yet</div>
    {/each}
  </div>
</div>

<style>
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }

  .custom-scrollbar::-webkit-scrollbar-track {
    background: rgb(var(--sv-surface-alt));
    border-radius: 3px;
  }

  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgb(var(--sv-border));
    border-radius: 3px;
  }

  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgb(var(--sv-text-faint));
  }
</style>
