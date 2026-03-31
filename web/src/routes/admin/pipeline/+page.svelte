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
  import { websocketStore, websocketActions } from "$lib/stores/websocketStore";
  import { apiStore, initializeAuth } from "$lib/stores/apiStore";

  // Services
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import type { PublishedRaceSummary, QueueItem } from "$lib/services/pipelineApiService";

  // Components
  import LiveLogs from "$lib/components/LiveLogs.svelte";
  import PipelineModal from "$lib/components/PipelineModal.svelte";
  import AdminTabs from "$lib/components/admin/AdminTabs.svelte";
  import DashboardTab from "$lib/components/admin/DashboardTab.svelte";
  import RacesTab from "$lib/components/admin/RacesTab.svelte";
  import RunDetailPanel from "$lib/components/admin/RunDetailPanel.svelte";

  // Utilities
  import { debounce, safeJsonStringify, downloadAsJson } from "$lib/utils/pipelineUtils";
  import { logger } from "$lib/utils/logger";
  import type { RunHistoryItem, Artifact } from "$lib/types";

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

  let apiService: PipelineApiService;
  let racesTabRef: RacesTab;
  let elapsedTimer: ReturnType<typeof setInterval> | null = null;
  let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;
  let queuePollTimer: ReturnType<typeof setInterval> | null = null;

  // Tab state
  let activeTab: "dashboard" | "races" | "pipeline" = "dashboard";
  let alertBadgeCount = 0;

  // Modal state
  let showModal = false;
  let modalTitle = "";
  let modalData: unknown = null;
  let modalLoading = false;

  // Pipeline options
  let enableReview = true;
  let cheapMode = true;
  let showAdvanced = false;
  let researchModel = "";
  let claudeModel = "";
  let geminiModel = "";
  let grokModel = "";

  // Server-side queue state
  let queueItems: QueueItem[] = [];
  let queueLoading = false;
  let addingToQueue = false;

  // Run detail view
  let detailRunId: string | null = null;
  $: showingDetail = !!detailRunId;

  // Reactive computed
  $: queueRunning = queueItems.find((i) => i.status === "running");
  $: queuePending = queueItems.filter((i) => i.status === "pending").length;
  $: queueFinished = queueItems.filter((i) => ["completed", "failed", "cancelled"].includes(i.status)).length;
  $: queueHasActive = !!queueRunning || queuePending > 0;

  function handleRaceIdInput(e: Event) {
    pipelineActions.setRaceId((e.currentTarget as HTMLInputElement).value);
  }

  function handleRaceIdKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") handleAddToQueue();
  }

  // Published races
  let publishedRaces: PublishedRaceSummary[] = [];
  let racesLoading = false;

  // Auto-refresh management
  const MIN_REFRESH_INTERVAL = 2000;
  let pendingRefresh = false;

  // Reactive subscriptions
  $: pipeline = $pipelineStore;
  $: websocket = $websocketStore;
  $: api = $apiStore;
  $: logs = $filteredLogs;
  $: _outputDisplay = $safeOutputDisplay;

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
      const [artifactsResult, historyResult, racesResult, queueResult] = await Promise.allSettled([
        apiService.loadArtifacts(),
        apiService.loadRunHistory(),
        apiService.loadPublishedRaces(),
        apiService.loadQueue(),
      ]);

      if (artifactsResult.status === "fulfilled") {
        pipelineActions.setArtifacts(artifactsResult.value);
      }

      if (historyResult.status === "fulfilled") {
        const history = historyResult.value;
        pipelineActions.setRunHistory(history);

        // Restore executing state if a run is still active (e.g. after page refresh)
        const activeRun = history.find((r: RunHistoryItem) => r.status === "running" || r.status === "pending");
        if (activeRun) {
          addLog("info", `Resuming monitoring of active run ${activeRun.run_id}`);
          pipelineActions.setCurrentRun(activeRun.run_id, activeRun.last_step ?? null);
          pipelineActions.setExecutionState(true);
          pipelineActions.setRunStatus("running");
          startAutoRefresh();
          startElapsedTimer();
        }
      }

      if (racesResult.status === "fulfilled") {
        publishedRaces = racesResult.value;
      }

      if (queueResult.status === "fulfilled") {
        queueItems = queueResult.value.items;
        // If the server has a running item, sync our execution state
        const running = queueItems.find((i) => i.status === "running");
        if (running && running.run_id && !pipeline.isExecuting) {
          pipelineActions.setCurrentRun(running.run_id, "agent");
          pipelineActions.setExecutionState(true);
          pipelineActions.setRunStatus("running");
          startAutoRefresh();
          startElapsedTimer();
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
      const wasRunning = !!queueItems.find((i) => i.status === "running");
      queueItems = data.items;
      const nowRunning = queueItems.find((i) => i.status === "running");

      // Sync execution state with server queue
      if (nowRunning && nowRunning.run_id && !pipeline.isExecuting) {
        pipelineActions.setCurrentRun(nowRunning.run_id, "agent");
        pipelineActions.setExecutionState(true);
        pipelineActions.setRunStatus("running");
        startAutoRefresh();
        startElapsedTimer();
      }

      // If was running but now finished, refresh other data
      if (wasRunning && !nowRunning) {
        pipelineActions.setExecutionState(false);
        stopElapsedTimer();
        debouncedRefresh();
        racesTabRef?.refresh();
      }
    } catch (e) {
      // Silently ignore poll failures
    }
  }

  const debouncedRefresh = debounce(async () => {
    if (pendingRefresh) return;
    const timeSinceLastRefresh = Date.now() - pipeline.lastRefreshTime;
    if (timeSinceLastRefresh < MIN_REFRESH_INTERVAL) return;

    pendingRefresh = true;
    pipelineActions.setRefreshing(true);

    try {
      const [historyResult, artifactsResult] = await Promise.allSettled([
        apiService.loadRunHistory(),
        apiService.loadArtifacts(),
      ]);

      if (historyResult.status === "fulfilled") {
        pipelineActions.setRunHistory(historyResult.value);
      }
      if (artifactsResult.status === "fulfilled") {
        pipelineActions.setArtifacts(artifactsResult.value);
      }
    } catch (error) {
      logger.error("Refresh failed:", error);
    } finally {
      pendingRefresh = false;
      pipelineActions.setRefreshing(false);
    }
  }, 1000);

  function startAutoRefresh() {
    if (autoRefreshTimer) return;
    autoRefreshTimer = setInterval(async () => {
      if (pipeline.isExecuting) {
        await debouncedRefresh();
      }
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

  async function refreshPublishedRaces() {
    racesLoading = true;
    try {
      publishedRaces = await apiService.loadPublishedRaces();
    } catch (e) {
      logger.error("Failed to refresh published races:", e);
    } finally {
      racesLoading = false;
    }
  }

  // -- Queue Operations (server-side) --

  function buildOptions(): Record<string, any> {
    const opts: Record<string, any> = {
      save_artifact: true,
      enable_review: enableReview,
      cheap_mode: cheapMode,
    };
    if (researchModel) opts.research_model = researchModel;
    if (claudeModel) opts.claude_model = claudeModel;
    if (geminiModel) opts.gemini_model = geminiModel;
    if (grokModel) opts.grok_model = grokModel;
    return opts;
  }

  async function handleAddToQueue() {
    const raw = pipeline.raceId.trim();
    if (!raw) return;
    const ids = raw.split(",").map((s) => s.trim()).filter(Boolean);
    if (ids.length === 0) return;

    addingToQueue = true;
    try {
      const result = await apiService.addToQueue(ids, buildOptions());
      if (result.added.length > 0) {
        addLog("info", `Queued ${result.added.length} race(s): ${result.added.map((a) => a.race_id).join(", ")}`);
        pipelineActions.setRaceId("");
      }
      for (const err of result.errors) {
        addLog("warning", `${err.race_id}: ${err.error}`);
      }
      await refreshQueue();
    } catch (e) {
      addLog("error", `Failed to queue: ${e}`);
    } finally {
      addingToQueue = false;
    }
  }

  async function handleQueueRace(race: PublishedRaceSummary) {
    try {
      const result = await apiService.addToQueue([race.id], buildOptions());
      if (result.added.length > 0) {
        addLog("info", `Queued update for ${race.id}`);
      }
      for (const err of result.errors) {
        addLog("warning", `${err.race_id}: ${err.error}`);
      }
      await refreshQueue();
    } catch (e) {
      addLog("error", `Failed to queue ${race.id}: ${e}`);
    }
  }

  async function handleQueueRaceById(race_id: string) {
    if (!apiService) return;
    try {
      const result = await apiService.addToQueue([race_id], buildOptions());
      if (result.added.length > 0) {
        addLog("info", `Queued update for ${race_id}`);
        activeTab = "pipeline";
      }
      for (const err of result.errors) {
        addLog("warning", `${err.race_id}: ${err.error}`);
      }
      await refreshQueue();
    } catch (e) {
      addLog("error", `Failed to queue ${race_id}: ${e}`);
    }
  }

  async function handleRemoveQueueItem(item: QueueItem) {
    try {
      await apiService.removeQueueItem(item.id);
      await refreshQueue();
    } catch (e) {
      addLog("error", `Failed to remove queue item: ${e}`);
    }
  }

  async function handleClearFinishedQueue() {
    try {
      const result = await apiService.clearFinishedQueue();
      if (result.removed > 0) {
        addLog("info", `Cleared ${result.removed} finished queue items`);
      }
      await refreshQueue();
    } catch (e) {
      addLog("error", `Failed to clear queue: ${e}`);
    }
  }

  async function handleDeleteRace(race: PublishedRaceSummary) {
    if (!confirm(`Delete race "${race.id}"? This removes the published data and cannot be undone.`)) {
      return;
    }
    try {
      await apiService.deletePublishedRace(race.id);
      addLog("info", `Deleted race: ${race.id}`);
      await racesTabRef?.refresh();
    } catch (e) {
      logger.error("Failed to delete race:", e);
      addLog("error", `Failed to delete race ${race.id}: ${e}`);
    }
  }

  async function handleExportRace(race: PublishedRaceSummary) {
    try {
      const data = await apiService.getPublishedRace(race.id);
      downloadAsJson(data, `${race.id}.json`);
      addLog("info", `Exported race: ${race.id}`);
    } catch (e) {
      logger.error("Failed to export race:", e);
      addLog("error", `Failed to export race ${race.id}: ${e}`);
    }
  }

  function handleStopExecution() {
    if (pipeline.currentRunId && websocket.ws && websocket.ws.readyState === WebSocket.OPEN) {
      websocketActions.send({ type: "stop_run", run_id: pipeline.currentRunId });
    }
    pipelineActions.setExecutionState(false);
    stopElapsedTimer();
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

  async function handleRunDetails(event: { detail: RunHistoryItem }) {
    const run = event.detail;
    detailRunId = run.run_id;
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
        <h1 class="text-xl font-bold text-gray-900">Admin Console</h1>
        <span class="text-sm text-gray-500">SmarterVote</span>
      </div>
      <div class="flex items-center space-x-2">
        <div class="w-3 h-3 rounded-full {websocket.connected ? 'bg-green-500' : 'bg-red-500'}" />
        <span class="text-sm text-gray-600">
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

  <!-- Dashboard tab -->
  {#if activeTab === "dashboard"}
    <DashboardTab
      onAlertCountChange={(n) => (alertBadgeCount = n)}
      recentRuns={pipeline.runHistory ?? []}
    />
  {/if}

  <!-- Races tab -->
  {#if activeTab === "races"}
    <RacesTab bind:this={racesTabRef} onUpdateRace={handleQueueRaceById} />
  {/if}

  <!-- Pipeline tab -->
  {#if activeTab === "pipeline"}
    {#if showingDetail && detailRunId}
      <RunDetailPanel
        runId={detailRunId}
        isLive={pipeline.isExecuting && pipeline.currentRunId === detailRunId}
        liveLogs={logs}
        liveProgress={pipeline.progress}
        liveProgressMessage={pipeline.progressMessage}
        liveElapsed={pipeline.elapsedTime}
        on:back={() => (detailRunId = null)}
      />
    {:else}
      <!-- Queue + Controls -->
      <div class="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-5">
        <!-- Left: Controls -->
        <div class="space-y-4">
          <!-- Research a Race -->
          <div class="card p-4">
            <h3 class="text-base font-semibold text-gray-900 mb-3">Research a Race</h3>
            <div class="space-y-3">
              <div>
                <div class="flex gap-2">
                  <input
                    id="raceId"
                    type="text"
                    value={pipeline.raceId}
                    on:input={handleRaceIdInput}
                    on:keydown={handleRaceIdKeydown}
                    placeholder="e.g. ga-senate-2026, tx-governor-2026"
                    class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  />
                  <button
                    type="button"
                    on:click={handleAddToQueue}
                    disabled={!pipeline.raceId.trim() || addingToQueue}
                    title="Add to queue"
                    class="btn-primary px-4 py-2 text-sm rounded-lg whitespace-nowrap disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                  >
                    {#if addingToQueue}
                      <svg class="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                        <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Queuing…
                    {:else}
                      + Queue
                    {/if}
                  </button>
                </div>
                <p class="mt-1 text-xs text-gray-400">
                  Comma-separate multiple IDs · <kbd class="px-1 py-0.5 bg-gray-100 rounded text-xs">Enter</kbd> to add
                </p>
              </div>

              <!-- Mode Toggles -->
              <div class="flex items-center gap-5">
                <label class="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input type="checkbox" bind:checked={cheapMode} class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                  <span>Cheap Mode</span>
                </label>
                <label class="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input type="checkbox" bind:checked={enableReview} class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                  <span>AI Review</span>
                  <span class="text-xs text-gray-400">✦</span>
                </label>
              </div>

              <!-- Advanced Model Config -->
              <button
                type="button"
                on:click={() => (showAdvanced = !showAdvanced)}
                class="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                <svg class="w-3 h-3 transition-transform {showAdvanced ? 'rotate-90' : ''}" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd" />
                </svg>
                Advanced Model Settings
              </button>
              {#if showAdvanced}
                <div class="space-y-2.5 border-t border-gray-200 pt-2.5">
                  <p class="text-xs text-gray-400">Leave on default, or override for this run.</p>
                  <div>
                    <label for="researchModel" class="block text-xs font-medium text-gray-600 mb-1">Research (OpenAI)</label>
                    <select id="researchModel" bind:value={researchModel}
                      class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:border-blue-500 bg-white">
                      <option value="">Default — {cheapMode ? 'gpt-5.4-mini' : 'gpt-5.4'}</option>
                      <option value="gpt-5.4">gpt-5.4 · best quality</option>
                      <option value="gpt-5.4-mini">gpt-5.4-mini · fast & smart</option>
                      <option value="gpt-5-nano">gpt-5-nano · fastest, cheapest</option>
                    </select>
                  </div>
                  <div class="grid grid-cols-3 gap-2">
                    <div>
                      <label for="claudeModel" class="block text-xs font-medium text-gray-600 mb-1">Claude</label>
                      <select id="claudeModel" bind:value={claudeModel}
                        class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:border-blue-500 bg-white">
                        <option value="">Default</option>
                        <option value="claude-sonnet-4-6">Sonnet 4.6</option>
                        <option value="claude-haiku-4-5-20251001">Haiku 4.5</option>
                      </select>
                    </div>
                    <div>
                      <label for="geminiModel" class="block text-xs font-medium text-gray-600 mb-1">Gemini</label>
                      <select id="geminiModel" bind:value={geminiModel}
                        class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:border-blue-500 bg-white">
                        <option value="">Default</option>
                        <option value="gemini-3-flash-preview">3 Flash</option>
                        <option value="gemini-3.1-flash-lite-preview">3.1 Lite</option>
                      </select>
                    </div>
                    <div>
                      <label for="grokModel" class="block text-xs font-medium text-gray-600 mb-1">Grok</label>
                      <select id="grokModel" bind:value={grokModel}
                        class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:border-blue-500 bg-white">
                        <option value="">Default</option>
                        <option value="grok-3">Grok 3</option>
                        <option value="grok-3-mini">Grok Mini</option>
                      </select>
                    </div>
                  </div>
                </div>
              {/if}
            </div>
          </div>

          <!-- Active Run Banner -->
          {#if pipeline.isExecuting}
            <button
              type="button"
              on:click={() => { if (pipeline.currentRunId) detailRunId = pipeline.currentRunId; }}
              class="w-full card p-4 border-blue-200 bg-blue-50 hover:bg-blue-100 transition-colors text-left"
            >
              <div class="flex items-center gap-3">
                <svg class="animate-spin h-5 w-5 text-blue-600 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-semibold text-blue-900">
                    Researching{queueRunning ? ` ${queueRunning.race_id}` : ''}…
                  </p>
                  <p class="text-xs text-blue-700 mt-0.5">
                    {pipeline.progressMessage || 'Running'}
                    {#if queuePending > 0} · {queuePending} more in queue{/if}
                  </p>
                </div>
                <div class="text-right shrink-0">
                  <p class="text-lg font-bold text-blue-800">{pipeline.progress}%</p>
                </div>
              </div>
              <div class="mt-2 w-full bg-blue-200 rounded-full h-1.5">
                <div class="bg-blue-600 h-1.5 rounded-full transition-all duration-700" style="width: {pipeline.progress}%" />
              </div>
            </button>
          {/if}

          <!-- Server Queue -->
          {#if queueItems.length > 0}
            <div class="card p-3">
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-semibold text-gray-700">
                  Queue — {queueFinished}/{queueItems.length} done
                  {#if queuePending > 0}
                    <span class="ml-1 text-blue-600">({queuePending} pending)</span>
                  {/if}
                </span>
                {#if queueFinished > 0}
                  <button type="button" on:click={handleClearFinishedQueue} class="text-xs text-red-500 hover:text-red-700">
                    Clear done
                  </button>
                {/if}
              </div>
              <div class="space-y-1 max-h-48 overflow-y-auto">
                {#each queueItems as item (item.id)}
                  <div class="flex items-center gap-2 py-1">
                    <span class="text-xs font-mono text-gray-700 flex-1 truncate">{item.race_id}</span>
                    <span class="text-xs px-1.5 py-0.5 rounded flex-shrink-0 {
                      item.status === 'completed' ? 'bg-green-100 text-green-700' :
                      item.status === 'failed' ? 'bg-red-100 text-red-700' :
                      item.status === 'cancelled' ? 'bg-yellow-100 text-yellow-700' :
                      item.status === 'running' ? 'bg-blue-100 text-blue-700 animate-pulse' :
                      'bg-gray-100 text-gray-500'}">
                      {item.status}
                    </span>
                    {#if item.status === 'pending' || item.status === 'running'}
                      <button type="button" on:click={() => handleRemoveQueueItem(item)} class="flex-shrink-0 text-gray-400 hover:text-red-500" title="Cancel">
                        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                        </svg>
                      </button>
                    {:else if item.status === 'failed' && item.error}
                      <span class="text-xs text-red-400 truncate max-w-[7rem]" title={item.error}>{item.error}</span>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- Live Logs (compact) -->
          <LiveLogs
            {logs}
            logFilter={pipeline.logFilter}
            connected={websocket.connected}
            on:filter-change={handleLogFilterChange}
            on:clear-logs={handleClearLogs}
          />
        </div>

        <!-- Right: Run History -->
        <div class="space-y-4">
          <div class="card p-0">
            <div class="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
              <h3 class="text-sm font-semibold text-gray-900">All Runs</h3>
              <button
                on:click={debouncedRefresh}
                disabled={pipeline.isRefreshing}
                class="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400 flex items-center gap-1"
              >
                {#if pipeline.isRefreshing}
                  <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                {/if}
                Refresh
              </button>
            </div>

            {#if pipeline.runHistory.length === 0}
              <div class="p-8 text-center text-gray-400 text-sm">No runs yet — queue a race to get started</div>
            {:else}
              <div class="divide-y divide-gray-100 max-h-[calc(100vh-300px)] overflow-auto">
                {#each pipeline.runHistory as run (run.run_id)}
                  {@const rId = (run.payload?.race_id) ?? `run-${run.display_id}`}
                  {@const isActive = run.status === "running"}
                  <button
                    type="button"
                    class="w-full text-left px-4 py-3 transition-colors hover:bg-gray-50 {isActive ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''}"
                    on:click={() => (detailRunId = run.run_id)}
                  >
                    <div class="flex items-center gap-2">
                      {#if isActive}
                        <svg class="animate-spin h-3.5 w-3.5 text-blue-500 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                          <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                      {/if}
                      <span class="text-sm font-mono font-medium text-gray-900 flex-1 truncate">{rId}</span>
                      <span class="text-xs px-2 py-0.5 rounded-full shrink-0 {
                        run.status === 'completed' ? 'bg-green-100 text-green-700' :
                        run.status === 'failed' ? 'bg-red-100 text-red-700' :
                        run.status === 'running' ? 'bg-blue-100 text-blue-700' :
                        run.status === 'cancelled' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-gray-100 text-gray-600'}">
                        {run.status ?? "unknown"}
                      </span>
                    </div>
                    <div class="flex items-center gap-3 mt-1 text-xs text-gray-400">
                      <span>{new Date(run.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                      {#if run.duration_ms}
                        {@const dur = run.duration_ms}
                        <span>· {dur < 60000 ? `${Math.round(dur / 1000)}s` : `${Math.floor(dur / 60000)}m ${Math.round((dur % 60000) / 1000)}s`}</span>
                      {/if}
                      {#if run.options?.research_model}
                        <span class="ml-auto font-mono">{run.options.research_model}</span>
                      {/if}
                      {#if run.options?.enable_review}
                        <span title="AI review enabled" class="text-purple-400">✦</span>
                      {/if}
                    </div>
                    {#if run.error}
                      <p class="text-xs text-red-500 mt-1 truncate">{run.error}</p>
                    {/if}
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        </div>
      </div>
    {/if}
  {/if}
</div>

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
