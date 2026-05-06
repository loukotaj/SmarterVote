<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { browser } from "$app/environment";

  // Stores
  import {
    pipelineStore,
    pipelineActions,
    filteredLogs,
    safeOutputDisplay,
  } from "$lib/stores/pipelineStore";
  import { runPollingStore, runPollingActions } from "$lib/stores/runPollingStore";
  import { apiStore, initializeAuth } from "$lib/stores/apiStore";

  // Services
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import type { QueueItem } from "$lib/services/pipelineApiService";

  // Components
  import LiveLogs from "$lib/components/LiveLogs.svelte";
  import PipelineModal from "$lib/components/PipelineModal.svelte";
  import AdminTabs from "$lib/components/admin/AdminTabs.svelte";
  import DashboardTab from "$lib/components/admin/DashboardTab.svelte";
  import RacesTab from "$lib/components/admin/RacesTab.svelte";
  import RacePanel from "$lib/components/admin/RacePanel.svelte";
  import BatchQueueModal from "$lib/components/admin/BatchQueueModal.svelte";
  import RunDetailPanel from "$lib/components/admin/RunDetailPanel.svelte";
  import RunsTab from "$lib/components/admin/RunsTab.svelte";
  import AdminChatTab from "$lib/components/admin/AdminChatTab.svelte";

  // Utilities
  import { debounce, safeJsonStringify } from "$lib/utils/pipelineUtils";
  import { logger } from "$lib/utils/logger";
  import type { RunHistoryItem, Artifact, RaceRecord, RunInfo } from "$lib/types";

  const API_BASE = import.meta.env.VITE_RACES_API_URL || "http://127.0.0.1:8080";

  let apiService: PipelineApiService;
  let racesTabRef: RacesTab;
  let elapsedTimer: ReturnType<typeof setInterval> | null = null;
  let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;
  let queuePollTimer: ReturnType<typeof setInterval> | null = null;

  // Tab state
  let activeTab: "dashboard" | "races" | "runs" | "agent" = "dashboard";
  let alertBadgeCount = 0;

  // Modal state
  let showModal = false;
  let modalTitle = "";
  let modalData: unknown = null;
  let modalLoading = false;

  // Race panel state
  let selectedRace: RaceRecord | null = null;
  let racePanelOpen = false;

  // Batch modal state
  let batchModalOpen = false;
  let batchRaceIds: string[] = [];

  // Server-side queue state
  let queueItems: QueueItem[] = [];

  // Run detail view
  let detailRunId: string | null = null;
  let detailRaceId: string | null = null;
  let liveRun: Partial<RunInfo> | null = null;
  $: showingDetail = !!detailRunId;

  function openRunDetail(runId: string, raceId: string | null = null) {
    detailRunId = runId;
    detailRaceId = raceId;
    if (!browser) return;
    const url = new URL(window.location.href);
    url.searchParams.set("run", runId);
    url.searchParams.set("tab", activeTab === "runs" ? "runs" : "races");
    if (raceId) url.searchParams.set("race", raceId);
    else url.searchParams.delete("race");
    history.pushState({ runId, raceId }, "", url.pathname + url.search);
  }

  function closeRunDetail(skipHistoryUpdate = false) {
    const raceId = detailRaceId;
    detailRunId = null;
    detailRaceId = null;
    liveRun = null;
    if (browser && !skipHistoryUpdate) {
      const url = new URL(window.location.href);
      url.searchParams.delete("run");
      url.searchParams.delete("race");
      history.replaceState(null, "", url.pathname + url.search);
    }
    if (activeTab !== "runs" && raceId) reopenRacePanel(raceId);
  }

  async function reopenRacePanel(raceId: string) {
    if (selectedRace?.race_id === raceId) {
      racePanelOpen = true;
    } else {
      try {
        selectedRace = await apiService.getRaceRecord(raceId);
        racePanelOpen = true;
      } catch {
        // silently fall back to just the races tab
      }
    }
  }

  function handlePopState() {
    const params = new URLSearchParams(window.location.search);
    const runParam = params.get("run");
    const raceParam = params.get("race");
    if (!runParam && detailRunId) {
      closeRunDetail(true);
    } else if (runParam) {
      detailRunId = runParam;
      detailRaceId = raceParam;
    }
  }

  // Reactive computed
  $: queueRunningItems = queueItems.filter((i) => i.status === "running");
  $: queueRunning = queueRunningItems[0] ?? null;
  $: queuePending = queueItems.filter((i) => i.status === "pending").length;
  $: oldestPendingMs = (() => {
    const pending = queueItems.filter((i) => i.status === "pending");
    if (pending.length === 0) return 0;
    const ages = pending
      .map((i) => {
        const created = i.created_at ? Date.parse(i.created_at) : NaN;
        return Number.isFinite(created) ? Date.now() - created : 0;
      })
      .filter((v) => v > 0);
    return ages.length ? Math.max(...ages) : 0;
  })();
  $: queueLikelyStalled = queuePending > 0 && queueRunningItems.length === 0 && oldestPendingMs >= 180000;
  // Runs that appear stuck: in "running" state for >15 min with no completion.
  // Cloud Functions time out around 9 min, so 15 min means it almost certainly timed out.
  const STUCK_THRESHOLD_MS = 15 * 60 * 1000;
  $: stuckRunItems = queueRunningItems.filter((i) => {
    const startMs = i.started_at ? Date.parse(i.started_at) : NaN;
    return Number.isFinite(startMs) && Date.now() - startMs > STUCK_THRESHOLD_MS;
  });

  function itemElapsedSec(startedAt: string | undefined): number {
    if (!startedAt) return 0;
    const ms = Date.now() - Date.parse(startedAt);
    return Number.isFinite(ms) ? Math.max(0, Math.floor(ms / 1000)) : 0;
  }

  function formatElapsed(seconds: number): string {
    if (seconds <= 0) return "";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  // Reactive subscriptions
  $: pipeline = $pipelineStore;
  $: polling = $runPollingStore;
  $: api = $apiStore;
  $: logs = $filteredLogs;

  onMount(async () => {
    if (!browser) return;

    try {
      await initializeAuth();
      apiService = new PipelineApiService(API_BASE);

      runPollingActions.setHandlers({
        onMessage: handlePollingMessage,
        onLog: addLog,
      });

      await loadInitialData();

      if (api.token) {
        runPollingActions.connect(API_BASE, api.token);
      }

      // Poll queue state at a lower rate to reduce API churn.
      queuePollTimer = setInterval(() => {
        if (document.hidden) return;
        void refreshQueue();
      }, 12000);

      // Restore tab and run detail from URL params
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab");
      if (tabParam === "dashboard" || tabParam === "races" || tabParam === "runs" || tabParam === "agent") {
        activeTab = tabParam;
      }
      const runParam = params.get("run");
      if (runParam) {
        activeTab = "races";
        detailRunId = runParam;
        detailRaceId = params.get("race");
      }

      addLog("info", "Pipeline dashboard initialized");

      window.addEventListener("popstate", handlePopState);
    } catch (error) {
      logger.error("Failed to initialize pipeline dashboard:", error);
      addLog("error", `Initialization failed: ${error}`);
    }
  });

  onDestroy(() => {
    stopElapsedTimer();
    stopAutoRefresh();
    if (queuePollTimer) clearInterval(queuePollTimer);
    runPollingActions.disconnect();
    if (browser) window.removeEventListener("popstate", handlePopState);
  });

  async function loadInitialData() {
    try {
      const [historyResult, queueResult] = await Promise.allSettled([
        apiService.loadRunHistory(),
        apiService.loadQueue(),
      ]);

      if (historyResult.status === "fulfilled") {
        const history = historyResult.value;
        pipelineActions.setRunHistory(history);
      }

      if (queueResult.status === "fulfilled") {
        const queueData = queueResult.value;
        queueItems = queueData.items;
        const running = queueItems.find((i) => i.status === "running");
        if (queueData.running || running) {
          pipelineActions.setCurrentRun(running?.run_id ?? null, "agent");
          pipelineActions.setExecutionState(true);
          pipelineActions.setRunStatus("running");
          startAutoRefresh();
          startElapsedTimer();
          if (running?.run_id) runPollingActions.watchRun(running.run_id);
        } else {
          pipelineActions.setExecutionState(false);
          pipelineActions.setRunStatus("idle");
          stopElapsedTimer();
          stopAutoRefresh();
        }
      }
    } catch (error) {
      logger.error("Failed to load initial data:", error);
      addLog("error", "Failed to load initial data");
    }
  }

  async function refreshQueue() {
    if (!apiService) return;
    try {
      const data = await apiService.loadQueue();
      queueItems = data.items;
      const nowRunning = queueItems.find((i) => i.status === "running");

      if (data.running || nowRunning) {
        if (!pipeline.isExecuting) {
          pipelineActions.setCurrentRun(nowRunning?.run_id ?? null, "agent");
          pipelineActions.setExecutionState(true);
          pipelineActions.setRunStatus("running");
          startAutoRefresh();
          startElapsedTimer();
          if (nowRunning?.run_id) runPollingActions.watchRun(nowRunning.run_id);
        } else if (nowRunning?.run_id && pipeline.currentRunId !== nowRunning.run_id) {
          pipelineActions.setCurrentRun(nowRunning.run_id, "agent");
          runPollingActions.watchRun(nowRunning.run_id);
        }
      } else {
        if (pipeline.isExecuting) {
          pipelineActions.setExecutionState(false);
          pipelineActions.setCurrentRun(null, null);
          pipelineActions.setRunStatus("idle");
          stopElapsedTimer();
          stopAutoRefresh();
          debouncedRefresh();
          racesTabRef?.refresh();
        }
      }
    } catch (e) {
      // Silently ignore poll failures
    }
  }

  const debouncedRefresh = debounce(async () => {
    pipelineActions.setRefreshing(true);
    try {
      const result = await apiService.loadRunHistory();
      pipelineActions.setRunHistory(result);
    } catch (error) {
      logger.error("Refresh failed:", error);
    } finally {
      pipelineActions.setRefreshing(false);
    }
  }, 1000);

  function startAutoRefresh() {
    if (autoRefreshTimer) return;
    autoRefreshTimer = setInterval(async () => {
      if (pipeline.isExecuting) await debouncedRefresh();
    }, 5000);
  }

  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }

  function startElapsedTimer() {
    if (elapsedTimer) return;
    elapsedTimer = setInterval(() => {
      if (pipeline.runStartTime) {
        const elapsed = Math.floor((Date.now() - pipeline.runStartTime) / 1000);
        pipelineActions.updateElapsedTime(elapsed);
      }
    }, 1000);
  }

  function stopElapsedTimer() {
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function addLog(level: string, message: string, timestamp?: string, run_id?: string) {
    pipelineActions.addLog({
      level,
      message,
      timestamp: timestamp || new Date().toISOString(),
      run_id,
    });
  }

  // Polling event handling
  function handlePollingMessage(data: any) {
    switch (data.type) {
      case "run_started":
        pipelineActions.setCurrentRun(data.run_id, data.step);
        pipelineActions.setExecutionState(true);
        pipelineActions.setRunStatus("running");
        pipelineActions.updateRunProgress(0, "Initializing...");
        runPollingActions.watchRun(data.run_id);
        startAutoRefresh();
        startElapsedTimer();
        break;
      case "run_progress":
        pipelineActions.updateRunProgress(
          data.progress ?? pipeline.progress,
          data.message ?? pipeline.progressMessage
        );
        break;
      case "run_status":
        if (data.data?.run_id === pipeline.currentRunId || data.data?.run_id === detailRunId) {
          liveRun = data.data;
        }
        break;
      case "run_completed":
        pipelineActions.setRunStatus("completed");
        pipelineActions.updateRunProgress(100, "Completed successfully");
        pipelineActions.setExecutionState(false);
        if (data.result !== undefined) pipelineActions.setOutput(data.result);
        stopAutoRefresh();
        stopElapsedTimer();
        debouncedRefresh();
        racesTabRef?.refresh();
        refreshQueue();
        break;
      case "run_failed":
        pipelineActions.setRunStatus("failed");
        pipelineActions.setExecutionState(false);
        addLog("error", `Run failed: ${data.error || "Unknown error"}`);
        stopAutoRefresh();
        stopElapsedTimer();
        debouncedRefresh();
        refreshQueue();
        break;
      case "log":
        addLog(data.level ?? "info", data.message ?? "", data.timestamp, data.run_id);
        break;
    }
  }

  // -- Race Panel / Batch handlers --

  function handleSelectRace(race: RaceRecord) {
    selectedRace = race;
    racePanelOpen = true;
  }

  function handleBatchQueue(raceIds: string[]) {
    batchRaceIds = raceIds;
    batchModalOpen = true;
  }

  function handleAddRaces(event: CustomEvent<string>) {
    const raw = event.detail;
    const ids = raw.split(",").map((s: string) => s.trim()).filter(Boolean);
    if (ids.length === 0) return;
    handleBatchQueue(ids);
  }

  function handleRacePanelClose() {
    racePanelOpen = false;
    selectedRace = null;
  }

  function handleRacePanelRunStarted(event: CustomEvent<{ race_id: string; run_id: string }>) {
    addLog("info", `Started run for ${event.detail.race_id}: ${event.detail.run_id}`);
    refreshQueue();
    racesTabRef?.refresh();
  }

  function handleRacePanelUpdated() {
    racesTabRef?.refresh();
    // Refresh the selected race data
    if (selectedRace) {
      apiService.getRaceRecord(selectedRace.race_id).then((r) => {
        selectedRace = r;
      }).catch(() => {});
    }
  }

  function handleRacePanelViewRun(event: CustomEvent<string>) {
    racePanelOpen = false;
    openRunDetail(event.detail, selectedRace?.race_id ?? null);
  }

  function handleRunsTabViewRun(event: CustomEvent<{ runId: string; raceId: string | null }>) {
    openRunDetail(event.detail.runId, event.detail.raceId);
  }

  async function handleClearQueue() {
    try {
      const result = await apiService.clearPendingQueue();
      addLog("info", `Cleared ${result.removed} pending item${result.removed !== 1 ? "s" : ""} from the queue`);
      await refreshQueue();
      racesTabRef?.refresh();
    } catch (e) {
      addLog("error", `Failed to clear queue: ${e}`);
    }
  }

  async function handleDeleteItem(event: CustomEvent<{ itemId?: string; runId?: string }>) {
    try {
      if (event.detail.itemId) {
        await apiService.removeQueueItem(event.detail.itemId);
      } else if (event.detail.runId) {
        // For active/running runs, try to cancel via the queue item first
        const queueMatch = queueItems.find((q) => q.run_id === event.detail.runId);
        if (queueMatch) {
          await apiService.removeQueueItem(queueMatch.id);
        } else {
          await apiService.deleteRun(event.detail.runId!);
        }
      }
      await refreshQueue();
      racesTabRef?.refresh();
      debouncedRefresh();
    } catch (e) {
      // Retry with force for stuck/broken items
      try {
        const itemId = event.detail.itemId ?? queueItems.find((q) => q.run_id === event.detail.runId)?.id;
        if (itemId) {
          await apiService.removeQueueItem(itemId, true);
          await refreshQueue();
          racesTabRef?.refresh();
          debouncedRefresh();
          addLog("warning", "Force-removed stuck queue item");
          return;
        }
      } catch (_retryErr) {
        // fall through to original error
      }
      addLog("error", `Failed to delete item: ${e}`);
    }
  }

  function handleBatchQueued(event: CustomEvent<{ added: number; errors: string[] }>) {
    batchModalOpen = false;
    batchRaceIds = [];
    if (event.detail.added > 0) {
      addLog("info", `Queued ${event.detail.added} races`);
    }
    for (const err of event.detail.errors) {
      addLog("warning", err);
    }
    racesTabRef?.refresh();
    refreshQueue();
  }

  function handleLogFilterChange(event: { detail: "all" | "debug" | "info" | "warning" | "error" }) {
    pipelineActions.setLogFilter(event.detail);
  }

  function handleClearLogs() {
    pipelineActions.clearLogs();
  }

  async function handleArtifactClick(event: { detail: Artifact }) {
    const artifact = event.detail;
    modalLoading = false;
    showModal = true;
    modalTitle = "Artifact Details";
    modalData = artifact as unknown as Record<string, unknown>;
  }

  function closeModal() {
    showModal = false;
    modalData = null;
    modalTitle = "";
    modalLoading = false;
  }

  function handleActiveRunClick(runId: string | undefined, raceId: string | undefined) {
    if (runId) {
      activeTab = "races";
      openRunDetail(runId, raceId ?? null);
    }
  }

  $: modalDataTooLarge = (() => {
    if (!modalData) return false;
    try {
      return JSON.stringify(modalData, null, 2).length > 200000;
    } catch {
      return true;
    }
  })();

  $: safeModalDisplay = (() => {
    if (!modalData) return "";
    return safeJsonStringify(modalData, 200000).content;
  })();
</script>

<svelte:head>
  <title>Admin Console - SmarterVote</title>
</svelte:head>

<div class="w-full px-4 max-w-[1600px] mx-auto {activeTab === 'agent' ? 'h-dvh flex flex-col overflow-hidden pt-6 pb-2' : 'py-6'}">
  <!-- Header -->
  <div class="mt-2 mb-6 card p-4">
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-4">
        <h1 class="text-xl font-bold text-content">Admin Console</h1>
        <span class="text-sm text-content-subtle">SmarterVote</span>
      </div>
      <div class="flex items-center space-x-2">
        <div class="w-3 h-3 rounded-full {polling.connected ? 'bg-green-500' : 'bg-red-500'}" />
        <span class="text-sm text-content-muted">
          {polling.connected ? "Connected" : "Disconnected"}
        </span>
        {#if pipeline.isRefreshing}
          <div class="flex items-center space-x-1">
            <svg class="animate-spin h-3 w-3 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span class="text-xs text-blue-600">Refreshing...</span>
          </div>
        {/if}
      </div>
    </div>
  </div>

  <!-- Tab navigation -->
  <AdminTabs
    bind:activeTab
    alertCount={alertBadgeCount}
    runsBadgeCount={queueItems.filter((q) => q.status === "running" || q.status === "pending").length}
  />

  <!-- Running banner (visible across tabs) — shows all active runs -->
  {#if pipeline.isExecuting || queueRunningItems.length > 0}
    <div class="mb-4 card border-blue-200 bg-blue-50 dark:bg-blue-900/20 overflow-hidden">
      <!-- Header row -->
      <div class="flex items-center gap-2 px-4 pt-3 pb-2 border-b border-blue-200 dark:border-blue-800">
        <svg class="animate-spin h-4 w-4 text-blue-600 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span class="text-sm font-semibold text-blue-900 dark:text-blue-200">
          {queueRunningItems.length} run{queueRunningItems.length !== 1 ? 's' : ''} in progress
          {#if queuePending > 0}
            <span class="font-normal text-blue-700 dark:text-blue-300">· {queuePending} queued</span>
          {/if}
        </span>
      </div>
      <!-- One row per running item -->
      <div class="divide-y divide-blue-100 dark:divide-blue-900/40">
        {#each queueRunningItems as item (item.id)}
          {@const isPrimary = item.run_id === pipeline.currentRunId}
          {@const elapsedSec = itemElapsedSec(item.started_at)}
          {@const isStuck = stuckRunItems.some((s) => s.id === item.id)}
          <button
            type="button"
            class="w-full text-left px-4 py-2.5 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors {isStuck ? 'bg-amber-50 dark:bg-amber-900/10' : ''}"
            on:click={() => handleActiveRunClick(item.run_id, item.race_id)}
            title="View run details"
          >
            <div class="flex items-center gap-3">
              <span class="font-mono text-sm font-medium text-blue-900 dark:text-blue-100 truncate flex-1">{item.race_id || item.run_id || 'Unknown race'}</span>
              {#if isStuck}
                <span class="text-xs px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 shrink-0">likely timed out</span>
              {:else if isPrimary && pipeline.progress > 0}
                <span class="text-sm font-bold text-blue-800 dark:text-blue-200 shrink-0">{pipeline.progress}%</span>
              {:else if elapsedSec > 0}
                <span class="text-xs text-blue-600 dark:text-blue-400 shrink-0">{formatElapsed(elapsedSec)}</span>
              {/if}
              <svg class="w-4 h-4 text-blue-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </div>
            {#if isPrimary && (pipeline.progressMessage || pipeline.elapsedTime)}
              <div class="mt-1.5">
                <p class="text-xs text-blue-700 dark:text-blue-300 truncate">
                  {pipeline.progressMessage || 'Running'}
                  {#if pipeline.elapsedTime > 0}· {formatElapsed(pipeline.elapsedTime)}{/if}
                </p>
                <div class="mt-1 w-full bg-blue-200 dark:bg-blue-800 rounded-full h-1">
                  <div class="bg-blue-600 h-1 rounded-full transition-all duration-700" style="width: {pipeline.progress}%" />
                </div>
              </div>
            {:else if !isPrimary && elapsedSec > 0}
              <p class="mt-0.5 text-xs text-blue-600 dark:text-blue-400">Running · {formatElapsed(elapsedSec)}</p>
            {/if}
          </button>
        {/each}
      </div>
    </div>
  {/if}

  {#if stuckRunItems.length > 0}
    <div class="mb-4 card p-3 border-amber-300 bg-amber-50 dark:bg-amber-900/20">
      <p class="text-sm font-medium text-amber-800 dark:text-amber-200">
        {stuckRunItems.length} run{stuckRunItems.length !== 1 ? 's' : ''} may have timed out
      </p>
      <p class="text-xs text-amber-700 dark:text-amber-300 mt-1">
        {stuckRunItems.map((i) => i.race_id).join(", ")} — still showing "running" after {Math.floor(STUCK_THRESHOLD_MS / 60000)} minutes.
        Cloud Functions typically time out at ~9 minutes. Click the run to force-cancel it.
      </p>
    </div>
  {/if}

  {#if queueLikelyStalled}
    <div class="mb-4 card p-3 border-amber-300 bg-amber-50 dark:bg-amber-900/20">
      <p class="text-sm font-medium text-amber-800 dark:text-amber-200">Queue appears stalled</p>
      <p class="text-xs text-amber-700 dark:text-amber-300 mt-1">
        {queuePending} pending item{queuePending !== 1 ? "s" : ""} and no active runner for over 3 minutes.
        This usually means the queue worker is not consuming Firestore queue documents.
      </p>
    </div>
  {/if}

  <!-- Dashboard tab -->
  {#if activeTab === "dashboard"}
    <DashboardTab
      onAlertCountChange={(n) => (alertBadgeCount = n)}
      {apiService}
      on:view-runs={() => (activeTab = "runs")}
      on:view-run={(event) => openRunDetail(event.detail.runId, event.detail.raceId)}
    />
  {/if}

  <!-- Races tab -->
  {#if activeTab === "races"}
    {#if showingDetail && detailRunId}
      <RunDetailPanel
        runId={detailRunId}
        {apiService}
        isLive={queueRunningItems.some((q) => q.run_id === detailRunId)}
        liveLogs={logs}
        liveProgress={pipeline.progress}
        liveProgressMessage={pipeline.progressMessage}
        liveElapsed={pipeline.elapsedTime}
        {liveRun}
        on:back={() => closeRunDetail()}
        on:deleted={() => { closeRunDetail(); racesTabRef?.refresh(); debouncedRefresh(); refreshQueue(); }}
        on:cancelled={() => { closeRunDetail(); refreshQueue(); debouncedRefresh(); racesTabRef?.refresh(); }}
      />
    {:else}
      <RacesTab
        bind:this={racesTabRef}
        onSelectRace={handleSelectRace}
        onBatchQueue={handleBatchQueue}
        on:addRaces={handleAddRaces}
      />

      <!-- Live Logs (collapsible, below races grid) -->
      {#if logs.length > 0}
        <div class="mt-4">
          <LiveLogs
            {logs}
            logFilter={pipeline.logFilter}
            connected={polling.connected}
            on:filter-change={handleLogFilterChange}
            on:clear-logs={handleClearLogs}
          />
        </div>
      {/if}
    {/if}
  {/if}

  <!-- Agent chat tab -->
  {#if activeTab === "agent"}
    <AdminChatTab {apiService} />
  {/if}

  <!-- Runs tab -->
  {#if activeTab === "runs"}
    {#if showingDetail && detailRunId}
      <RunDetailPanel
        runId={detailRunId}
        {apiService}
        isLive={queueRunningItems.some((q) => q.run_id === detailRunId)}
        liveLogs={logs}
        liveProgress={pipeline.progress}
        liveProgressMessage={pipeline.progressMessage}
        liveElapsed={pipeline.elapsedTime}
        {liveRun}
        on:back={() => closeRunDetail()}
        on:deleted={() => { closeRunDetail(); debouncedRefresh(); refreshQueue(); }}
        on:cancelled={() => { closeRunDetail(); refreshQueue(); debouncedRefresh(); }}
      />
    {:else}
      <RunsTab
        runs={pipeline.runHistory ?? []}
        {queueItems}
        isRefreshing={pipeline.isRefreshing}
        currentRunId={pipeline.currentRunId}
        on:view-run={handleRunsTabViewRun}
        on:refresh={debouncedRefresh}
        on:clear-queue={handleClearQueue}
        on:delete-item={handleDeleteItem}
      />
    {/if}
  {/if}
</div>

<!-- Race Panel (slide-over) -->
{#if selectedRace}
  <RacePanel
    race={selectedRace}
    open={racePanelOpen}
    on:close={handleRacePanelClose}
    on:runStarted={handleRacePanelRunStarted}
    on:updated={handleRacePanelUpdated}
    on:viewRun={handleRacePanelViewRun}
  />
{/if}

<!-- Batch Queue Modal -->
<BatchQueueModal
  open={batchModalOpen}
  raceIds={batchRaceIds}
  on:close={() => { batchModalOpen = false; batchRaceIds = []; }}
  on:queued={handleBatchQueued}
/>

<!-- Modal -->
<PipelineModal
  show={showModal}
  title={modalTitle}
  loading={modalLoading}
  contentTooLarge={modalDataTooLarge}
  on:close={closeModal}
>
  {safeModalDisplay}
</PipelineModal>

<style>
  /* no custom styles needed — using Tailwind utilities */
</style>
