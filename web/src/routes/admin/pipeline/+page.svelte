<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  const API_BASE = "http://127.0.0.1:8001"; // FastAPI local

  let steps: string[] = [];
  let selectedStep = "";
  let inputJson = '{\n  "race_id": "mo-senate-2024"\n}';
  let output: any = null;
  let artifacts: any[] = [];
  let loading = false;

  let skip_llm_apis = false;
  let skip_external_apis = false;
  let skip_network_calls = false;
  let skip_cloud_services = false;
  let save_artifact = true;

  // Enhanced features
  let ws: WebSocket | null = null;
  let connected = false;
  let logs: Array<{
    level: string;
    message: string;
    timestamp: string;
    run_id?: string;
  }> = [];
  let currentRunId: string | null = null;
  let isExecuting = false;
  let runStartTime: number | null = null;
  let elapsedTime = 0;
  let elapsedTimer: any = null;
  let runStatus = "idle";
  let progress = 0;
  let progressMessage = "";
  let logFilter = "all";
  let runHistory: any[] = [];
  let selectedRun: any = null;

  // Modal state
  let showModal = false;
  let modalTitle = "";
  let modalData: any = null;
  let modalLoading = false;

  async function loadSteps() {
    const res = await fetch(`${API_BASE}/steps`);
    const data = await res.json();
    steps = data.steps;
    if (!selectedStep && steps.length) selectedStep = steps[0];
  }

  async function loadArtifacts() {
    const res = await fetch(`${API_BASE}/artifacts`);
    const data = await res.json();
    artifacts = data.items;
  }

  async function loadRunHistory() {
    try {
      const res = await fetch(`${API_BASE}/runs`);
      const data = await res.json();
      runHistory = data.runs || [];
    } catch (error) {
      console.error("Failed to load run history:", error);
    }
  }

  function connectWebSocket() {
    const wsUrl = `ws://127.0.0.1:8001/ws/logs`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      connected = true;
      addLog("info", "Connected to pipeline server");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      } catch (e) {
        console.error("Failed to parse WebSocket message:", e);
      }
    };

    ws.onclose = () => {
      connected = false;
      addLog("warning", "Disconnected from pipeline server");

      // Attempt to reconnect after 3 seconds
      setTimeout(() => {
        if (!ws || ws.readyState === WebSocket.CLOSED) {
          connectWebSocket();
        }
      }, 3000);
    };

    ws.onerror = () => {
      connected = false;
      addLog("error", "WebSocket connection error");
    };
  }

  function handleWebSocketMessage(data: any) {
    switch (data.type) {
      case "log":
        addLog(data.level, data.message, data.timestamp, data.run_id);
        break;
      case "run_started":
        handleRunStarted(data);
        break;
      case "run_progress":
        handleRunProgress(data);
        break;
      case "run_completed":
        handleRunCompleted(data);
        break;
      case "run_failed":
        handleRunFailed(data);
        break;
    }
  }

  function addLog(
    level: string,
    message: string,
    timestamp?: string,
    run_id?: string
  ) {
    const logEntry = {
      level,
      message,
      timestamp: timestamp || new Date().toISOString(),
      run_id,
    };

    logs = [...logs.slice(-999), logEntry]; // Keep last 1000 entries
  }

  function handleRunStarted(data: any) {
    currentRunId = data.run_id;
    runStatus = "running";
    progress = 0;
    progressMessage = "Initializing...";
  }

  function handleRunProgress(data: any) {
    progress = data.progress || 0;
    progressMessage = data.message || "";
  }

  function handleRunCompleted(data: any) {
    runStatus = "completed";
    progress = 100;
    progressMessage = "Completed successfully";
    setExecutionState(false);

    if (data.result) {
      output = data.result;
    }

    loadRunHistory();
    loadArtifacts();
  }

  function handleRunFailed(data: any) {
    runStatus = "failed";
    setExecutionState(false);
    addLog("error", `Run failed: ${data.error || "Unknown error"}`);
    loadRunHistory();
  }

  async function runStep() {
    if (isExecuting) return;

    setExecutionState(true);
    output = null;

    try {
      const payload = JSON.parse(inputJson || "{}");
      const options: Record<string, any> = {
        skip_llm_apis: skip_llm_apis || undefined,
        skip_external_apis: skip_external_apis || undefined,
        skip_network_calls: skip_network_calls || undefined,
        skip_cloud_services: skip_cloud_services || undefined,
        save_artifact,
      };
      const body = { payload, options };

      const res = await fetch(`${API_BASE}/run/${selectedStep}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const result = await res.json();
      currentRunId = result.run_id;

      addLog(
        "info",
        `Started execution: ${selectedStep} (Run ID: ${currentRunId})`
      );
    } catch (err) {
      output = { error: String(err) };
      addLog("error", `Execution failed: ${err}`);
      setExecutionState(false);
    }
  }

  function setExecutionState(executing: boolean) {
    isExecuting = executing;

    if (executing) {
      runStartTime = Date.now();
      runStatus = "running";
      startElapsedTimer();
    } else {
      stopElapsedTimer();
      runStartTime = null;
    }
  }

  function startElapsedTimer() {
    elapsedTimer = setInterval(() => {
      if (runStartTime) {
        elapsedTime = Math.floor((Date.now() - runStartTime) / 1000);
      }
    }, 1000);
  }

  function stopElapsedTimer() {
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function stopExecution() {
    if (currentRunId && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "stop_run",
          run_id: currentRunId,
        })
      );
    }
    setExecutionState(false);
  }

  function useAsInput() {
    if (!output) return;
    try {
      const next = output.output ?? output;
      inputJson = JSON.stringify(next, null, 2);
    } catch {}
  }

  function clearLogs() {
    logs = [];
  }

  function copyOutput() {
    if (output) {
      navigator.clipboard.writeText(JSON.stringify(output, null, 2));
    }
  }

  function downloadOutput() {
    if (output) {
      const blob = new Blob([JSON.stringify(output, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pipeline-result-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  function formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  }

  function getStatusClass(status: string): string {
    switch (status) {
      case "running":
        return "bg-blue-100 text-blue-800 border-blue-200";
      case "completed":
        return "bg-green-100 text-green-800 border-green-200";
      case "failed":
        return "bg-red-100 text-red-800 border-red-200";
      default:
        return "bg-gray-100 text-gray-800 border-gray-200";
    }
  }

  function getLogClass(level: string): string {
    switch (level) {
      case "error":
        return "bg-red-50 text-red-800 border-l-red-500";
      case "warning":
        return "bg-yellow-50 text-yellow-800 border-l-yellow-500";
      case "info":
        return "bg-blue-50 text-blue-800 border-l-blue-500";
      case "debug":
        return "bg-gray-50 text-gray-600 border-l-gray-400";
      default:
        return "bg-gray-50 text-gray-600 border-l-gray-400";
    }
  }

  $: filteredLogs = logs.filter(
    (log) => logFilter === "all" || log.level === logFilter
  );

  onMount(async () => {
    await loadSteps();
    await loadArtifacts();
    await loadRunHistory();
    connectWebSocket();
  });

  onDestroy(() => {
    if (ws) {
      ws.close();
    }
    stopElapsedTimer();
  });

  function openModal(title: string, data: any) {
    modalTitle = title;
    modalData = data;
    showModal = true;
    modalLoading = false;
  }

  function closeModal() {
    showModal = false;
    modalData = null;
    modalTitle = "";
    modalLoading = false;
  }

  async function handleRunClick(run: any) {
    modalLoading = true;
    showModal = true;
    modalTitle = "Run Details";
    modalData = null;
    try {
      // Prefer run.id, fallback to run.run_id, fallback to run._id
      const runId = run.id || run.run_id || run._id;
      if (runId) {
        const res = await fetch(`${API_BASE}/run/${runId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        modalData = await res.json();
      } else {
        modalData = run;
      }
    } catch (e) {
      modalData = { error: String(e), ...run };
    }
    modalLoading = false;
  }

  async function handleArtifactClick(artifact: any) {
    modalLoading = true;
    showModal = true;
    modalTitle = "Artifact Details";
    modalData = null;
    try {
      // Prefer artifact.id, fallback to artifact.artifact_id, fallback to artifact._id
      const artifactId = artifact.id || artifact.artifact_id || artifact._id;
      if (artifactId) {
        const res = await fetch(`${API_BASE}/artifact/${artifactId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        modalData = await res.json();
      } else {
        modalData = artifact;
      }
    } catch (e) {
      modalData = { error: String(e), ...artifact };
    }
    modalLoading = false;
  }

  async function selectRun(run: any) {
    try {
      const runId = run.id || run.run_id || run._id;
      if (!runId) return;
      const res = await fetch(`${API_BASE}/run/${runId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const runData = await res.json();
      selectedRun = runData;

      let payload = runData.payload || {};
      if (runData.artifact_id) {
        try {
          const artRes = await fetch(`${API_BASE}/artifact/${runData.artifact_id}`);
          if (artRes.ok) {
            const artifact = await artRes.json();
            payload = { ...payload };
            switch (runData.step) {
              case 'step01a_metadata':
                payload.race_json = artifact;
                break;
              case 'step01b_discovery':
                payload.sources = artifact;
                break;
              case 'step01c_fetch':
                payload.raw_content = artifact;
                break;
              case 'step01d_extract':
                payload.content = artifact;
                break;
            }
          }
        } catch (e) {
          console.error('Failed to load artifact for run', e);
        }
      }

      inputJson = JSON.stringify(payload, null, 2);

      if (steps.length) {
        const idx = steps.indexOf(runData.step);
        if (idx >= 0 && idx < steps.length - 1) {
          selectedStep = steps[idx + 1];
        }
      }
    } catch (e) {
      console.error('Failed to select run:', e);
    }
  }

  function startNewRun() {
    selectedRun = null;
    inputJson = '{\n  "race_id": "mo-senate-2024"\n}';
    if (steps.length) {
      selectedStep = steps[0];
    }
  }
</script>

<!-- Connection Status Header -->
<div class="mb-6 card p-4">
  <div class="flex items-center justify-between">
    <div class="flex items-center space-x-4">
      <h2 class="text-lg font-semibold text-gray-900">
        Pipeline Client Dashboard
      </h2>
      <span class="text-sm text-gray-500"
        >Live Logging & Real-time Monitoring</span
      >
    </div>
    <div class="flex items-center space-x-2">
      <div
        class="w-3 h-3 rounded-full {connected ? 'bg-green-500' : 'bg-red-500'}"
      />
      <span class="text-sm text-gray-600"
        >{connected ? "Connected" : "Disconnected"}</span
      >
    </div>
  </div>
</div>

<div class="dashboard-grid">
  <!-- Left Panel: Controls & Progress -->
  <div class="space-y-6">
    <!-- Pipeline Execution Card -->
    <div class="card p-6">
      <h3 class="text-lg font-semibold text-gray-900 mb-4">
        Pipeline Execution
      </h3>

      <div class="mb-4 flex items-center justify-between text-sm text-gray-600">
        {#if selectedRun}
          <span>Using run {selectedRun.run_id}</span>
          <button on:click={startNewRun} class="text-blue-600 hover:text-blue-800">Start New Run</button>
        {:else}
          <span>Starting new run</span>
        {/if}
      </div>

      <div class="space-y-4">
        <!-- Step Selection -->
        <div>
          <label
            for="stepSelect"
            class="block text-sm font-medium text-gray-700 mb-2"
            >Pipeline Step</label
          >
          <div class="flex gap-2">
            <select
              bind:value={selectedStep}
              class="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {#each steps as step}
                <option value={step}>{step}</option>
              {/each}
            </select>
            <button on:click={loadSteps} class="btn-secondary">Refresh</button>
          </div>
        </div>

        <!-- Input JSON -->
        <div>
          <label
            for="inputJson"
            class="block text-sm font-medium text-gray-700 mb-2"
            >Input JSON</label
          >
          <textarea
            id="inputJson"
            bind:value={inputJson}
            class="json-editor"
            spellcheck="false"
            placeholder={'{"race_id": "example_race_2024"}'}
          />
        </div>

        <!-- Options -->
        <details class="options border border-gray-200 rounded-lg p-4">
          <summary class="cursor-pointer font-medium text-gray-700 mb-3"
            >Execution Options</summary
          >
          <div class="grid grid-cols-2 gap-3">
            <label class="flex items-center space-x-2">
              <input
                type="checkbox"
                bind:checked={skip_llm_apis}
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span class="text-sm text-gray-700">Skip LLM APIs</span>
            </label>
            <label class="flex items-center space-x-2">
              <input
                type="checkbox"
                bind:checked={skip_external_apis}
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span class="text-sm text-gray-700">Skip External APIs</span>
            </label>
            <label class="flex items-center space-x-2">
              <input
                type="checkbox"
                bind:checked={skip_network_calls}
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span class="text-sm text-gray-700">Skip Network Calls</span>
            </label>
            <label class="flex items-center space-x-2">
              <input
                type="checkbox"
                bind:checked={skip_cloud_services}
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span class="text-sm text-gray-700">Skip Cloud Services</span>
            </label>
            <label class="flex items-center space-x-2 col-span-2">
              <input
                type="checkbox"
                bind:checked={save_artifact}
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span class="text-sm text-gray-700">Save Artifact</span>
            </label>
          </div>
        </details>

        <!-- Action Buttons -->
        <div class="flex space-x-3">
          <button
            disabled={isExecuting}
            on:click={runStep}
            class="btn-primary flex-1 flex items-center justify-center"
          >
            {#if isExecuting}
              <svg
                class="animate-spin h-4 w-4 mr-2"
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
              Executing...
            {:else}
              Execute Pipeline
            {/if}
          </button>
          {#if isExecuting}
            <button on:click={stopExecution} class="btn-danger">Stop</button>
          {/if}
        </div>
      </div>
    </div>

    <!-- Current Run Progress -->
    {#if isExecuting || runStatus !== "idle"}
      <div class="card p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-gray-900">Current Run</h3>
          <span
            class="px-3 py-1 rounded-full text-xs font-medium border {getStatusClass(
              runStatus
            )}">{runStatus.charAt(0).toUpperCase() + runStatus.slice(1)}</span
          >
        </div>

        <!-- Progress Bar -->
        <div class="mb-4">
          <div class="flex justify-between text-sm text-gray-600 mb-2">
            <span>{progressMessage}</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div
              class="progress-bar bg-blue-600 h-2 rounded-full"
              style="width: {progress}%"
            />
          </div>
        </div>

        <!-- Run Metrics -->
        <div class="grid grid-cols-3 gap-4 text-sm">
          <div class="text-center">
            <div class="text-lg font-semibold text-blue-600">
              {formatDuration(elapsedTime)}
            </div>
            <div class="text-gray-600">Elapsed</div>
          </div>
          <div class="text-center">
            <div class="text-lg font-semibold text-green-600">
              {currentRunId ? "1" : "0"}
            </div>
            <div class="text-gray-600">Active</div>
          </div>
          <div class="text-center">
            <div class="text-lg font-semibold text-gray-600">
              {filteredLogs.filter((l) => l.level === "error").length}
            </div>
            <div class="text-gray-600">Errors</div>
          </div>
        </div>
      </div>
    {/if}

    <!-- Output Results -->
    {#if output}
      <div class="card p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-gray-900">Results</h3>
          <div class="flex space-x-2">
            <button on:click={copyOutput} class="btn-secondary text-sm"
              >Copy</button
            >
            <button on:click={downloadOutput} class="btn-secondary text-sm"
              >Download</button
            >
            <button on:click={useAsInput} class="btn-secondary text-sm"
              >Use as Input</button
            >
          </div>
        </div>
        <div class="output-display custom-scrollbar">
          {JSON.stringify(output, null, 2)}
        </div>
      </div>
    {/if}
  </div>

  <!-- Right Panel: Logs & History -->
  <div class="space-y-6">
    <!-- Live Logs -->
    <div class="card p-0 flex flex-col h-96">
      <div
        class="p-4 border-b border-gray-200 flex items-center justify-between"
      >
        <div class="flex items-center space-x-3">
          <h3 class="text-lg font-semibold text-gray-900">Live Logs</h3>
          <div class="flex items-center space-x-2">
            <div class="w-2 h-2 rounded-full bg-green-500 pulse-dot" />
            <span class="text-xs text-gray-500">Live</span>
          </div>
        </div>
        <div class="flex space-x-2">
          <select
            bind:value={logFilter}
            class="text-xs px-2 py-1 border border-gray-300 rounded"
          >
            <option value="all">All Levels</option>
            <option value="debug">Debug</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
          </select>
          <button
            on:click={clearLogs}
            class="text-xs px-2 py-1 text-gray-600 hover:text-gray-800"
            >Clear</button
          >
        </div>
      </div>
      <div class="flex-1 overflow-auto custom-scrollbar bg-gray-50">
        <div class="min-h-full">
          {#each filteredLogs as log}
            <div class="log-line {getLogClass(log.level)}">
              <span class="text-gray-500"
                >[{new Date(log.timestamp).toLocaleTimeString()}]</span
              >
              <span class="font-medium">[{log.level.toUpperCase()}]</span>
              {log.message}
            </div>
          {/each}
          {#if filteredLogs.length === 0}
            <div class="p-4 text-center text-gray-500 text-sm">No logs yet</div>
          {/if}
        </div>
      </div>
    </div>

    <!-- Run History -->
    <div class="card p-0">
      <div
        class="p-4 border-b border-gray-200 flex items-center justify-between"
      >
        <h3 class="text-lg font-semibold text-gray-900">Recent Runs</h3>
        <button
          on:click={loadRunHistory}
          class="text-sm text-blue-600 hover:text-blue-800">Refresh</button
        >
      </div>
      <div
        class="divide-y divide-gray-200 max-h-64 overflow-auto custom-scrollbar"
      >
        {#each runHistory.slice(0, 10) as run}
          <div
            class="p-4 hover:bg-gray-50 cursor-pointer"
            on:click={() => handleRunClick(run)}
          >
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-medium text-gray-900">
                  {run.step || "Unknown Step"}
                </div>
                <div class="text-xs text-gray-500">
                  {new Date(run.started_at).toLocaleString()}
                </div>
              </div>
              <span
                class="px-2 py-1 rounded-full text-xs {getStatusClass(
                  run.status
                )}"
              >
                {(run.status || "unknown").charAt(0).toUpperCase() +
                  (run.status || "unknown").slice(1)}
              </span>
            </div>
            <button class="text-xs text-blue-600 ml-2" on:click|stopPropagation={() => selectRun(run)}>
              Use
            </button>
          </div>
        {:else}
          <div class="p-4 text-center text-gray-500 text-sm">No runs yet</div>
        {/each}
      </div>
    </div>

    <!-- Artifacts -->
    <div class="card p-0">
      <div
        class="p-4 border-b border-gray-200 flex items-center justify-between"
      >
        <h3 class="text-lg font-semibold text-gray-900">Artifacts</h3>
        <button
          on:click={loadArtifacts}
          class="text-sm text-blue-600 hover:text-blue-800">Refresh</button
        >
      </div>
      <ul class="artifacts-list custom-scrollbar">
        {#each artifacts as artifact}
          <li
            class="cursor-pointer"
            on:click={() => handleArtifactClick(artifact)}
          >
            <span class="font-mono text-sm">{artifact.id}</span>
            <span class="text-xs text-gray-500"
              >{Math.round((artifact.size / 1024) * 10) / 10} KB</span
            >
          </li>
        {:else}
          <li class="text-center text-gray-500 text-sm py-4">
            No artifacts yet
          </li>
        {/each}
      </ul>
    </div>
  </div>
</div>

{#if showModal}
  <div class="modal-bg" on:click|self={closeModal}>
    <div class="modal-content">
      <button class="modal-close" on:click={closeModal} title="Close"
        >&times;</button
      >
      <div class="modal-title">{modalTitle}</div>
      {#if modalLoading}
        <div class="text-gray-500 text-center py-8">Loading...</div>
      {:else}
        <div class="modal-json">{JSON.stringify(modalData, null, 2)}</div>
      {/if}
    </div>
  </div>
{/if}

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

  .json-editor {
    width: 100%;
    min-height: 120px;
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 13px;
    border: 1px solid #d1d5db;
    border-radius: 0.5rem;
    padding: 0.75rem;
  }

  .json-editor:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .output-display {
    white-space: pre-wrap;
    background: #0f172a;
    color: #e2e8f0;
    padding: 1rem;
    border-radius: 0.5rem;
    max-height: 400px;
    overflow: auto;
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 12px;
  }

  .log-line {
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 11px;
    padding: 6px 12px;
    border-bottom: 1px solid #f1f5f9;
    line-height: 1.5;
    white-space: pre-wrap;
    border-left: 4px solid transparent;
  }

  .progress-bar {
    transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
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
    background: #f1f5f9;
    border-radius: 3px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
  }

  .options label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .artifacts-list {
    list-style: none;
    padding: 0;
    max-height: 200px;
    overflow-y: auto;
  }

  .artifacts-list li {
    font-size: 0.875rem;
    padding: 8px 12px;
    border-bottom: 1px solid #f1f5f9;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .artifacts-list li:hover {
    background-color: #f8fafc;
  }

  /* Modal styles */
  .modal-bg {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.35);
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .modal-content {
    background: #fff;
    border-radius: 0.75rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
    max-width: 600px;
    width: 90vw;
    max-height: 80vh;
    overflow-y: auto;
    padding: 2rem;
    position: relative;
  }
  .modal-close {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: none;
    border: none;
    font-size: 1.5rem;
    color: #64748b;
    cursor: pointer;
  }
  .modal-title {
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 1rem;
    color: #1e293b;
  }
  .modal-json {
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 13px;
    background: #f8fafc;
    color: #334155;
    border-radius: 0.5rem;
    padding: 1rem;
    white-space: pre-wrap;
    max-height: 50vh;
    overflow-y: auto;
  }
</style>
