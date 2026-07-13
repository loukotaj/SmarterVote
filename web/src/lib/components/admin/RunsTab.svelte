<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from "svelte";
  import { getStatusClass, getLogClass } from "$lib/utils/pipelineUtils";
  import type {
    RunHistoryItem,
    PipelineMetricsSummary,
    PipelineRunRecord,
    LogEntry,
    RunInfo,
  } from "$lib/types";
  import type {
    QueueItem,
    PipelineApiService,
  } from "$lib/services/pipelineApiService";
  import { analyticsService } from "$lib/services/analyticsService";

  export let runs: RunHistoryItem[] = [];
  export let queueItems: QueueItem[] = [];
  export let isRefreshing = false;
  export let isPruning = false;
  export let apiService: PipelineApiService | undefined = undefined;

  const dispatch = createEventDispatcher<{
    refresh: void;
    "clear-queue": void;
    "prune-runs": void;
  }>();

  // Date/Time Range Filter
  const TIME_RANGES = [
    { label: "1h", value: 1 },
    { label: "6h", value: 6 },
    { label: "24h", value: 24 },
    { label: "7d", value: 168 },
    { label: "30d", value: 720 },
  ];
  let selectedHours = 24;
  $: rangeLabel =
    TIME_RANGES.find((r) => r.value === selectedHours)?.label ??
    `${selectedHours}h`;

  let pipelineSummary: PipelineMetricsSummary | null = null;
  let pipelineRecords: PipelineRunRecord[] = [];
  let loadingMetrics = true;
  let metricsError = "";

  // Logs drawer state
  let selectedRunId: string | null = null;
  let selectedRunRaceId: string | null = null;
  let selectedRunDetail: RunInfo | null = null;
  let drawerLogs: LogEntry[] = [];
  let drawerLogFilter: "all" | "debug" | "info" | "warning" | "error" = "all";
  let logSearchQuery = "";
  let loadingDrawerDetails = false;
  let drawerError = "";
  let logPollTimer: ReturnType<typeof setInterval> | null = null;
  let lastLogIndex = 0;
  let logContainer: HTMLDivElement;
  let lastRenderedLogCount = 0;
  let shouldAutoScrollLogs = true;

  // History list filtering
  let runSearchQuery = "";
  let runStatusFilter = "all";
  let runModeFilter = "all"; // 'all', 'cheap', 'full'
  let runModelNameFilter = "all";

  // Actions
  let cancellingRunId: string | null = null;
  let clearingQueue = false;

  type RunMetricFields = RunHistoryItem & {
    estimated_usd?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    invocation_run_ids?: string[];
  };

  $: filteredDrawerLogs = drawerLogs.filter((log) => {
    const matchesLevel =
      drawerLogFilter === "all" || log.level === drawerLogFilter;
    const matchesQuery =
      !logSearchQuery ||
      log.message.toLowerCase().includes(logSearchQuery.toLowerCase());
    return matchesLevel && matchesQuery;
  });

  // Follow live logs only while the viewer is already near the bottom.
  $: if (
    logContainer &&
    filteredDrawerLogs.length !== lastRenderedLogCount &&
    shouldAutoScrollLogs
  ) {
    setTimeout(() => {
      if (logContainer) {
        logContainer.scrollTop = logContainer.scrollHeight;
      }
    }, 50);
    lastRenderedLogCount = filteredDrawerLogs.length;
  } else if (filteredDrawerLogs.length !== lastRenderedLogCount) {
    lastRenderedLogCount = filteredDrawerLogs.length;
  }

  // cleared externally resets local clearing state
  $: if (!pendingQueue.length) clearingQueue = false;

  $: selectedMetricsRecord = pipelineRecords.find(
    (r) => r.run_id === selectedRunId,
  );
  $: _isPruningPlaceholder = isPruning;

  // Dynamic list of specific models present in history
  $: uniqueModels = (() => {
    const models = new Set<string>();
    for (const r of runs) {
      const model = r.options?.research_model;
      if (model) models.add(model);
    }
    return Array.from(models).sort();
  })();

  // Metrics Derived
  $: topModels = (() => {
    const counts: Record<string, number> = {};
    for (const rec of pipelineRecords) {
      if (rec.model) {
        const sm = shortModel(rec.model);
        counts[sm] = (counts[sm] ?? 0) + 1;
      }
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  })();

  export async function fetchMetrics(hours = selectedHours) {
    loadingMetrics = true;
    metricsError = "";
    try {
      const [summary, recs] = await Promise.all([
        analyticsService.getPipelineMetricsSummary(hours),
        analyticsService.getPipelineMetrics(Math.max(50, runs.length)),
      ]);
      pipelineSummary = summary;
      pipelineRecords = recs.records || [];
    } catch (err) {
      console.error("Failed to load pipeline metrics:", err);
      metricsError = String(err);
    } finally {
      loadingMetrics = false;
    }
  }

  function handleRangeChange(hours: number) {
    selectedHours = hours;
    void fetchMetrics(hours);
  }

  async function openRunDrawer(runId: string, raceId: string | null) {
    selectedRunId = runId;
    selectedRunRaceId = raceId;
    selectedRunDetail = null;
    drawerLogs = [];
    lastLogIndex = 0;
    lastRenderedLogCount = 0;
    shouldAutoScrollLogs = true;
    drawerError = "";
    loadingDrawerDetails = true;

    if (logPollTimer) {
      clearInterval(logPollTimer);
      logPollTimer = null;
    }

    try {
      if (apiService) {
        // load initial details
        selectedRunDetail = await apiService.getRunDetails(runId);

        // load logs
        const logRes = await apiService.getRunLogs(runId, 0);
        drawerLogs = logRes.logs || [];
        lastLogIndex = drawerLogs.length;

        // If status is running or pending, start polling
        if (
          selectedRunDetail.status === "running" ||
          selectedRunDetail.status === "pending"
        ) {
          const currentTimer = setInterval(async () => {
            if (selectedRunId !== runId) {
              clearInterval(currentTimer);
              if (logPollTimer === currentTimer) {
                logPollTimer = null;
              }
              return;
            }
            try {
              if (apiService) {
                selectedRunDetail = await apiService.getRunDetails(runId);
                const newLogsRes = await apiService.getRunLogs(
                  runId,
                  lastLogIndex,
                );
                if (newLogsRes.logs && newLogsRes.logs.length > 0) {
                  drawerLogs = [...drawerLogs, ...newLogsRes.logs];
                  lastLogIndex = lastLogIndex + newLogsRes.logs.length;
                }

                if (
                  selectedRunDetail.status !== "running" &&
                  selectedRunDetail.status !== "pending"
                ) {
                  clearInterval(currentTimer);
                  if (logPollTimer === currentTimer) {
                    logPollTimer = null;
                  }
                }
              }
            } catch (err) {
              console.error("Error polling logs/details:", err);
            }
          }, 3000);
          logPollTimer = currentTimer;
        }
      } else {
        drawerError = "API service not available";
      }
    } catch (err) {
      drawerError = String(err);
    } finally {
      loadingDrawerDetails = false;
    }
  }

  function closeRunDrawer() {
    selectedRunId = null;
    selectedRunRaceId = null;
    selectedRunDetail = null;
    drawerLogs = [];
    lastRenderedLogCount = 0;
    shouldAutoScrollLogs = true;
    if (logPollTimer) {
      clearInterval(logPollTimer);
      logPollTimer = null;
    }
  }

  function handleLogScroll() {
    if (!logContainer) return;
    const distanceFromBottom =
      logContainer.scrollHeight -
      logContainer.scrollTop -
      logContainer.clientHeight;
    shouldAutoScrollLogs = distanceFromBottom < 48;
  }

  async function handleClearQueue() {
    if (
      !confirm(
        `Remove all ${pendingQueue.length} pending item${
          pendingQueue.length !== 1 ? "s" : ""
        } from the queue?`,
      )
    )
      return;
    clearingQueue = true;
    dispatch("clear-queue");
  }

  async function handleCancelRun(runId: string, event?: Event) {
    if (event) event.stopPropagation();
    if (!confirm(`Are you sure you want to cancel run ${runId}?`)) return;
    cancellingRunId = runId;
    try {
      if (apiService) {
        await apiService.deleteRun(runId);
        dispatch("refresh");
        void fetchMetrics();
        if (selectedRunId === runId) {
          selectedRunDetail = await apiService.getRunDetails(runId);
        }
      }
    } catch (err) {
      alert(`Failed to cancel run: ${err}`);
    } finally {
      cancellingRunId = null;
    }
  }

  function sumStepTokens(run: RunHistoryItem | RunInfo): {
    prompt: number;
    completion: number;
    total: number;
    cost: number;
  } {
    let prompt = 0;
    let completion = 0;
    let cost = 0;
    if (run.steps) {
      for (const step of run.steps) {
        prompt += step.prompt_tokens ?? 0;
        completion += step.completion_tokens ?? 0;
        cost += step.estimated_usd ?? 0;
      }
    }
    return { prompt, completion, total: prompt + completion, cost };
  }

  function getRunMetrics(run: RunHistoryItem | RunInfo) {
    const record = pipelineRecords.find((r) => r.run_id === run.run_id);
    const stepSum = sumStepTokens(run);
    const runMetrics = run as RunMetricFields;

    const cost = record
      ? (record.cost_usd ?? record.estimated_usd)
      : stepSum.cost || runMetrics.estimated_usd || 0;
    const prompt = record
      ? record.prompt_tokens
      : stepSum.prompt || runMetrics.prompt_tokens || 0;
    const completion = record
      ? record.completion_tokens
      : stepSum.completion || runMetrics.completion_tokens || 0;
    const total = record
      ? record.total_tokens
      : stepSum.total || runMetrics.total_tokens || 0;
    const serper = (record ? record.serper_calls : run.serper_calls) ?? 0;

    return { cost, prompt, completion, total, serper };
  }

  function timeAgo(iso: string): string {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 90000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }

  function formatMs(ms?: number): string {
    if (!ms) return "";
    if (ms < 60000) return `${Math.round(ms / 1000)}s`;
    const m = Math.floor(ms / 60000);
    const s = Math.round((ms % 60000) / 1000);
    return s ? `${m}m ${s}s` : `${m}m`;
  }

  function formatUsd(n: number | null | undefined) {
    if (typeof n !== "number" || !Number.isFinite(n)) return "-";
    return n < 0.001 ? "<$0.001" : `$${n.toFixed(4)}`;
  }

  function formatExactUsd(n: number | null | undefined) {
    if (typeof n !== "number" || !Number.isFinite(n)) return "-";
    return `$${n.toFixed(6)}`;
  }

  function formatTokens(n?: number): string {
    if (n === undefined || n === null) return "-";
    if (n < 1000) return String(n);
    return `${(n / 1000).toFixed(1)}k`;
  }

  function shortModel(m: string): string {
    if (!m) return "";
    return m.replace(/^openai\/|^google\/|^anthropic\//, "");
  }

  function formatDate(s?: string) {
    if (!s) return "-";
    return new Date(s).toLocaleString(undefined, {
      dateStyle: "short",
      timeStyle: "short",
    });
  }

  function raceId(run: RunHistoryItem | QueueItem): string {
    if ("payload" in run)
      return (run.payload?.race_id as string) ?? run.run_id ?? "—";
    return run.race_id ?? "—";
  }

  function modelLabel(run: RunHistoryItem): string {
    if (run.options?.research_model) return String(run.options.research_model);
    if (run.options?.cheap_mode === false) return "full";
    return "mini";
  }

  function runProgress(run: RunHistoryItem): number {
    return Math.max(0, Math.min(100, Number(run.progress ?? 0)));
  }

  function currentStepLabel(run: RunHistoryItem): string {
    if (run.progress_message) return run.progress_message;
    const step = run.current_step ?? run.last_step;
    return step ? String(step).replaceAll("_", " ") : run.status;
  }

  $: liveRunIds = new Set(
    queueItems
      .filter((q) => q.status === "running" || q.status === "pending")
      .map((q) => q.run_id)
      .filter(Boolean),
  );
  $: continuationParentRunIds = new Set(
    queueItems.map((q) => q.parent_run_id).filter(Boolean),
  );
  $: activeQueueItems = queueItems.filter(
    (q) =>
      (q.status === "running" || q.status === "pending") &&
      !continuationParentRunIds.has(q.run_id),
  );

  $: activeQueueRuns = activeQueueItems
    .filter(
      (q) =>
        (q.status === "running" || q.status === "pending") &&
        q.run_id &&
        !runs.some((r) => r.run_id === q.run_id),
    )
    .map(
      (q, idx) =>
        ({
          run_id: q.run_id!,
          race_id: q.race_id,
          status: q.status,
          progress: 0,
          progress_message: q.is_continuation
            ? "Waiting for continuation"
            : undefined,
          current_step: q.status,
          payload: { race_id: q.race_id },
          options: q.options ?? {},
          started_at: q.started_at ?? q.created_at,
          updated_at: q.started_at ?? q.created_at,
          display_id: -(idx + 1),
          steps: [],
        }) as RunHistoryItem,
    );

  $: activeRuns = [
    ...runs.filter(
      (r) =>
        (r.status === "running" ||
          r.status === "pending" ||
          liveRunIds.has(r.run_id)) &&
        !continuationParentRunIds.has(r.run_id),
    ),
    ...activeQueueRuns,
  ];
  $: pendingQueue = activeQueueItems.filter((q) => q.status === "pending");
  $: historicalRuns = runs.filter(
    (r) =>
      r.status !== "running" &&
      r.status !== "pending" &&
      !liveRunIds.has(r.run_id),
  );

  // Filtered lists
  $: filteredHistoricalRuns = historicalRuns.filter((r) => {
    // 1. Search Query
    if (runSearchQuery) {
      const q = runSearchQuery.toLowerCase();
      const matchRace =
        r.race_id?.toLowerCase().includes(q) ||
        (r.payload?.race_id as string)?.toLowerCase().includes(q);
      const matchRun = r.run_id?.toLowerCase().includes(q);
      if (!matchRace && !matchRun) return false;
    }
    // 2. Status Filter
    if (runStatusFilter !== "all" && r.status !== runStatusFilter) {
      return false;
    }
    // 3. Mode Filter
    if (runModeFilter !== "all") {
      const isCheap = r.options?.cheap_mode !== false;
      if (runModeFilter === "cheap" && !isCheap) return false;
      if (runModeFilter === "full" && isCheap) return false;
    }
    // 4. Model Name Filter
    if (runModelNameFilter !== "all") {
      if (r.options?.research_model !== runModelNameFilter) return false;
    }
    return true;
  });

  $: filteredActiveRuns = activeRuns.filter((r) => {
    if (runSearchQuery) {
      const q = runSearchQuery.toLowerCase();
      const matchRace =
        r.race_id?.toLowerCase().includes(q) ||
        (r.payload?.race_id as string)?.toLowerCase().includes(q);
      const matchRun = r.run_id?.toLowerCase().includes(q);
      if (!matchRace && !matchRun) return false;
    }
    return true;
  });

  // Dynamic aggregations for filtered runs
  $: aggregations = (() => {
    let totalCost = 0;
    let totalDurationMs = 0;
    let durationCount = 0;
    let totalTokens = 0;
    let totalSearches = 0;

    for (const r of filteredHistoricalRuns) {
      const m = getRunMetrics(r);
      totalCost += m.cost;
      totalTokens += m.total;
      totalSearches += m.serper;
      if (r.duration_ms) {
        totalDurationMs += r.duration_ms;
        durationCount++;
      }
    }

    return {
      cost: totalCost,
      avgDurationMs: durationCount > 0 ? totalDurationMs / durationCount : 0,
      tokens: totalTokens,
      searches: totalSearches,
    };
  })();

  // Lineage path calculation
  $: lineageRunIds = (() => {
    if (!selectedRunId) return [];
    const activeRunId = selectedRunId;
    const matchingRun = runs.find((r) => {
      const runWithLineage = r as RunMetricFields;
      return (
        r.run_id === activeRunId ||
        runWithLineage.invocation_run_ids?.includes(activeRunId)
      );
    }) as RunMetricFields | undefined;
    return matchingRun?.invocation_run_ids || [];
  })();

  onMount(() => {
    void fetchMetrics();
  });

  onDestroy(() => {
    if (logPollTimer) clearInterval(logPollTimer);
  });
</script>

<div class="space-y-6">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <div>
      <h2 class="text-lg font-semibold text-content">All Runs</h2>
      {#if activeRuns.length > 1}
        <p class="text-xs font-medium text-blue-700 dark:text-blue-300 mt-0.5">
          {activeRuns.length} active runs processing
        </p>
      {/if}
      <p class="text-xs text-content-muted mt-0.5">
        {runs.length} run{runs.length !== 1 ? "s" : ""}{pendingQueue.length > 0
          ? ` · ${pendingQueue.length} queued`
          : ""}
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
            <svg
              class="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                class="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="4"
              />
              <path
                class="opacity-75"
                fill="currentColor"
                d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          {:else}
            <svg
              class="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
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
          <svg
            class="animate-spin h-4 w-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              class="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              stroke-width="4"
            />
            <path
              class="opacity-75"
              fill="currentColor"
              d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        {:else}
          <svg
            class="h-4 w-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        {/if}
        Refresh
      </button>
    </div>
  </div>

  <!-- Time range selector & Metrics Section -->
  <div class="border-t border-stroke pt-4 space-y-4">
    <div class="flex items-center justify-between">
      <h3
        class="text-xs font-semibold uppercase tracking-wider text-content-muted"
      >
        Pipeline Performance Metrics
      </h3>
      <div class="flex items-center gap-1 bg-surface-alt rounded-lg p-1">
        {#each TIME_RANGES as range}
          <button
            type="button"
            class="px-2 py-0.5 rounded text-xs font-medium transition-colors
              {selectedHours === range.value
              ? 'bg-surface text-content shadow-sm'
              : 'text-content-subtle hover:text-content-muted'}"
            on:click={() => handleRangeChange(range.value)}
          >
            {range.label}
          </button>
        {/each}
      </div>
    </div>

    {#if loadingMetrics}
      <!-- Skeleton Loaders -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse">
        {#each Array(4) as _}
          <div class="card p-4 space-y-2">
            <div class="h-3 bg-surface-alt rounded w-2/3"></div>
            <div class="h-6 bg-surface-alt rounded w-1/2"></div>
          </div>
        {/each}
      </div>
    {:else if metricsError}
      <div
        class="card p-4 flex flex-col items-center justify-center text-center space-y-3"
      >
        <p class="text-sm text-red-600">
          Failed to load pipeline analytics: {metricsError}
        </p>
        <button
          type="button"
          class="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-medium shadow-sm"
          on:click={() => fetchMetrics(selectedHours)}
        >
          Retry
        </button>
      </div>
    {:else}
      <!-- Metrics cards -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="card p-4">
          <p
            class="text-xs font-medium text-content-subtle uppercase tracking-wide"
          >
            Total Runs ({rangeLabel})
          </p>
          <p class="mt-1 text-2xl font-bold text-content">
            {pipelineSummary
              ? pipelineSummary.total_runs.toLocaleString()
              : "-"}
          </p>
        </div>
        <div class="card p-4">
          <p
            class="text-xs font-medium text-content-subtle uppercase tracking-wide"
          >
            Avg Cost / Run
          </p>
          {#if pipelineSummary && (pipelineSummary.cheap_runs > 0 || pipelineSummary.full_runs > 0)}
            <div class="space-y-1">
              {#if pipelineSummary.cheap_runs > 0}
                <div class="flex items-center justify-between">
                  <span
                    class="text-xs px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300"
                    >cheap</span
                  >
                  <span class="text-sm font-bold text-content"
                    >{formatUsd(pipelineSummary.avg_cheap_usd)}</span
                  >
                </div>
              {/if}
              {#if pipelineSummary.full_runs > 0}
                <div class="flex items-center justify-between">
                  <span
                    class="text-xs px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300"
                    >full</span
                  >
                  <span class="text-sm font-bold text-content"
                    >{formatUsd(pipelineSummary.avg_full_usd)}</span
                  >
                </div>
              {/if}
            </div>
          {:else}
            <p class="mt-1 text-2xl font-bold text-content">
              {pipelineSummary ? formatUsd(pipelineSummary.avg_usd) : "-"}
            </p>
          {/if}
        </div>
        <div class="card p-4">
          <p
            class="text-xs font-medium text-content-subtle uppercase tracking-wide"
          >
            Avg Cost / Candidate
          </p>
          <p class="mt-1 text-2xl font-bold text-content">
            {pipelineSummary && pipelineSummary.avg_usd_per_candidate > 0
              ? formatUsd(pipelineSummary.avg_usd_per_candidate)
              : "-"}
          </p>
          {#if pipelineSummary && pipelineSummary.avg_usd_per_candidate > 0}
            <p class="mt-1 text-xs text-content-faint">
              across runs with candidates
            </p>
          {:else}
            <p class="mt-1 text-xs text-content-faint">
              available after next run
            </p>
          {/if}
        </div>
        <div class="card p-4">
          <p
            class="text-xs font-medium text-content-subtle uppercase tracking-wide"
          >
            Success Rate
          </p>
          <p class="mt-1 text-2xl font-bold text-content">
            {pipelineSummary
              ? `${(pipelineSummary.success_rate * 100).toFixed(1)}%`
              : "-"}
          </p>
        </div>
      </div>

      <!-- Mode run count bar -->
      {#if pipelineSummary && pipelineSummary.total_runs > 0 && (pipelineSummary.cheap_runs > 0 || pipelineSummary.full_runs > 0)}
        <div class="card p-3 flex items-center gap-4 flex-wrap">
          <span class="text-xs text-content-muted shrink-0">Run modes:</span>
          {#if pipelineSummary.cheap_runs > 0}
            <div class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block"
              ></span>
              <span class="text-xs text-content-muted"
                ><strong>{pipelineSummary.cheap_runs}</strong> cheap ({formatUsd(
                  pipelineSummary.avg_cheap_usd,
                )} avg)</span
              >
            </div>
          {/if}
          {#if pipelineSummary.full_runs > 0}
            <div class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-sm bg-purple-500 inline-block"
              ></span>
              <span class="text-xs text-content-muted"
                ><strong>{pipelineSummary.full_runs}</strong> full ({formatUsd(
                  pipelineSummary.avg_full_usd,
                )} avg)</span
              >
            </div>
          {/if}
          {#if topModels.length > 0}
            <div class="ml-auto flex items-center gap-2 flex-wrap">
              <span class="text-xs text-content-faint">Models:</span>
              {#each topModels as [model, count]}
                <span
                  class="text-xs px-1.5 py-0.5 rounded bg-surface-alt text-content-muted font-mono"
                >
                  {model} x{count}
                </span>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    {/if}
  </div>

  <!-- Active / running runs -->
  {#if filteredActiveRuns.length > 0}
    <section>
      <h3
        class="text-xs font-semibold uppercase tracking-wider text-content-muted mb-2"
      >
        Active
      </h3>
      <div class="card p-0 divide-y divide-stroke">
        {#each filteredActiveRuns as run (run.run_id)}
          {@const m = getRunMetrics(run)}
          <div
            class="px-4 py-3 hover:bg-surface-alt transition-colors cursor-pointer flex items-center justify-between"
            role="button"
            tabindex="0"
            on:click={() => openRunDrawer(run.run_id, raceId(run))}
            on:keydown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                openRunDrawer(run.run_id, raceId(run));
              }
            }}
          >
            <div class="flex-1 min-w-0 mr-4">
              <div class="flex items-center gap-3">
                {#if run.status === "running"}
                  <svg
                    class="animate-spin h-4 w-4 text-blue-500 shrink-0"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      class="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      stroke-width="4"
                    />
                    <path
                      class="opacity-75"
                      fill="currentColor"
                      d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                {/if}
                <span
                  class="font-mono text-sm font-medium text-content flex-1 truncate"
                  >{raceId(run)}</span
                >
                <span
                  class="text-xs text-content-subtle capitalize truncate max-w-40"
                  >{currentStepLabel(run)}</span
                >
                <span
                  class="text-xs font-mono text-content-muted w-10 text-right"
                  >{runProgress(run)}%</span
                >
                <span
                  class="text-xs px-2 py-0.5 rounded-full border {getStatusClass(
                    run.status,
                  )}">{run.status}</span
                >
              </div>
              <div class="mt-2 grid grid-cols-[1fr_auto] items-center gap-3">
                <div class="h-1.5 rounded-full bg-surface-alt overflow-hidden">
                  <div
                    class="h-full rounded-full bg-blue-500 transition-all duration-500"
                    style="width: {runProgress(run)}%"
                  ></div>
                </div>
                <div
                  class="text-xs text-content-faint whitespace-nowrap font-mono"
                >
                  {modelLabel(run)}
                  {#if m.total > 0}
                    · {formatTokens(m.prompt)}/{formatTokens(m.completion)} tokens{/if}
                  {#if m.cost > 0}
                    · <span class="font-semibold text-content-muted"
                      >{formatUsd(m.cost)}</span
                    >{/if}
                </div>
              </div>
            </div>
            <button
              type="button"
              class="px-2.5 py-1 text-xs border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/10 rounded transition-colors font-medium whitespace-nowrap flex items-center gap-1"
              disabled={cancellingRunId === run.run_id}
              on:click={(e) => handleCancelRun(run.run_id, e)}
            >
              {#if cancellingRunId === run.run_id}
                <svg
                  class="animate-spin h-3 w-3"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    class="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    stroke-width="4"
                  />
                  <path
                    class="opacity-75"
                    fill="currentColor"
                    d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
              {/if}
              Cancel
            </button>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Queued (pending without a run_id yet) -->
  {#if pendingQueue.length > 0}
    <section>
      <h3
        class="text-xs font-semibold uppercase tracking-wider text-content-muted mb-2"
      >
        Queued ({pendingQueue.length})
      </h3>
      <div class="card p-0 divide-y divide-stroke">
        {#each pendingQueue as item}
          <div
            class="px-4 py-3 flex items-center gap-3 hover:bg-surface-alt transition-colors"
          >
            <svg
              class="h-4 w-4 text-content-faint shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span
              class="font-mono text-sm font-medium text-content flex-1 truncate"
              >{item.race_id}</span
            >
            <span
              class="text-xs px-2 py-0.5 rounded-full border {getStatusClass(
                'pending',
              )}">pending</span
            >
            <span class="text-xs text-content-faint"
              >{timeAgo(item.created_at)}</span
            >
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- History section with Filters & Aggregations -->
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <h3
        class="text-xs font-semibold uppercase tracking-wider text-content-muted"
      >
        History ({filteredHistoricalRuns.length})
      </h3>
    </div>

    <!-- Runs Filters -->
    <div
      class="flex items-center gap-3 flex-wrap bg-surface-alt p-3 rounded-lg border border-stroke text-sm"
    >
      <div class="flex-1 min-w-[200px]">
        <input
          type="search"
          bind:value={runSearchQuery}
          placeholder="Filter history by Race ID or Run ID..."
          class="w-full px-3 py-1.5 text-xs border border-stroke rounded bg-surface text-content focus:outline-none focus:border-blue-500"
        />
      </div>

      <!-- Status Dropdown -->
      <select
        bind:value={runStatusFilter}
        class="px-2.5 py-1.5 text-xs border border-stroke rounded bg-surface text-content focus:outline-none focus:border-blue-500"
      >
        <option value="all">All Statuses</option>
        <option value="completed">Completed</option>
        <option value="failed">Failed</option>
        <option value="cancelled">Cancelled</option>
      </select>

      <!-- Mode Dropdown -->
      <select
        bind:value={runModeFilter}
        class="px-2.5 py-1.5 text-xs border border-stroke rounded bg-surface text-content focus:outline-none focus:border-blue-500"
      >
        <option value="all">All Modes</option>
        <option value="cheap">Cheap Mode (Mini)</option>
        <option value="full">Full Mode (Quality)</option>
      </select>

      <!-- Model Name Dropdown -->
      {#if uniqueModels.length > 0}
        <select
          bind:value={runModelNameFilter}
          class="px-2.5 py-1.5 text-xs border border-stroke rounded bg-surface text-content focus:outline-none focus:border-blue-500 font-mono"
        >
          <option value="all">All Models</option>
          {#each uniqueModels as model}
            <option value={model}>{shortModel(model)}</option>
          {/each}
        </select>
      {/if}
    </div>

    <!-- Aggregations Bar -->
    {#if filteredHistoricalRuns.length > 0}
      <div
        class="grid grid-cols-2 md:grid-cols-4 gap-4 p-3 bg-surface border border-stroke rounded-lg text-xs"
      >
        <div>
          <span class="text-content-faint block">Matched Cost:</span>
          <span class="font-bold text-content text-sm"
            >{formatUsd(aggregations.cost)}</span
          >
        </div>
        <div>
          <span class="text-content-faint block">Avg Duration:</span>
          <span class="font-bold text-content text-sm"
            >{aggregations.avgDurationMs
              ? formatMs(aggregations.avgDurationMs)
              : "—"}</span
          >
        </div>
        <div>
          <span class="text-content-faint block">Total Tokens:</span>
          <span class="font-bold text-content text-sm"
            >{formatTokens(aggregations.tokens)}</span
          >
        </div>
        <div>
          <span class="text-content-faint block">Total Searches:</span>
          <span class="font-bold text-content text-sm"
            >{aggregations.searches}</span
          >
        </div>
      </div>
    {/if}

    {#if filteredHistoricalRuns.length === 0}
      <div class="card p-8 text-center text-content-muted text-sm">
        No matching historical runs found.
      </div>
    {:else}
      <div class="card p-0 divide-y divide-stroke">
        {#each filteredHistoricalRuns as run}
          {@const metrics = getRunMetrics(run)}
          <div
            class="px-4 py-3 hover:bg-surface-alt transition-colors cursor-pointer"
            role="button"
            tabindex="0"
            on:click={() => openRunDrawer(run.run_id, raceId(run))}
            on:keydown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                openRunDrawer(run.run_id, raceId(run));
              }
            }}
          >
            <div class="flex items-center gap-3">
              <span
                class="font-mono text-sm font-medium text-content flex-1 truncate"
                >{raceId(run)}</span
              >
              <span
                class="text-xs px-2 py-0.5 rounded-full border {getStatusClass(
                  run.status,
                )}">{run.status}</span
              >
            </div>
            <div
              class="mt-1 flex items-center gap-3 text-xs text-content-faint flex-wrap"
            >
              <span>{timeAgo(run.started_at)}</span>
              {#if run.duration_ms}<span>· {formatMs(run.duration_ms)}</span
                >{/if}
              <span>· {modelLabel(run)}</span>
              {#if metrics.total > 0}
                <span
                  >· {formatTokens(metrics.prompt)} / {formatTokens(
                    metrics.completion,
                  )} tokens</span
                >
              {/if}
              {#if metrics.cost > 0}
                <span class="font-semibold text-content-muted"
                  >· {formatUsd(metrics.cost)}</span
                >
              {/if}
              {#if metrics.serper > 0}
                <span
                  >· {metrics.serper} search{metrics.serper === 1
                    ? ""
                    : "es"}</span
                >
              {/if}
              {#if run.options?.goal}<span class="text-content-subtle truncate"
                  >· {run.options.goal}</span
                >{/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>
</div>

<!-- Logs / Details Side Drawer -->
{#if selectedRunId}
  <div
    class="fixed inset-y-0 right-0 w-full max-w-2xl bg-surface border-l border-stroke shadow-2xl z-50 flex flex-col transition-transform duration-300"
  >
    <!-- Drawer Header -->
    <div
      class="p-4 border-b border-stroke flex items-center justify-between bg-surface-alt/20"
    >
      <div>
        <h3 class="text-md font-bold text-content truncate max-w-md">
          Run Logs: {selectedRunId}
        </h3>
        {#if selectedRunRaceId}
          <p class="text-xs text-content-subtle font-mono">
            {selectedRunRaceId}
          </p>
        {/if}
      </div>
      <div class="flex items-center gap-2">
        {#if selectedRunDetail && (selectedRunDetail.status === "running" || selectedRunDetail.status === "pending")}
          <button
            type="button"
            class="px-2.5 py-1 text-xs border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/10 rounded transition-colors font-medium whitespace-nowrap flex items-center gap-1"
            disabled={cancellingRunId === selectedRunId}
            on:click={() => handleCancelRun(selectedRunId ?? "")}
          >
            {#if cancellingRunId === selectedRunId}
              <svg
                class="animate-spin h-3 w-3"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  class="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  stroke-width="4"
                />
                <path
                  class="opacity-75"
                  fill="currentColor"
                  d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            {/if}
            Cancel Run
          </button>
        {/if}
        <button
          type="button"
          aria-label="Close run details"
          class="p-1.5 rounded-lg hover:bg-surface-alt text-content-muted hover:text-content transition-colors"
          on:click={closeRunDrawer}
        >
          <svg
            class="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>
    </div>

    <!-- Lineage Graph -->
    {#if lineageRunIds.length > 1}
      <div
        class="px-4 py-2 bg-surface-alt border-b border-stroke flex items-center gap-1.5 flex-wrap text-[11px] font-mono"
      >
        <span class="text-content-faint font-sans">Lineage:</span>
        {#each lineageRunIds as id, idx}
          {#if idx > 0}
            <span class="text-content-faint">➔</span>
          {/if}
          {#if id === selectedRunId}
            <span
              class="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded font-bold"
              >{id}</span
            >
          {:else}
            <button
              type="button"
              class="px-1.5 py-0.5 hover:bg-surface text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 rounded underline decoration-dotted transition-colors"
              on:click={() => openRunDrawer(id, selectedRunRaceId)}
            >
              {id}
            </button>
          {/if}
        {/each}
      </div>
    {/if}

    <!-- Drawer Content -->
    <div class="flex-1 overflow-y-auto p-4 space-y-4">
      {#if loadingDrawerDetails}
        <div class="animate-pulse space-y-4">
          <div class="h-20 bg-surface-alt rounded"></div>
          <div class="h-10 bg-surface-alt rounded w-1/3"></div>
          <div class="space-y-2">
            <div class="h-4 bg-surface-alt rounded"></div>
            <div class="h-4 bg-surface-alt rounded w-5/6"></div>
          </div>
        </div>
      {:else if drawerError}
        <div
          class="p-4 flex flex-col items-center justify-center text-center space-y-2 border border-red-200 bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-200 rounded-lg"
        >
          <svg
            class="h-8 w-8 text-red-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span class="text-sm font-semibold">Failed to load run details</span>
          <p class="text-xs opacity-80">{drawerError}</p>
          <button
            type="button"
            class="px-3 py-1.5 text-xs bg-red-600 hover:bg-red-700 text-white rounded transition-colors font-medium shadow-sm"
            on:click={() =>
              openRunDrawer(selectedRunId ?? "", selectedRunRaceId)}
          >
            Retry
          </button>
        </div>
      {:else if selectedRunDetail}
        {@const m = getRunMetrics(selectedRunDetail)}
        <!-- Metadata cards -->
        <div class="card p-3 grid grid-cols-2 gap-3 text-xs">
          <div>
            <span class="text-content-faint">Status:</span>
            <span
              class="ml-1 px-1.5 py-0.5 rounded font-medium {getStatusClass(
                selectedRunDetail.status,
              )}"
            >
              {selectedRunDetail.status}
            </span>
          </div>
          <div>
            <span class="text-content-faint">Model:</span>
            <span class="ml-1 text-content font-mono"
              >{selectedRunDetail.options?.research_model ||
                (selectedRunDetail.options?.cheap_mode ? "mini" : "full")}</span
            >
          </div>
          <div>
            <span class="text-content-faint">Duration:</span>
            <span class="ml-1 text-content"
              >{selectedRunDetail.duration_ms
                ? formatMs(selectedRunDetail.duration_ms)
                : selectedMetricsRecord?.duration_s
                  ? `${selectedMetricsRecord.duration_s}s`
                  : "—"}</span
            >
          </div>
          <div>
            <span class="text-content-faint">Cost:</span>
            <span class="ml-1 text-content font-semibold"
              >{formatExactUsd(m.cost)}</span
            >
          </div>
          <div>
            <span class="text-content-faint">Tokens:</span>
            <span class="ml-1 text-content font-mono"
              >{formatTokens(m.prompt)} / {formatTokens(m.completion)} ({formatTokens(
                m.total,
              )} total)</span
            >
          </div>
          <div>
            <span class="text-content-faint">Searches:</span>
            <span class="ml-1 text-content font-mono">{m.serper}</span>
          </div>
          <div class="col-span-2">
            <span class="text-content-faint">Time:</span>
            <span class="ml-1 text-content"
              >{formatDate(selectedRunDetail.started_at)}</span
            >
          </div>
          {#if selectedRunDetail.options?.goal}
            <div class="col-span-2">
              <span class="text-content-faint">Goal:</span>
              <p
                class="mt-1 p-2 bg-surface-alt rounded text-content text-[11px] font-mono whitespace-pre-wrap"
              >
                {selectedRunDetail.options.goal}
              </p>
            </div>
          {/if}
        </div>

        <!-- Execution Steps -->
        {#if selectedRunDetail.steps && selectedRunDetail.steps.length > 0}
          <div>
            <h4 class="text-xs font-semibold text-content-muted mb-2">
              Execution Steps
            </h4>
            <div class="space-y-1.5">
              {#each selectedRunDetail.steps as step}
                <div
                  class="flex items-center justify-between text-xs p-2 rounded bg-surface border border-stroke"
                >
                  <div class="flex flex-col">
                    <span class="font-medium capitalize"
                      >{step.label || step.name.replaceAll("_", " ")}</span
                    >
                    <span class="text-[10px] text-content-faint mt-0.5">
                      {#if step.duration_ms}{formatMs(step.duration_ms)}{/if}
                      {#if step.prompt_tokens || step.completion_tokens}
                        · {formatTokens(step.prompt_tokens)}/{formatTokens(
                          step.completion_tokens,
                        )} tokens
                      {/if}
                      {#if step.estimated_usd}
                        · {formatUsd(step.estimated_usd)}
                      {/if}
                    </span>
                  </div>
                  <div class="flex items-center gap-2">
                    {#if step.progress_pct !== undefined && step.status === "running"}
                      <span class="text-[10px] text-content-faint"
                        >{step.progress_pct}%</span
                      >
                    {/if}
                    <span
                      class="px-1.5 py-0.5 rounded-full text-[10px] border {getStatusClass(
                        step.status,
                      )}">{step.status}</span
                    >
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      {/if}

      <!-- Logs -->
      <div
        class="border-t border-stroke pt-3 flex flex-col h-[55vh] max-h-[520px] min-h-[320px]"
      >
        <div class="flex items-center gap-2 justify-between mb-2">
          <h4 class="text-xs font-semibold text-content-muted">
            Execution Logs
          </h4>
          <div class="flex items-center gap-2">
            <!-- Log Search Input -->
            <input
              type="text"
              bind:value={logSearchQuery}
              placeholder="Search logs..."
              class="text-[10px] px-2 py-0.5 border border-stroke rounded bg-surface text-content focus:outline-none focus:border-blue-500 w-32"
            />
            <!-- Level filter -->
            <select
              bind:value={drawerLogFilter}
              class="text-[10px] px-2 py-0.5 border border-stroke rounded bg-surface text-content"
              aria-label="Filter logs by level"
            >
              <option value="all">All Levels</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
            </select>
          </div>
        </div>

        <div
          bind:this={logContainer}
          class="flex-1 overflow-auto rounded-lg bg-surface-alt border border-stroke p-2 font-mono text-[11px] space-y-1"
          role="log"
          on:scroll={handleLogScroll}
        >
          {#each filteredDrawerLogs as log}
            <div
              class="py-1 px-2 border-b border-stroke/40 whitespace-pre-wrap rounded-sm border-l-4 {getLogClass(
                log.level,
              )}"
            >
              <span class="text-content-faint"
                >[{log.timestamp
                  ? new Date(log.timestamp).toLocaleTimeString()
                  : ""}]</span
              >
              <span class="font-semibold text-[10px]"
                >[{(log.level ?? "info").toUpperCase()}]</span
              >
              {log.message}
            </div>
          {/each}
          {#if filteredDrawerLogs.length === 0}
            <div class="py-12 text-center text-content-faint text-xs">
              No logs found
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>

  <!-- Overlay Backdrop -->
  <div
    class="fixed inset-0 bg-black/45 backdrop-blur-sm z-40"
    on:click={closeRunDrawer}
    on:keydown={(e) => {
      if (e.key === "Escape") {
        closeRunDrawer();
      }
    }}
    role="button"
    tabindex="-1"
    aria-label="Close drawer"
  ></div>
{/if}
