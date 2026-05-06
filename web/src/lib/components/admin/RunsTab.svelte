<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { getStatusClass } from "$lib/utils/pipelineUtils";
  import type { RunHistoryItem } from "$lib/types";
  import type { QueueItem } from "$lib/services/pipelineApiService";

  export let runs: RunHistoryItem[] = [];
  export let queueItems: QueueItem[] = [];
  export let isRefreshing = false;
  export let currentRunId: string | null = null;

  // cleared externally resets local clearing state
  $: if (!pendingQueue.length) clearingQueue = false;

  const dispatch = createEventDispatcher<{
    "view-run": { runId: string; raceId: string | null };
    refresh: void;
    "clear-queue": void;
    "delete-item": { itemId?: string; runId?: string };
  }>();

  let clearingQueue = false;

  // Runs stuck in "running" state for more than 15 min have likely timed out.
  const STUCK_MS = 15 * 60 * 1000;

  async function handleClearQueue() {
    if (!confirm(`Remove all ${pendingQueue.length} pending item${pendingQueue.length !== 1 ? 's' : ''} from the queue?`)) return;
    clearingQueue = true;
    dispatch("clear-queue");
  }

  function handleViewRun(runId: string, raceId: string | null = null) {
    dispatch("view-run", { runId, raceId });
  }

  function handleDeleteItem(id: string, type: "queue" | "run") {
    if (type === "queue") dispatch("delete-item", { itemId: id });
    else dispatch("delete-item", { runId: id });
  }

  function timeAgo(iso: string): string {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 90000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }

  function elapsedSince(iso: string | undefined): string {
    if (!iso) return "";
    const ms = Date.now() - new Date(iso).getTime();
    if (!Number.isFinite(ms) || ms < 0) return "";
    const totalSec = Math.floor(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  function formatMs(ms?: number): string {
    if (!ms) return "";
    if (ms < 60000) return `${Math.round(ms / 1000)}s`;
    const m = Math.floor(ms / 60000);
    const s = Math.round((ms % 60000) / 1000);
    return s ? `${m}m ${s}s` : `${m}m`;
  }

  function raceId(run: RunHistoryItem | QueueItem): string {
    if ("payload" in run) return (run.payload?.race_id as string) ?? run.run_id ?? "—";
    return run.race_id ?? "—";
  }

  function modelLabel(run: RunHistoryItem): string {
    if (run.options?.research_model) return String(run.options.research_model);
    if (run.options?.cheap_mode === false) return "full";
    return "mini";
  }

  function payloadRaceId(run: RunHistoryItem): string | null {
    const id = run.payload?.race_id;
    return typeof id === "string" && id ? id : null;
  }

  function isLikelyStuck(run: RunHistoryItem): boolean {
    if (run.status !== "running" && run.status !== "pending") return false;
    const startMs = run.started_at ? Date.parse(run.started_at) : NaN;
    return Number.isFinite(startMs) && Date.now() - startMs > STUCK_MS;
  }

  $: liveRunIds = new Set(
    queueItems.filter((q) => q.status === "running" || q.status === "pending").map((q) => q.run_id).filter(Boolean)
  );

  $: activeRuns = runs.filter(
    (r) => r.status === "running" || r.status === "pending" || liveRunIds.has(r.run_id)
  );
  $: pendingQueue = queueItems.filter((q) => q.status === "pending");
  $: historicalRuns = runs.filter(
    (r) => r.status !== "running" && r.status !== "pending" && !liveRunIds.has(r.run_id)
  );
</script>

<div class="space-y-6">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <div>
      <h2 class="text-lg font-semibold text-content">All Runs</h2>
      <p class="text-xs text-content-muted mt-0.5">
        {runs.length} run{runs.length !== 1 ? "s" : ""}{pendingQueue.length > 0 ? ` · ${pendingQueue.length} queued` : ""}
      </p>
    </div>
    <div class="flex items-center gap-2">
      {#if pendingQueue.length > 0}
        <button
          on:click={handleClearQueue}
          disabled={clearingQueue}
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
        >
          {#if clearingQueue}
            <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          {:else}
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          {/if}
          Clear Queue ({pendingQueue.length})
        </button>
      {/if}
      <button
        on:click={() => dispatch("refresh")}
        disabled={isRefreshing}
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-stroke text-content-muted hover:text-content hover:bg-surface-alt disabled:opacity-50 transition-colors"
      >
      {#if isRefreshing}
        <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      {:else}
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      {/if}
      Refresh
    </button>
  </div>
  </div>

  <!-- Active / running runs -->
  {#if activeRuns.length > 0}
    <section>
      <h3 class="text-xs font-semibold uppercase tracking-wider text-content-muted mb-2">
        Active
      </h3>
      <div class="card p-0 divide-y divide-stroke">
        {#each activeRuns as run}
          {@const stuck = isLikelyStuck(run)}
          <div class="flex items-stretch transition-colors
            {currentRunId === run.run_id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}
            {stuck ? 'bg-amber-50 dark:bg-amber-900/10' : 'hover:bg-surface-alt'}">
            <button
              type="button"
              class="flex-1 text-left px-4 py-3"
              on:click={() => handleViewRun(run.run_id, payloadRaceId(run))}
            >
              <div class="flex items-center gap-3">
                {#if run.status === "running" && !stuck}
                  <svg class="animate-spin h-4 w-4 text-blue-500 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                {/if}
                <span class="font-mono text-sm font-medium text-content flex-1 truncate">{raceId(run)}</span>
                {#if stuck}
                  <span class="text-xs px-2 py-0.5 rounded-full border border-amber-300 bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">likely timed out</span>
                {:else}
                  <span class="text-xs px-2 py-0.5 rounded-full border {getStatusClass(run.status)}">{run.status}</span>
                {/if}
                <svg class="h-4 w-4 text-content-faint shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </div>
              <div class="mt-1 flex items-center gap-3 text-xs text-content-faint">
                <span>{timeAgo(run.started_at)}</span>
                {#if run.started_at && (run.status === "running" || run.status === "pending")}
                  <span class="{stuck ? 'text-amber-600 dark:text-amber-400' : ''}">· {elapsedSince(run.started_at)} elapsed</span>
                {/if}
                {#if run.last_step}<span>· {run.last_step}</span>{/if}
                <span>· {modelLabel(run)}</span>
                {#if run.options?.goal}<span class="text-content-subtle truncate">· {run.options.goal}</span>{/if}
              </div>
            </button>
            <button
              type="button"
              title={stuck ? "Force-cancel stuck run" : "Cancel run"}
              on:click|stopPropagation={() => handleDeleteItem(run.run_id, 'run')}
              class="px-3 transition-colors shrink-0
                {stuck
                  ? 'text-amber-500 hover:text-red-500 dark:text-amber-400 hover:bg-red-50 dark:hover:bg-red-900/20'
                  : 'text-content-faint hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20'}"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Queued (pending without a run_id yet) -->
  {#if pendingQueue.length > 0}
    <section>
      <h3 class="text-xs font-semibold uppercase tracking-wider text-content-muted mb-2">
        Queued ({pendingQueue.length})
      </h3>
      <div class="card p-0 divide-y divide-stroke">
        {#each pendingQueue as item}
          <div class="px-4 py-3 flex items-center gap-3 hover:bg-surface-alt transition-colors">
            <svg class="h-4 w-4 text-content-faint shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span class="font-mono text-sm font-medium text-content flex-1 truncate">{item.race_id}</span>
            <span class="text-xs px-2 py-0.5 rounded-full border {getStatusClass('pending')}">pending</span>
            <span class="text-xs text-content-faint">{timeAgo(item.created_at)}</span>
            <button
              type="button"
              title="Remove from queue"
              on:click={() => handleDeleteItem(item.id, 'queue')}
              class="ml-1 p-1 text-content-faint hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors shrink-0"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- History -->
  <section>
    <h3 class="text-xs font-semibold uppercase tracking-wider text-content-muted mb-2">
      History ({historicalRuns.length})
    </h3>
    {#if historicalRuns.length === 0}
      <div class="card p-8 text-center text-content-muted text-sm">
        No completed runs yet.
      </div>
    {:else}
      <div class="card p-0 divide-y divide-stroke">
        {#each historicalRuns as run}
          <div class="flex items-stretch hover:bg-surface-alt transition-colors">
            <button
              type="button"
              class="flex-1 text-left px-4 py-3"
              on:click={() => handleViewRun(run.run_id, payloadRaceId(run))}
            >
              <div class="flex items-center gap-3">
                <span class="font-mono text-sm font-medium text-content flex-1 truncate">{raceId(run)}</span>
                <span class="text-xs px-2 py-0.5 rounded-full border {getStatusClass(run.status)}">{run.status}</span>
                <svg class="h-4 w-4 text-content-faint shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </div>
              <div class="mt-1 flex items-center gap-3 text-xs text-content-faint">
                <span>{timeAgo(run.started_at)}</span>
                {#if run.duration_ms}<span>· {formatMs(run.duration_ms)}</span>{/if}
                <span>· {modelLabel(run)}</span>                {#if run.options?.goal}<span class="text-content-subtle truncate">\u00b7 {run.options.goal}</span>{/if}              </div>
            </button>
            <button
              type="button"
              title="Delete run"
              on:click|stopPropagation={() => handleDeleteItem(run.run_id, 'run')}
              class="px-3 text-content-faint hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors shrink-0"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        {/each}
      </div>
    {/if}
  </section>
</div>
