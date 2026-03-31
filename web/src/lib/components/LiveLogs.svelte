<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { LogEntry } from "$lib/types";
  import { getLogClass } from "$lib/utils/pipelineUtils";

  export let logs: LogEntry[] = [];
  export let logFilter: "all" | "debug" | "info" | "warning" | "error" = "all";
  export let connected = false;

  const dispatch = createEventDispatcher<{
    "filter-change": "all" | "debug" | "info" | "warning" | "error";
    "clear-logs": void;
  }>();

  $: filteredLogs = logs.filter(
    (log) => logFilter === "all" || log.level === logFilter
  );

  function handleFilterChange(event: Event) {
    const value = (event.target as HTMLSelectElement).value as typeof logFilter;
    dispatch("filter-change", value);
  }

  function clearLogs() {
    dispatch("clear-logs");
  }
</script>

<div class="card p-0 flex flex-col h-96">
  <div class="p-4 border-b border-stroke flex items-center justify-between">
    <div class="flex items-center space-x-3">
      <h3 class="text-lg font-semibold text-content">Live Logs</h3>
      <div class="flex items-center space-x-2">
        <div
          class="w-2 h-2 rounded-full {connected
            ? 'bg-green-500'
            : 'bg-red-500'} pulse-dot"
        />
        <span class="text-xs text-content-subtle"
          >{connected ? "Live" : "Disconnected"}</span
        >
      </div>
    </div>
    <div class="flex space-x-2">
      <select
        bind:value={logFilter}
        on:change={handleFilterChange}
        class="text-xs px-2 py-1 border border-stroke rounded bg-surface text-content"
      >
        <option value="all">All Levels</option>
        <option value="debug">Debug</option>
        <option value="info">Info</option>
        <option value="warning">Warning</option>
        <option value="error">Error</option>
      </select>
      <button
        on:click={clearLogs}
        class="text-xs px-2 py-1 text-content-muted hover:text-content"
      >
        Clear
      </button>
    </div>
  </div>

  <div class="flex-1 overflow-auto custom-scrollbar bg-surface-alt">
    <div class="min-h-full">
      {#each filteredLogs as log}
        <div class="log-line {getLogClass(log.level)}">
          <span class="text-content-subtle">
            [{new Date(log.timestamp).toLocaleTimeString()}]
          </span>
          <span class="font-medium">[{log.level.toUpperCase()}]</span>
          {log.message}
        </div>
      {/each}
      {#if filteredLogs.length === 0}
        <div class="p-4 text-center text-content-subtle text-sm">No logs yet</div>
      {/if}
    </div>
  </div>
</div>

<style>
  .log-line {
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 11px;
    padding: 6px 12px;
    border-bottom: 1px solid rgb(var(--sv-border));
    line-height: 1.5;
    white-space: pre-wrap;
    border-left: 4px solid transparent;
  }

  .pulse-dot {
    animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }

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
