<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import type {
    RunInfo,
    RunStatus,
    RunStep,
    Artifact,
    LogEntry,
    RunHistoryItem,
    RunOptions,
  } from "$lib/types";
  import RunStepList from "$lib/components/RunStepList.svelte";

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001"; // FastAPI local

  let steps: string[] = [];
  let inputJson = '{\n  "race_id": "mo-senate-2024"\n}';
  let output: unknown = null;
  let artifacts: Artifact[] = [];

  let skip_llm_apis = false;
  let skip_external_apis = false;
  let skip_network_calls = false;
  let skip_cloud_services = false;
  let save_artifact = true;

  // Enhanced features
  let ws: WebSocket | null = null;
  let connected = false;
  let logs: LogEntry[] = [];
  let currentRunId: string | null = null;
  let isExecuting = false;
  let runStartTime: number | null = null;
  let elapsedTime = 0;
  let elapsedTimer: ReturnType<typeof setInterval> | null = null;
  let runStatus: RunStatus | "idle" = "idle";
  let progress = 0;
  let progressMessage = "";
  let logFilter: "all" | "debug" | "info" | "warning" | "error" = "all";
  let currentStep: string | null = null;

  let runHistory: RunHistoryItem[] = [];
  let selectedRun: RunHistoryItem | null = null;
  let selectedRunId = "";
  let startStep = "";
  let endStep = "";

  // Modal state
  let showModal = false;
  let modalTitle = "";
  let modalData: unknown = null;
  let modalLoading = false;

  async function loadSteps() {
    const res = await fetch(`${API_BASE}/steps`);
    const data = await res.json();
    steps = data.steps || [];
    startStep = steps[0] || "";
    endStep = steps[steps.length - 1] || "";
  }

  async function loadArtifacts() {
    const res = await fetch(`${API_BASE}/artifacts`);
    const data = await res.json();
    artifacts = data.items || [];
  }

  interface RunsResponse {
    runs: RunInfo[];
  }

  async function loadRunHistory() {
    try {
      const res = await fetch(`${API_BASE}/runs`);
      const data: RunsResponse = await res.json();
      const runs = data.runs || [];
      runHistory = runs.map((r: RunInfo, idx: number) => {
        const lastStep = r.steps?.at(-1)?.name || (r as any).step;
        return {
          ...(r as any),
          run_id: (r as any).run_id || (r as any).id || (r as any)._id,
          display_id: runs.length - idx,
          updated_at: (r as any).completed_at || (r as any).started_at,
          last_step: lastStep,
        } as RunHistoryItem;
      });
    } catch (error) {
      console.error("Failed to load run history:", error);
    }
  }

  function connectWebSocket() {
    const wsUrl = API_BASE.replace(/^http/, "ws") + "/ws/logs";
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      connected = true;
      addLog("info", "Connected to pipeline server");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as PipelineEvent;
        handleWebSocketMessage(data);
      } catch (e) {
        console.error("Failed to parse WebSocket message:", e);
      }
    };

    ws.onclose = () => {
      connected = false;
      addLog("warning", "Disconnected from pipeline server");
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

  type PipelineEvent =
    | { type: "log"; level: string; message: string; timestamp?: string; run_id?: string }
    | { type: "run_started"; run_id: string; step: string }
    | { type: "run_progress"; progress?: number; message?: string }
    | { type: "run_completed"; result?: unknown; artifact_id?: string; duration_ms?: number }
    | { type: "run_failed"; error?: string };

  function handleWebSocketMessage(data: PipelineEvent) {
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

  function addLog(level: string, message: string, timestamp?: string, run_id?: string) {
    const logEntry: LogEntry = {
      level,
      message,
      timestamp: timestamp || new Date().toISOString(),
      run_id,
    };
    logs = [...logs.slice(-999), logEntry]; // Keep last 1000 entries
  }

  function handleRunStarted(data: { run_id: string; step: string }) {
    currentRunId = data.run_id;
    runStatus = "running";
    progress = 0;
    progressMessage = "Initializing...";
    currentStep = data.step;
    updateStepStatus(data.step, "running");
  }

  function handleRunProgress(data: { progress?: number; message?: string }) {
    progress = data.progress ?? progress;
    progressMessage = data.message ?? progressMessage;
  }

  function handleRunCompleted(data: {
    result?: unknown;
    artifact_id?: string;
    duration_ms?: number;
  }) {
    runStatus = "completed";
    progress = 100;
    progressMessage = "Completed successfully";
    setExecutionState(false);

    if (currentStep) {
      updateStepStatus(currentStep, "completed", {
        artifact_id: data.artifact_id,
        duration_ms: data.duration_ms,
      });
      currentStep = null;
    }

    if (data.result !== undefined) {
      output = data.result;
    }

    loadRunHistory();
    loadArtifacts();
  }

  function handleRunFailed(data: { error?: string }) {
    runStatus = "failed";
    setExecutionState(false);
    if (currentStep) {
      updateStepStatus(currentStep, "failed");
      currentStep = null;
    }
    addLog("error", `Run failed: ${data.error || "Unknown error"}`);
    loadRunHistory();
  }

  function updateStepStatus(name: string, status: RunStatus, extras: Partial<RunStep> = {}) {
    if (!selectedRun) return;
    selectedRun = {
      ...selectedRun,
      steps: selectedRun.steps.map((s) =>
        s.name === name ? { ...s, status, ...extras } : s
      ),
    };
  }

  async function executeStep(stepName: string) {
    const payload = JSON.parse(inputJson || "{}");
    const options: RunOptions = {
      skip_llm_apis: skip_llm_apis || undefined,
      skip_external_apis: skip_external_apis || undefined,
      skip_network_calls: skip_network_calls || undefined,
      skip_cloud_services: skip_cloud_services || undefined,
      save_artifact,
    };
    const body = { payload, options };

    const res = await fetch(`${API_BASE}/run/${stepName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }

    const result = await res.json();
    currentRunId = result.run_id;
    addLog("info", `Started execution: ${stepName}`);

    await loadRunHistory();
    await loadArtifacts();
    const runId = result.meta?.run_id || result.run_id;
    const run = runHistory.find((r) => r.run_id === runId);
    if (run) {
      await selectRun(run);
    }
    selectedRunId = runId;
  }

  async function runFromStep(stepName: string) {
    if (isExecuting) return;

    if (!ws || ws.readyState === WebSocket.CLOSED) {
      connectWebSocket();
    }

    setExecutionState(true);
    output = null;

    try {
      if (selectedRun) {
        currentRunId = selectedRun.run_id;
        const state = JSON.parse(inputJson || "{}");
        const startIdx = Math.max(0, steps.indexOf(stepName));
        const endIdx = Math.max(startIdx, steps.indexOf(endStep));
        const stepsToRun = steps.slice(startIdx, endIdx + 1);

        const res = await fetch(
          `${API_BASE}/runs/${selectedRun.run_id}/continue`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ steps: stepsToRun, state }),
          }
        );

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        const result = await res.json();
        output = result;
        inputJson = JSON.stringify(result.state ?? {}, null, 2);
        const last = result.runs?.[result.runs.length - 1];
        if (last) {
          selectedRunId = last.run_id;
        }
        await loadRunHistory();
        await loadArtifacts();
        if (selectedRunId) {
          const run = runHistory.find((r) => r.run_id === selectedRunId);
          if (run) {
            selectedRun = run;
          }
        }
      } else {
        const step = stepName || steps[0] || "step01a_metadata";
        await executeStep(step);
      }
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
      const next = (output as any)?.output ?? output;
      inputJson = JSON.stringify(next, null, 2);
    } catch {}
  }

  function clearLogs() {
    logs = [];
  }

  function copyOutput() {
    if (output !== null && output !== undefined) {
      navigator.clipboard.writeText(JSON.stringify(output, null, 2));
    }
  }

  function downloadOutput() {
    if (output !== null && output !== undefined) {
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

  function getStatusClass(status: RunStatus | string): string {
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

  function openModal(title: string, data: unknown) {
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

  async function handleRunClick(run: RunHistoryItem) {
    modalLoading = true;
    showModal = true;
    modalTitle = "Run Details";
    modalData = null;
    try {
      const runId = run.run_id;
      if (runId) {
        const res = await fetch(`${API_BASE}/run/${runId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const runData: RunInfo = await res.json();
        modalData = runData;
      } else {
        modalData = run;
      }
    } catch (e) {
      modalData = { error: String(e), ...run };
    }
    modalLoading = false;
  }

  async function handleArtifactClick(artifact: Artifact) {
    modalLoading = true;
    showModal = true;
    modalTitle = "Artifact Details";
    modalData = null;
    try {
      const artifactId = artifact.id || (artifact as any).artifact_id || (artifact as any)._id;
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

  async function selectRun(run: RunHistoryItem) {
    try {
      const runId = run.run_id;
      if (!runId) return;
      const res = await fetch(`${API_BASE}/run/${runId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const runData: RunInfo = await res.json();
      const stepsData: RunStep[] = runData.steps || [];
      const stepName = stepsData[stepsData.length - 1]?.name || "";

      selectedRun = {
        ...(runData as any),
        display_id: (run as any).display_id,
        updated_at: (runData as any).completed_at ?? (runData as any).started_at,
        step: stepName,
        steps: stepsData,
      } as RunHistoryItem;

      currentStep = stepsData.find((s) => s.status === "running")?.name || null;

      const lastIdx = Math.max(0, steps.indexOf(stepName));
      const nextIndex = Math.min(lastIdx + 1, Math.max(0, steps.length - 1));
      startStep = steps[nextIndex] || steps[0] || "";
      endStep = steps[steps.length - 1] || "";

      let payload: Record<string, unknown> = (runData as any).payload || {};
      if ((runData as any).artifact_id) {
        try {
          const artRes = await fetch(`${API_BASE}/artifact/${(runData as any).artifact_id}`);
          if (artRes.ok) {
            const artifact = await artRes.json();
            payload = { ...payload };
            switch (stepName) {
              case "step01a_metadata":
                (payload as any).race_json = artifact.output;
                break;
              case "step01b_discovery":
                (payload as any).sources = artifact.output;
                break;
              case "step01c_fetch":
                (payload as any).raw_content = artifact.output;
                break;
              case "step01d_extract":
                (payload as any).content = artifact.output;
                break;
            }
          }
        } catch (e) {
          console.error("Failed to load artifact for run", e);
        }
      }

      inputJson = JSON.stringify(payload, null, 2);
    } catch (e) {
      console.error("Failed to select run:", e);
    }
  }

  async function handleRunSelect(event: Event) {
    const runId = (event.target as HTMLSelectElement).value;
    selectedRunId = runId;
    const run = runHistory.find((r) => r.run_id === runId);
    if (run) {
      await selectRun(run);
    }
  }
</script>

<div class="mt-2 mb-6 card p-4">
  <div class="flex items-center justify-between">
    <div class="flex items-center space-x-4">
      <h2 class="text-lg font-semibold text-gray-900">
        Pipeline Client Dashboard
      </h2>
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

      <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700 mb-2">Run</label>
        <div class="flex items-center gap-4">
          <button
            class="btn-secondary"
            on:click={() => {
              selectedRun = null;
              selectedRunId = "";
              inputJson = '{\n  "race_id": "mo-senate-2024"\n}';
              startStep = steps[0] || "";
              endStep = steps[steps.length - 1] || "";
            }}
          >
            Start New Run
          </button>
          {#if runHistory.length}
            <select
              class="px-2 py-1 border border-gray-300 rounded"
              bind:value={selectedRunId}
              on:change={handleRunSelect}
            >
              <option value="" selected>Select run</option>
              {#each runHistory as run}
                <option value={run.run_id}>
                  Run {run.display_id} – {run.last_step || "Unknown Step"} –
                  {new Date(run.updated_at).toLocaleString()}
                </option>
              {/each}
            </select>
          {:else}
            <span class="text-sm text-gray-500">No runs yet</span>
          {/if}
        </div>
        {#if selectedRun}
          <p class="text-sm text-gray-600 mt-2">
            Continuing run {selectedRun.display_id}
          </p>
        {/if}
      </div>

      <div class="space-y-4">
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
            placeholder='{"race_id": "example_race_2024"}'
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

        {#if selectedRun}
          <RunStepList
            {API_BASE}
            {currentStep}
            steps={selectedRun.steps}
            runFromStep={runFromStep}
          />
        {/if}

        <!-- Action Buttons -->
        <div class="flex space-x-3">
          <button
            disabled={isExecuting}
            on:click={() => runFromStep(startStep)}
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
            )}"
            >{(runStatus as string).charAt(0).toUpperCase() + (runStatus as string).slice(1)}</span
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
    {#if output !== null}
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
      <div class="p-4 border-b border-gray-200 flex items-center justify-between">
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
      <div class="p-4 border-b border-gray-200 flex items-center justify-between">
        <h3 class="text-lg font-semibold text-gray-900">Recent Runs</h3>
        <button
          on:click={loadRunHistory}
          class="text-sm text-blue-600 hover:text-blue-800">Refresh</button
        >
      </div>
      <div class="divide-y divide-gray-200 max-h-64 overflow-auto custom-scrollbar">
        {#each runHistory.slice(0, 10) as run}
          <div
            class="p-4 hover:bg-gray-50 cursor-pointer"
            on:click={() => handleRunClick(run)}
          >
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-medium text-gray-900">
                  Run {run.display_id} – {run.last_step || "Unknown Step"}
                </div>
                <div class="text-xs text-gray-500">
                  {new Date(run.started_at).toLocaleString()}
                </div>
              </div>
              <span
                class="px-2 py-1 rounded-full text-xs {getStatusClass(run.status || 'unknown')}"
              >
                {(run.status || "unknown").charAt(0).toUpperCase() +
                  (run.status || "unknown").slice(1)}
              </span>
            </div>
          </div>
        {:else}
          <div class="p-4 text-center text-gray-500 text-sm">No runs yet</div>
        {/each}
      </div>
    </div>

    <!-- Artifacts -->
    <div class="card p-0">
      <div class="p-4 border-b border-gray-200 flex items-center justify-between">
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
            <span class="font-mono text-sm">{artifact.id || (artifact as any).artifact_id || (artifact as any)._id}</span>
            <span class="text-xs text-gray-500">
              {artifact.size ? `${(artifact.size / 1024).toFixed(1)} KB` : "—"}
            </span>
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
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .custom-scrollbar::-webkit-scrollbar { width: 6px; }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 3px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

  .options label { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }

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

  .artifacts-list li:hover { background-color: #f8fafc; }

  /* Modal */
  .modal-bg {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.35);
    z-index: 50; display: flex; align-items: center; justify-content: center;
  }
  .modal-content {
    background: #fff; border-radius: 0.75rem; box-shadow: 0 8px 32px rgba(0,0,0,0.18);
    max-width: 600px; width: 90vw; max-height: 80vh; overflow-y: auto; padding: 2rem; position: relative;
  }
  .modal-close {
    position: absolute; top: 1rem; right: 1rem; background: none; border: none; font-size: 1.5rem; color: #64748b; cursor: pointer;
  }
  .modal-title { font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; color: #1e293b; }
  .modal-json {
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 13px; background: #f8fafc; color: #334155; border-radius: 0.5rem; padding: 1rem; white-space: pre-wrap; max-height: 50vh; overflow-y: auto;
  }
</style>
