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
  let enableReview = false;
  let cheapMode = true;
  let showAdvanced = false;
  let researchModel = "";
  let claudeModel = "";
  let geminiModel = "";
  let grokModel = "";

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
      const [artifactsResult, historyResult] = await Promise.allSettled([
        apiService.loadArtifacts(),
        apiService.loadRunHistory(),
      ]);

      if (artifactsResult.status === "fulfilled") {
        pipelineActions.setArtifacts(artifactsResult.value);
      }

      if (historyResult.status === "fulfilled") {
        pipelineActions.setRunHistory(historyResult.value);
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
        break;
      case "run_failed":
        pipelineActions.setRunStatus("failed");
        pipelineActions.setExecutionState(false);
        addLog("error", `Run failed: ${data.error || "Unknown error"}`);
        stopAutoRefresh();
        stopElapsedTimer();
        debouncedRefresh();
        break;
    }
  }

  // V2 Agent execution
  async function handleRunAgent() {
    const raceId = pipeline.v2RaceId.trim();
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
      const result = await apiService.runV2Agent(raceId, opts);
      pipelineActions.setCurrentRun(result.run_id, "v2_agent");
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
            <label for="v2RaceId" class="block text-sm font-medium text-gray-700 mb-1">
              Race ID
            </label>
            <input
              id="v2RaceId"
              type="text"
              value={pipeline.v2RaceId}
              on:input={(e) => pipelineActions.setV2RaceId(e.currentTarget.value)}
              placeholder="e.g. mo-senate-2024"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
            <p class="mt-1 text-xs text-gray-400">
              Format: state-office-year (e.g. tx-governor-2026, ca-house-12-2024)
            </p>
          </div>

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

          <button
            disabled={pipeline.isExecuting || !pipeline.v2RaceId.trim()}
            on:click={handleRunAgent}
            class="btn-primary w-full flex items-center justify-center py-2.5"
          >
            {#if pipeline.isExecuting}
              <svg class="animate-spin h-4 w-4 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Researching...
            {:else}
              🔍 Research Race
            {/if}
          </button>
        </div>
      </div>

      <!-- Run Progress -->
      <RunProgress
        isExecuting={pipeline.isExecuting}
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
