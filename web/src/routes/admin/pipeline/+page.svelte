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
  import RunProgress from "$lib/components/RunProgress.svelte";
  import OutputResults from "$lib/components/OutputResults.svelte";
  import LiveLogs from "$lib/components/LiveLogs.svelte";
  import RunHistory from "$lib/components/RunHistory.svelte";
  import ArtifactsList from "$lib/components/ArtifactsList.svelte";
  import PipelineModal from "$lib/components/PipelineModal.svelte";

  // Utilities
  import { debounce, safeJsonStringify, downloadAsJson } from "$lib/utils/pipelineUtils";
  import { logger } from "$lib/utils/logger";
  import type { RunHistoryItem, Artifact } from "$lib/types";

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

  let apiService: PipelineApiService;
  let elapsedTimer: ReturnType<typeof setInterval> | null = null;
  let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;
  let queuePollTimer: ReturnType<typeof setInterval> | null = null;

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
        refreshPublishedRaces();
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
        refreshPublishedRaces();
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
      await refreshPublishedRaces();
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
    modalLoading = true;
    showModal = true;
    modalTitle = "Run Details";
    modalData = null;

    try {
      modalData = run.run_id ? await apiService.getRunDetails(run.run_id) : run;
    } catch (e) {
      modalData = { error: String(e), ...run };
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
  <title>Pipeline Dashboard - SmarterVote</title>
</svelte:head>

<div class="container mx-auto px-4 py-6 max-w-7xl">
  <!-- Header -->
  <div class="mt-2 mb-6 card p-4">
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-4">
        <h1 class="text-xl font-bold text-gray-900">Pipeline Dashboard</h1>
        <span class="text-sm text-gray-500">AI Agent Research</span>
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

  <div class="dashboard-grid">
    <!-- Left Panel -->
    <div class="space-y-6">
      <!-- Agent Controls -->
      <div class="card p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-1">Research a Race</h3>
        <p class="text-sm text-gray-500 mb-4">
          The AI agent will search the web, research candidates, and produce
          a structured profile with sources. Re-running an existing race updates it.
        </p>
        <div class="space-y-4">
          <div>
            <label for="raceId" class="block text-sm font-medium text-gray-700 mb-1">
              Race ID
            </label>
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
                disabled={!pipeline.raceId.trim()}
                title="Add to server queue (processes sequentially)"
                class="btn-primary px-4 py-2 text-sm rounded-lg whitespace-nowrap disabled:opacity-40 disabled:cursor-not-allowed"
              >
                + Queue
              </button>
            </div>
            <p class="mt-1 text-xs text-gray-400">
              Comma-separate multiple IDs · Press <kbd class="px-1 py-0.5 bg-gray-100 rounded text-xs">Enter</kbd> or + Queue to add all
            </p>
          </div>

          <!-- Server Queue -->
          {#if queueItems.length > 0}
            <div class="border border-gray-200 rounded-lg p-3">
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-medium text-gray-600">
                  Queue — {queueFinished}/{queueItems.length} done
                  {#if queuePending > 0}
                    <span class="ml-1 text-blue-600">({queuePending} pending)</span>
                  {/if}
                  {#if queueRunning}
                    <span class="ml-1 text-green-600 animate-pulse">● processing</span>
                  {/if}
                </span>
                {#if queueFinished > 0}
                  <button
                    type="button"
                    on:click={handleClearFinishedQueue}
                    class="text-xs text-red-500 hover:text-red-700"
                  >
                    Clear finished
                  </button>
                {/if}
              </div>
              <div class="space-y-1.5 max-h-48 overflow-y-auto">
                {#each queueItems as item (item.id)}
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-mono text-gray-700 flex-1 truncate">{item.race_id}</span>
                    <span class="text-xs px-1.5 py-0.5 rounded flex-shrink-0 {
                      item.status === 'completed' ? 'bg-green-100 text-green-700' :
                      item.status === 'failed' ? 'bg-red-100 text-red-700' :
                      item.status === 'cancelled' ? 'bg-yellow-100 text-yellow-700' :
                      item.status === 'running' ? 'bg-blue-100 text-blue-700 animate-pulse' :
                      'bg-gray-100 text-gray-500'
                    }">
                      {item.status}
                    </span>
                    {#if item.status === 'pending' || item.status === 'running'}
                      <button
                        type="button"
                        on:click={() => handleRemoveQueueItem(item)}
                        class="flex-shrink-0 text-gray-400 hover:text-red-500"
                        title="Remove / Cancel"
                      >
                        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                        </svg>
                      </button>
                    {:else if item.status === 'failed' && item.error}
                      <span class="text-xs text-red-400 truncate max-w-[8rem]" title={item.error}>{item.error}</span>
                    {:else}
                      <div class="w-3.5 h-3.5 flex-shrink-0" />
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- Mode Toggles -->
          <div class="flex flex-wrap gap-x-6 gap-y-2">
            <label class="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                bind:checked={cheapMode}
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span>Cheap Mode</span>
              <span class="text-xs text-gray-400">(faster, lower cost)</span>
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                bind:checked={enableReview}
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span>AI Review</span>
              <span class="text-xs text-gray-400">(Claude + Gemini + Grok)</span>
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
            <div class="space-y-3 border-t border-gray-200 pt-3">
              <p class="text-xs text-gray-500">Leave blank for defaults. Cheap mode selects lighter variants automatically.</p>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label for="researchModel" class="block text-xs font-medium text-gray-600">Research (OpenAI)</label>
                  <input id="researchModel" type="text" bind:value={researchModel}
                    placeholder={cheapMode ? "gpt-5.4-mini" : "gpt-5.4"}
                    class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs font-mono focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label for="claudeModel" class="block text-xs font-medium text-gray-600">Claude (Review)</label>
                  <input id="claudeModel" type="text" bind:value={claudeModel}
                    placeholder={cheapMode ? "claude-haiku-4-5-20251001" : "claude-sonnet-4-6"}
                    class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs font-mono focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label for="geminiModel" class="block text-xs font-medium text-gray-600">Gemini (Review)</label>
                  <input id="geminiModel" type="text" bind:value={geminiModel}
                    placeholder={cheapMode ? "gemini-3.0-flash" : "gemini-3.0-flash"}
                    class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs font-mono focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label for="grokModel" class="block text-xs font-medium text-gray-600">Grok (Review)</label>
                  <input id="grokModel" type="text" bind:value={grokModel}
                    placeholder={cheapMode ? "grok-3-mini" : "grok-3"}
                    class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs font-mono focus:outline-none focus:border-blue-500" />
                </div>
              </div>
            </div>
          {/if}

          {#if pipeline.isExecuting}
            <button
              on:click={handleStopExecution}
              class="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-red-600 text-white hover:bg-red-700 text-sm font-medium"
            >
              <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Researching{queueRunning ? ` ${queueRunning.race_id}` : ''}...
              {#if queuePending > 0}
                <span class="text-xs opacity-75">({queuePending} more queued)</span>
              {/if}
            </button>
          {/if}
        </div>
      </div>

      <!-- Existing Races -->
      <div class="card p-6">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">Published Races</h3>
            <p class="text-sm text-gray-500">
              {publishedRaces.length} race{publishedRaces.length !== 1 ? 's' : ''} published.
              Update, export, or delete.
            </p>
          </div>
          <button
            type="button"
            on:click={refreshPublishedRaces}
            disabled={racesLoading}
            class="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1 disabled:opacity-50"
            title="Refresh list"
          >
            <svg class="w-3.5 h-3.5 {racesLoading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>

        {#if publishedRaces.length === 0}
          <p class="text-sm text-gray-400 text-center py-4">No published races found.</p>
        {:else}
          <div class="space-y-2 max-h-[28rem] overflow-y-auto">
            {#each publishedRaces as race (race.id)}
              {@const updatedDate = race.updated_utc ? new Date(race.updated_utc) : null}
              {@const daysSinceUpdate = updatedDate ? Math.floor((Date.now() - updatedDate.getTime()) / 86400000) : null}
              <div class="flex items-start justify-between gap-3 p-3 rounded-lg border border-gray-200 hover:border-blue-200 hover:bg-blue-50/50 transition-colors">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-sm font-medium text-gray-900 font-mono">{race.id}</span>
                    {#if daysSinceUpdate !== null}
                      <span class="text-xs px-1.5 py-0.5 rounded {daysSinceUpdate > 90 ? 'bg-red-100 text-red-700' : daysSinceUpdate > 30 ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700'}">
                        {daysSinceUpdate === 0 ? 'today' : daysSinceUpdate === 1 ? '1d ago' : `${daysSinceUpdate}d ago`}
                      </span>
                    {/if}
                  </div>
                  {#if race.title}
                    <p class="text-xs text-gray-500 mt-0.5 truncate">{race.title}</p>
                  {/if}
                  <p class="text-xs text-gray-400 mt-0.5">
                    {race.candidates.map((c) => `${c.name}${c.party ? ` (${c.party})` : ""}`).join(" · ")}
                  </p>
                </div>
                <div class="flex items-center gap-1.5 flex-shrink-0">
                  <button
                    type="button"
                    on:click={() => handleExportRace(race)}
                    title="Download race JSON"
                    class="text-xs px-2 py-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    on:click={() => handleQueueRace(race)}
                    disabled={queueItems.some((q) => q.race_id === race.id && (q.status === 'pending' || q.status === 'running'))}
                    title="Queue re-research"
                    class="text-xs px-2.5 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {queueItems.some((q) => q.race_id === race.id && (q.status === 'pending' || q.status === 'running')) ? 'Queued' : 'Update'}
                  </button>
                  <button
                    type="button"
                    on:click={() => handleDeleteRace(race)}
                    disabled={pipeline.isExecuting}
                    title="Delete race"
                    class="text-xs px-2 py-1.5 rounded border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    ✕
                  </button>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Run Progress -->
      <RunProgress        isExecuting={pipeline.isExecuting}
        runStatus={pipeline.runStatus}
        progress={pipeline.progress}
        progressMessage={pipeline.progressMessage}
        elapsedTime={pipeline.elapsedTime}
        currentRunId={pipeline.currentRunId}
        errorCount={logs.filter((l) => l.level === "error").length}
        on:stop-execution={handleStopExecution}
      />

      <!-- Output Results -->
      <OutputResults
        output={pipeline.output}
        onAddLog={addLog}
      />
    </div>

    <!-- Right Panel -->
    <div class="space-y-6">
      <!-- Live Logs -->
      <LiveLogs
        {logs}
        logFilter={pipeline.logFilter}
        connected={websocket.connected}
        on:filter-change={handleLogFilterChange}
        on:clear-logs={handleClearLogs}
      />

      <!-- Run History -->
      <RunHistory
        runHistory={pipeline.runHistory}
        selectedRunId={pipeline.selectedRunId}
        isRefreshing={pipeline.isRefreshing}
        on:run-select={({ detail }) => handleRunDetails({ detail })}
        on:run-details={handleRunDetails}
        on:refresh={debouncedRefresh}
      />

      <!-- Artifacts -->
      <ArtifactsList
        artifacts={pipeline.artifacts}
        isRefreshing={pipeline.isRefreshing}
        on:artifact-click={handleArtifactClick}
        on:refresh={() =>
          apiService
            .loadArtifacts()
            .then((artifacts) => pipelineActions.setArtifacts(artifacts))}
      />
    </div>
  </div>
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
  .dashboard-grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: 1fr 400px;
  }

  @media (max-width: 1024px) {
    .dashboard-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
