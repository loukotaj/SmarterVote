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
  import type { PublishedRaceSummary } from "$lib/services/pipelineApiService";

  // Components
  import RunProgress from "$lib/components/RunProgress.svelte";
  import OutputResults from "$lib/components/OutputResults.svelte";
  import LiveLogs from "$lib/components/LiveLogs.svelte";
  import RunHistory from "$lib/components/RunHistory.svelte";
  import ArtifactsList from "$lib/components/ArtifactsList.svelte";
  import PipelineModal from "$lib/components/PipelineModal.svelte";

  // Utilities
  import { debounce, safeJsonStringify } from "$lib/utils/pipelineUtils";
  import type { RunHistoryItem, Artifact } from "$lib/types";

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

  let apiService: PipelineApiService;
  let elapsedTimer: ReturnType<typeof setInterval> | null = null;
  let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;

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

  // Race queue
  type QueueStatus = "pending" | "running" | "completed" | "failed";
  type QueueItem = { id: string; status: QueueStatus };
  let raceQueue: Array<QueueItem> = [];
  let isQueueMode = false;

  function addToQueue() {
    const id = pipeline.raceId.trim();
    if (!id) return;
    if (raceQueue.some((r: QueueItem) => r.id === id)) {
      addLog("warning", `Race "${id}" is already in the queue`);
      return;
    }
    raceQueue = [...raceQueue, { id, status: "pending" as QueueStatus }];
    pipelineActions.setRaceId("");
  }

  function removeFromQueue(id: string) {
    raceQueue = raceQueue.filter((r: QueueItem) => r.id !== id);
  }

  function clearQueue() {
    raceQueue = raceQueue.filter((r: QueueItem) => r.status === "running");
  }

  async function runQueue() {
    if (pipeline.isExecuting) return;
    isQueueMode = true;
    await processNextQueueItem();
  }

  async function processNextQueueItem() {
    const next = raceQueue.find((r: QueueItem) => r.status === "pending");
    if (!next) {
      isQueueMode = false;
      addLog("info", "Queue complete — all races processed");
      return;
    }
    raceQueue = raceQueue.map((r: QueueItem) =>
      r.id === next.id ? { ...r, status: "running" as QueueStatus } : r
    );
    pipelineActions.setRaceId(next.id);
    await handleRunAgent();
  }

  $: pendingCount = raceQueue.filter((r: QueueItem) => r.status === "pending").length;
  $: completedCount = raceQueue.filter((r: QueueItem) => r.status === "completed").length;

  function handleRaceIdInput(e: Event) {
    pipelineActions.setRaceId((e.currentTarget as HTMLInputElement).value);
  }

  function handleRaceIdKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") addToQueue();
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

      addLog("info", "Pipeline dashboard initialized");
    } catch (error) {
      console.error("Failed to initialize pipeline dashboard:", error);
      addLog("error", `Initialization failed: ${error}`);
    }
  });

  onDestroy(() => {
    stopElapsedTimer();
    stopAutoRefresh();
    websocketActions.disconnect();
  });

  async function loadInitialData() {
    try {
      const [artifactsResult, historyResult, racesResult] = await Promise.allSettled([
        apiService.loadArtifacts(),
        apiService.loadRunHistory(),
        apiService.loadPublishedRaces(),
      ]);

      if (artifactsResult.status === "fulfilled") {
        pipelineActions.setArtifacts(artifactsResult.value);
      }

      if (historyResult.status === "fulfilled") {
        pipelineActions.setRunHistory(historyResult.value);
      }

      if (racesResult.status === "fulfilled") {
        publishedRaces = racesResult.value;
      }
    } catch (error) {
      console.error("Failed to load initial data:", error);
      addLog("error", "Failed to load initial data");
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
      console.error("Refresh failed:", error);
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
        if (isQueueMode) {
          raceQueue = raceQueue.map((r: QueueItem) =>
            r.status === "running" ? { ...r, status: "completed" as QueueStatus } : r
          );
          setTimeout(() => processNextQueueItem(), 800);
        }
        break;
      case "run_failed":
        pipelineActions.setRunStatus("failed");
        pipelineActions.setExecutionState(false);
        addLog("error", `Run failed: ${data.error || "Unknown error"}`);
        stopAutoRefresh();
        stopElapsedTimer();
        debouncedRefresh();
        if (isQueueMode) {
          raceQueue = raceQueue.map((r: QueueItem) =>
            r.status === "running" ? { ...r, status: "failed" as QueueStatus } : r
          );
          setTimeout(() => processNextQueueItem(), 800);
        }
        break;
    }
  }

  async function refreshPublishedRaces() {
    racesLoading = true;
    try {
      publishedRaces = await apiService.loadPublishedRaces();
    } catch (e) {
      console.error("Failed to refresh published races:", e);
    } finally {
      racesLoading = false;
    }
  }

  function handleUpdateRace(race: PublishedRaceSummary) {
    pipelineActions.setRaceId(race.id);
    // Scroll to top of left panel so the run button is visible
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Agent execution
  async function handleRunAgent() {
    const raceId = pipeline.raceId.trim();
    if (!raceId || pipeline.isExecuting) return;

    if (!websocket.connected) {
      websocketActions.connect(API_BASE, api.token);
    }

    pipelineActions.setExecutionState(true);
    pipelineActions.setOutput(null);
    pipelineActions.clearLogs();
    startElapsedTimer();

    try {
      addLog("info", `Starting agent research for: ${raceId}`);
      const opts: Record<string, any> = {
        save_artifact: true,
        enable_review: enableReview,
        cheap_mode: cheapMode,
      };
      if (researchModel) opts.research_model = researchModel;
      if (claudeModel) opts.claude_model = claudeModel;
      if (geminiModel) opts.gemini_model = geminiModel;
      if (grokModel) opts.grok_model = grokModel;
      const result = await apiService.runAgent(raceId, opts);
      pipelineActions.setCurrentRun(result.run_id, "agent");
      addLog("info", `Agent run started (run_id: ${result.run_id})`);
      startAutoRefresh();
    } catch (err) {
      console.error("Agent execution failed:", err);
      pipelineActions.setOutput({ error: String(err) });
      addLog("error", `Agent failed: ${err}`);
      pipelineActions.setExecutionState(false);
      stopElapsedTimer();
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
                placeholder="e.g. georgia-senate-2026"
                class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
              <button
                type="button"
                on:click={addToQueue}
                disabled={!pipeline.raceId.trim()}
                title="Add to queue (run multiple races sequentially)"
                class="px-3 py-2 text-sm border border-blue-300 text-blue-600 rounded-lg hover:bg-blue-50 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
              >
                + Queue
              </button>
            </div>
            <p class="mt-1 text-xs text-gray-400">
              Format: state-office-year · Press <kbd class="px-1 py-0.5 bg-gray-100 rounded text-xs">Enter</kbd> or click + Queue to batch
            </p>
          </div>

          <!-- Race Queue -->
          {#if raceQueue.length > 0}
            <div class="border border-gray-200 rounded-lg p-3">
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-medium text-gray-600">
                  Queue — {completedCount}/{raceQueue.length} done
                  {#if isQueueMode && pendingCount > 0}
                    <span class="ml-1 text-blue-600">({pendingCount} remaining)</span>
                  {/if}
                </span>
                <button
                  type="button"
                  on:click={clearQueue}
                  disabled={pipeline.isExecuting}
                  class="text-xs text-red-500 hover:text-red-700 disabled:opacity-40"
                >
                  Clear
                </button>
              </div>
              <div class="space-y-1.5 max-h-48 overflow-y-auto">
                {#each raceQueue as item (item.id)}
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-mono text-gray-700 flex-1 truncate">{item.id}</span>
                    <span class="text-xs px-1.5 py-0.5 rounded flex-shrink-0 {
                      item.status === 'completed' ? 'bg-green-100 text-green-700' :
                      item.status === 'failed' ? 'bg-red-100 text-red-700' :
                      item.status === 'running' ? 'bg-blue-100 text-blue-700 animate-pulse' :
                      'bg-gray-100 text-gray-500'
                    }">
                      {item.status}
                    </span>
                    {#if item.status === 'pending'}
                      <button
                        type="button"
                        on:click={() => removeFromQueue(item.id)}
                        class="flex-shrink-0 text-gray-400 hover:text-red-500"
                        title="Remove"
                      >
                        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                        </svg>
                      </button>
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
                    placeholder={cheapMode ? "gpt-4o-mini" : "gpt-4o"}
                    class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs font-mono focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label for="claudeModel" class="block text-xs font-medium text-gray-600">Claude (Review)</label>
                  <input id="claudeModel" type="text" bind:value={claudeModel}
                    placeholder={cheapMode ? "claude-haiku-4-20250514" : "claude-sonnet-4-20250514"}
                    class="w-full px-2 py-1.5 border border-gray-300 rounded text-xs font-mono focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label for="geminiModel" class="block text-xs font-medium text-gray-600">Gemini (Review)</label>
                  <input id="geminiModel" type="text" bind:value={geminiModel}
                    placeholder={cheapMode ? "gemini-2.0-flash-lite" : "gemini-2.0-flash"}
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

          <div class="flex gap-2">
            <button
              disabled={pipeline.isExecuting || !pipeline.raceId.trim()}
              on:click={handleRunAgent}
              class="btn-primary flex-1 flex items-center justify-center py-2.5"
            >
              {#if pipeline.isExecuting && !isQueueMode}
                <svg class="animate-spin h-4 w-4 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Researching...
              {:else}
                🔍 Research Race
              {/if}
            </button>
            {#if pendingCount > 0}
              <button
                disabled={pipeline.isExecuting}
                on:click={runQueue}
                class="flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium whitespace-nowrap"
              >
                {#if isQueueMode && pipeline.isExecuting}
                  <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  {completedCount}/{raceQueue.length}
                {:else}
                  ▶ Run {pendingCount}
                {/if}
              </button>
            {/if}
          </div>
        </div>
      </div>

      <!-- Existing Races -->
      <div class="card p-6">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">Existing Races</h3>
            <p class="text-sm text-gray-500">Click Update to re-run research on a published race.</p>
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
          <div class="space-y-2 max-h-72 overflow-y-auto">
            {#each publishedRaces as race (race.id)}
              {@const updatedDate = race.updated_utc ? new Date(race.updated_utc) : null}
              {@const daysSinceUpdate = updatedDate ? Math.floor((Date.now() - updatedDate.getTime()) / 86400000) : null}
              <div class="flex items-start justify-between gap-3 p-3 rounded-lg border border-gray-200 hover:border-blue-200 hover:bg-blue-50 transition-colors">
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
                <button
                  type="button"
                  on:click={() => handleUpdateRace(race)}
                  disabled={pipeline.isExecuting}
                  class="flex-shrink-0 text-xs px-2.5 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Update
                </button>
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
