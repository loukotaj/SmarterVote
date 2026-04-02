<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";

  // Stores
  import {
    pipelineStore,
    pipelineActions,
    filteredLogs,
    safeOutputDisplay,
  } from "$lib/stores/pipelineStore";
  import { websocketStore, websocketActions } from "$lib/stores/websocketStore";
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

  // Utilities
  import { debounce, safeJsonStringify } from "$lib/utils/pipelineUtils";
  import { logger } from "$lib/utils/logger";
  import type { RunHistoryItem, Artifact, RaceRecord } from "$lib/types";

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

  let apiService: PipelineApiService;
  let racesTabRef: RacesTab;
  let elapsedTimer: ReturnType<typeof setInterval> | null = null;
  let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;
  let queuePollTimer: ReturnType<typeof setInterval> | null = null;

  // Tab state
  let activeTab: "dashboard" | "races" = "dashboard";
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
  $: showingDetail = !!detailRunId;

  function setDetailRunId(runId: string | null) {
    detailRunId = runId;
    if (!browser) return;
    const url = new URL(window.location.href);
    if (runId) {
      url.searchParams.set("run", runId);
      url.searchParams.set("tab", "races");
    } else {
      url.searchParams.delete("run");
    }
    goto(url.pathname + url.search, { replaceState: true, noScroll: true, keepFocus: true });
  }

  // Reactive computed
  $: queueRunning = queueItems.find((i) => i.status === "running");
  $: queuePending = queueItems.filter((i) => i.status === "pending").length;

  // Reactive subscriptions
  $: pipeline = $pipelineStore;
  $: websocket = $websocketStore;
  $: api = $apiStore;
  $: logs = $filteredLogs;

  onMount(async () => {
    if (!browser) return;

    try {
      await initializeAuth();
      apiService = new PipelineApiService(API_BASE);

      websocketActions.setHandlers({
        onMessage: handleWebSocketMessage,
        onLog: addLog,
      });

      await loadInitialData();

      if (api.token) {
        websocketActions.connect(API_BASE, api.token);
      }

      // Start polling queue state every 4s
      queuePollTimer = setInterval(refreshQueue, 4000);

      // Restore tab and run detail from URL params
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab");
      if (tabParam === "dashboard" || tabParam === "races") {
        activeTab = tabParam;
      }
      const runParam = params.get("run");
      if (runParam) {
        activeTab = "races";
        detailRunId = runParam;
      }

      addLog("info", "Pipeline dashboard initialized");
    } catch (error) {
      logger.error("Failed to initialize pipeline dashboard:", error);
      addLog("error", `Initialization failed: ${error}`);
    }
  });

  onDestroy(() => {
    stopElapsedTimer();
    stopAutoRefresh();
    if (queuePollTimer) clearInterval(queuePollTimer);
    websocketActions.disconnect();
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
        queueItems = queueResult.value.items;
        const running = queueItems.find((i) => i.status === "running");
        if (running && running.run_id) {
          pipelineActions.setCurrentRun(running.run_id, "agent");
          pipelineActions.setExecutionState(true);
          pipelineActions.setRunStatus("running");
          startAutoRefresh();
          startElapsedTimer();
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

      if (nowRunning && nowRunning.run_id) {
        if (!pipeline.isExecuting) {
          pipelineActions.setCurrentRun(nowRunning.run_id, "agent");
          pipelineActions.setExecutionState(true);
          pipelineActions.setRunStatus("running");
          startAutoRefresh();
          startElapsedTimer();
        }
      } else {
        if (pipeline.isExecuting) {
          pipelineActions.setExecutionState(false);
          stopElapsedTimer();
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

  // WebSocket message handling
  function handleWebSocketMessage(data: any) {
    switch (data.type) {
      case "run_started":
        pipelineActions.setCurrentRun(data.run_id, data.step);
        pipelineActions.setRunStatus("running");
        pipelineActions.updateRunProgress(0, "Initializing...");
        startAutoRefresh();
        break;
      case "run_progress":
        pipelineActions.updateRunProgress(
          data.progress ?? pipeline.progress,
          data.message ?? pipeline.progressMessage
        );
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

  async function handleAddRaces(event: CustomEvent<string>) {
    const raw = event.detail;
    const ids = raw.split(",").map((s: string) => s.trim()).filter(Boolean);
    if (ids.length === 0) return;

    try {
      const result = await apiService.queueRaces(ids, { cheap_mode: true });
      if (result.added.length > 0) {
        addLog("info", `Queued ${result.added.length} race(s): ${result.added.map((a) => a.race_id).join(", ")}`);
      }
      for (const err of result.errors) {
        addLog("warning", `${err.race_id}: ${err.error}`);
      }
      await racesTabRef?.refresh();
      await refreshQueue();
    } catch (e) {
      addLog("error", `Failed to queue: ${e}`);
    }
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
    setDetailRunId(event.detail);
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
    modalLoading = true;
    showModal = true;
    modalTitle = "Artifact Details";
    modalData = null;

    try {
      const artifactId = artifact.id || (artifact as any).artifact_id || (artifact as any)._id;
      modalData = artifactId ? await apiService.getArtifact(artifactId) : artifact;
    } catch (e) {
      modalData = { error: String(e), ...artifact };
    }
    modalLoading = false;
  }

  function closeModal() {
    showModal = false;
    modalData = null;
    modalTitle = "";
    modalLoading = false;
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

<div class="w-full px-4 py-6 max-w-[1600px] mx-auto">
  <!-- Header -->
  <div class="mt-2 mb-6 card p-4">
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-4">
        <h1 class="text-xl font-bold text-content">Admin Console</h1>
        <span class="text-sm text-content-subtle">SmarterVote</span>
      </div>
      <div class="flex items-center space-x-2">
        <div class="w-3 h-3 rounded-full {websocket.connected ? 'bg-green-500' : 'bg-red-500'}" />
        <span class="text-sm text-content-muted">
          {websocket.connected ? "Connected" : "Disconnected"}
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
  <AdminTabs bind:activeTab alertCount={alertBadgeCount} />

  <!-- Running banner (visible across tabs) -->
  {#if pipeline.isExecuting}
    <div class="mb-4 card p-4 border-blue-200 bg-blue-50 dark:bg-blue-900/20">
      <div class="flex items-center gap-3">
        <svg class="animate-spin h-5 w-5 text-blue-600 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-semibold text-blue-900 dark:text-blue-200">
            Researching{queueRunning ? ` ${queueRunning.race_id}` : ''}…
          </p>
          <p class="text-xs text-blue-700 dark:text-blue-300 mt-0.5">
            {pipeline.progressMessage || 'Running'}
            {#if queuePending > 0} · {queuePending} more in queue{/if}
          </p>
        </div>
        <div class="text-right shrink-0">
          <p class="text-lg font-bold text-blue-800 dark:text-blue-200">{pipeline.progress}%</p>
        </div>
      </div>
      <div class="mt-2 w-full bg-blue-200 dark:bg-blue-800 rounded-full h-1.5">
        <div class="bg-blue-600 h-1.5 rounded-full transition-all duration-700" style="width: {pipeline.progress}%" />
      </div>
    </div>
  {/if}

  <!-- Dashboard tab -->
  {#if activeTab === "dashboard"}
    <DashboardTab
      onAlertCountChange={(n) => (alertBadgeCount = n)}
      recentRuns={pipeline.runHistory ?? []}
    />
  {/if}

  <!-- Races tab -->
  {#if activeTab === "races"}
    {#if showingDetail && detailRunId}
      <RunDetailPanel
        runId={detailRunId}
        isLive={pipeline.isExecuting && pipeline.currentRunId === detailRunId}
        liveLogs={logs}
        liveProgress={pipeline.progress}
        liveProgressMessage={pipeline.progressMessage}
        liveElapsed={pipeline.elapsedTime}
        on:back={() => setDetailRunId(null)}
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
            connected={websocket.connected}
            on:filter-change={handleLogFilterChange}
            on:clear-logs={handleClearLogs}
          />
        </div>
      {/if}
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
