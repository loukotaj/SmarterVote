<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { getAuth0Client } from "$lib/auth";
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
  import type { Auth0Client } from "@auth0/auth0-spa-js";

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001"; // FastAPI local
  let auth0: Auth0Client;
  let token = "";

  /**
   * Fetch with authentication and smart timeout handling
   *
   * Timeout Strategy:
   * - Pipeline execution (/run/, /continue): NO TIMEOUT (can take hours)
   * - Metadata operations (steps, runs): 10-15 seconds
   * - Artifact loading: 20 seconds (can be large files)
   * - Default operations: 30 seconds
   *
   * @param url - The URL to fetch
   * @param options - Fetch options
   * @param timeoutMs - Override timeout in milliseconds, null for no timeout
   */
  async function fetchWithAuth(url: string, options: RequestInit = {}, timeoutMs?: number) {
    if (!token) {
      token = await auth0.getTokenSilently();
    }

    // Different timeout strategies based on operation type
    let defaultTimeout = 30000; // 30 seconds for most operations

    // Determine if this is a long-running operation that shouldn't timeout
    const isLongRunningOperation =
      url.includes('/run/') || // Pipeline execution
      url.includes('/continue') || // Pipeline continuation
      (options.method === 'POST' && url.includes('/run')); // Any run operation

    // Use provided timeout, or no timeout for long operations, or default
    const actualTimeout = timeoutMs !== undefined ? timeoutMs :
      (isLongRunningOperation ? null : defaultTimeout);

    const controller = new AbortController();
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    if (actualTimeout !== null) {
      timeoutId = setTimeout(() => controller.abort(), actualTimeout);
    }

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          ...(options.headers || {}),
          Authorization: `Bearer ${token}`,
        },
      });

      if (timeoutId) clearTimeout(timeoutId);
      return response;
    } catch (error) {
      if (timeoutId) clearTimeout(timeoutId);
      if (error instanceof Error && error.name === 'AbortError') {
        const timeoutText = actualTimeout ? `after ${actualTimeout / 1000} seconds` : 'due to abort signal';
        throw new Error(`Request timed out ${timeoutText}`);
      }
      throw error;
    }
  }

  let steps: string[] = [];
  let inputJson = '{\n  "race_id": "mo-senate-2024"\n}';
  let output: unknown = null;
  let artifacts: Artifact[] = [];

  let use_cloud_storage = false;

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

  // WebSocket reconnection management
  let wsReconnectAttempts = 0;
  const MAX_RECONNECT_ATTEMPTS = 5;
  let wsReconnectTimeout: ReturnType<typeof setTimeout> | null = null;

  let runHistory: RunHistoryItem[] = [];
  let selectedRun: RunHistoryItem | null = null;
  let selectedRunId = "";
  let startStep = "";
  let endStep = "";
  let executionMode: "single" | "range" = "single";

  // Auto-refresh and UI optimization
  let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;
  let lastRefreshTime = 0;
  const MIN_REFRESH_INTERVAL = 2000; // Minimum 2 seconds between refreshes
  let pendingRefresh = false;
  let isRefreshing = false;

  // Modal state
  let showModal = false;
  let modalTitle = "";
  let modalData: unknown = null;
  let modalLoading = false;

  async function loadSteps() {
    try {
      const res = await fetchWithAuth(`${API_BASE}/steps`, {}, 10000); // 10 second timeout for metadata
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();
      steps = data.steps || [];
      startStep = steps[0] || "";
      endStep = steps[steps.length - 1] || "";
    } catch (error) {
      console.error("Failed to load steps:", error);
      addLog("error", "Failed to load pipeline steps");
    }
  }

  async function loadArtifacts() {
    try {
      const res = await fetchWithAuth(`${API_BASE}/artifacts`, {}, 15000); // 15 second timeout for artifacts
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();
      artifacts = data.items || [];
    } catch (error) {
      console.error("Failed to load artifacts:", error);
      addLog("error", "Failed to load artifacts");
    }
  }

  interface RunsResponse {
    runs: RunInfo[];
  }

  async function loadRunHistory() {
    try {
      const res = await fetchWithAuth(`${API_BASE}/runs`, {}, 10000); // 10 second timeout for run history
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

  // Debounced refresh function to prevent excessive API calls
  const debouncedRefresh = (() => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    return async function() {
      if (pendingRefresh) return;

      const now = Date.now();
      const timeSinceLastRefresh = now - lastRefreshTime;

      if (timeSinceLastRefresh < MIN_REFRESH_INTERVAL) {
        // Wait for the minimum interval
        if (timeoutId) clearTimeout(timeoutId);
        timeoutId = setTimeout(debouncedRefresh, MIN_REFRESH_INTERVAL - timeSinceLastRefresh);
        return;
      }

      pendingRefresh = true;
      isRefreshing = true;
      lastRefreshTime = now;

      try {
        await Promise.allSettled([loadRunHistory(), loadArtifacts()]);

        // Update selected run if it exists
        if (selectedRun && selectedRunId) {
          const updatedRun = runHistory.find(r => r.run_id === selectedRunId);
          if (updatedRun) {
            selectedRun = updatedRun;
          }
        }
      } catch (error) {
        console.error("Debounced refresh failed:", error);
      } finally {
        pendingRefresh = false;
        isRefreshing = false;
      }
    };
  })();

  // Start auto-refresh for active runs
  function startAutoRefresh() {
    if (autoRefreshTimer) return; // Already running

    autoRefreshTimer = setInterval(async () => {
      // Only refresh if we have an active run or are currently executing
      if (isExecuting || (selectedRun && selectedRun.status === "running")) {
        await debouncedRefresh();
      }
    }, 5000); // Check every 5 seconds
  }

  // Stop auto-refresh
  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }

  function connectWebSocket() {
    // Clear any existing reconnect timeout
    if (wsReconnectTimeout) {
      clearTimeout(wsReconnectTimeout);
      wsReconnectTimeout = null;
    }

    // Don't reconnect if we've hit the limit
    if (wsReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      addLog("error", "Max WebSocket reconnection attempts reached. Please refresh the page.");
      return;
    }

    try {
      const wsUrl =
        API_BASE.replace(/^http/, "ws") + `/ws/logs?token=${encodeURIComponent(token)}`;
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        connected = true;
        wsReconnectAttempts = 0; // Reset attempts on successful connection
        addLog("info", "Connected to pipeline server");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as PipelineEvent;
          // Queue message for throttled processing to prevent UI blocking
          queueWebSocketMessage(data);
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
          addLog("error", "Failed to parse server message");
        }
      };

      ws.onclose = (event) => {
        connected = false;
        if (event.code === 1000) {
          // Normal closure, don't reconnect
          addLog("info", "WebSocket connection closed normally");
          return;
        }

        addLog("warning", "Disconnected from pipeline server");
        wsReconnectAttempts++;

        if (wsReconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          const delay = Math.min(1000 * Math.pow(2, wsReconnectAttempts), 10000); // Exponential backoff, max 10s
          addLog("info", `Attempting to reconnect in ${delay/1000}s... (${wsReconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);

          wsReconnectTimeout = setTimeout(() => {
            if (!ws || ws.readyState === WebSocket.CLOSED) {
              connectWebSocket();
            }
          }, delay);
        }
      };

      ws.onerror = (error) => {
        connected = false;
        console.error("WebSocket error:", error);
        addLog("error", "WebSocket connection error");
      };
    } catch (error) {
      console.error("Failed to create WebSocket:", error);
      addLog("error", "Failed to create WebSocket connection");
    }
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

    // Keep last 500 entries to prevent memory issues (reduced from 1000)
    // Use slice to prevent the array from growing indefinitely
    if (logs.length >= 500) {
      logs = [...logs.slice(-499), logEntry];
    } else {
      logs = [...logs, logEntry];
    }

    // Request DOM update on next frame to prevent blocking
    requestAnimationFrame(() => {
      // Trigger reactivity update if needed
      logs = logs;
    });
  }

  // Throttle WebSocket message processing to prevent UI blocking
  let wsMessageQueue: PipelineEvent[] = [];
  let wsProcessingTimer: ReturnType<typeof setTimeout> | null = null;

  function processMessageQueue() {
    if (wsMessageQueue.length === 0) return;

    // Process up to 5 messages at once to prevent blocking
    const messagesToProcess = wsMessageQueue.splice(0, 5);

    for (const message of messagesToProcess) {
      handleWebSocketMessage(message);
    }

    // If there are more messages, schedule next batch
    if (wsMessageQueue.length > 0) {
      wsProcessingTimer = setTimeout(processMessageQueue, 10);
    } else {
      wsProcessingTimer = null;
    }
  }

  function queueWebSocketMessage(message: PipelineEvent) {
    wsMessageQueue.push(message);

    // Start processing if not already running
    if (!wsProcessingTimer) {
      wsProcessingTimer = setTimeout(processMessageQueue, 10);
    }
  }

  function handleRunStarted(data: { run_id: string; step: string }) {
    currentRunId = data.run_id;
    runStatus = "running";
    progress = 0;
    progressMessage = "Initializing...";
    currentStep = data.step;
    updateStepStatus(data.step, "running");

    // Start auto-refresh when a run starts
    startAutoRefresh();
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

    // Stop auto-refresh and do a final refresh
    stopAutoRefresh();

    // Use debounced refresh to prevent overwhelming the UI
    debouncedRefresh().then(() => {
      addLog("info", "UI refreshed after successful completion");
    }).catch((error) => {
      console.error('Failed to refresh after completion:', error);
      addLog("warning", "Failed to refresh UI after completion");
    });
  }

  function handleRunFailed(data: { error?: string }) {
    runStatus = "failed";
    setExecutionState(false);
    if (currentStep) {
      updateStepStatus(currentStep, "failed");
      currentStep = null;
    }
    addLog("error", `Run failed: ${data.error || "Unknown error"}`);

    // Stop auto-refresh and do a final refresh
    stopAutoRefresh();

    // Use debounced refresh for consistent behavior
    debouncedRefresh().then(() => {
      addLog("info", "UI refreshed after failure");
    }).catch((error) => {
      console.error('Failed to refresh after failure:', error);
      addLog("warning", "Failed to refresh UI after failure");
    });
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
      skip_cloud_services: !use_cloud_storage || undefined,
      save_artifact: true,
    };
    const body = { payload, options };

    // No timeout for pipeline execution - it can take a very long time
    const res = await fetchWithAuth(`${API_BASE}/run/${stepName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }); // No timeout parameter = no timeout for long-running operations

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
        let state;

        try {
          state = JSON.parse(inputJson || "{}");
        } catch (parseError) {
          throw new Error(`Invalid JSON in input: ${parseError}`);
        }

        // Handle truncated artifacts - if we have an artifact reference, let the backend know
        if (state._truncated && state._artifact_id) {
          addLog("info", `Loading full artifact data for execution (artifact: ${state._artifact_id})`);
          // The backend should handle this automatically when it sees _artifact_id
        }

        const startIdx = Math.max(0, steps.indexOf(stepName));
        // Only run the single step, not all steps to the end
        const stepsToRun = [stepName];

        const res = await fetchWithAuth(
          `${API_BASE}/runs/${selectedRun.run_id}/continue`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ steps: stepsToRun, state }),
          }
        ); // No timeout for pipeline execution

        if (!res.ok) {
          const errorText = await res.text().catch(() => 'Unknown error');
          throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
        }

        const result = await res.json();
        output = result;

        try {
          inputJson = JSON.stringify(result.state ?? {}, null, 2);
        } catch (stringifyError) {
          console.warn("Result too large for JSON display:", stringifyError);
          inputJson = JSON.stringify({
            _note: "Result too large to display",
            _size: JSON.stringify(result.state ?? {}).length
          }, null, 2);
        }

        const last = result.runs?.[result.runs.length - 1];
        if (last) {
          selectedRunId = last.run_id;
        }

        // Use Promise.allSettled to prevent cascading failures
        const [historyResult, artifactsResult] = await Promise.allSettled([
          loadRunHistory(),
          loadArtifacts()
        ]);

        if (historyResult.status === 'rejected') {
          console.error('Failed to load run history:', historyResult.reason);
          addLog("warning", "Failed to refresh run history");
        }

        if (artifactsResult.status === 'rejected') {
          console.error('Failed to load artifacts:', artifactsResult.reason);
          addLog("warning", "Failed to refresh artifacts");
        }

        if (selectedRunId && historyResult.status === 'fulfilled') {
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
      console.error("Execution failed:", err);
      output = { error: String(err) };
      addLog("error", `Execution failed: ${err}`);
      setExecutionState(false);
    }
  }

  async function runStepsRange(startStepName: string, endStepName: string) {
    if (isExecuting) return;

    if (!ws || ws.readyState === WebSocket.CLOSED) {
      connectWebSocket();
    }

    setExecutionState(true);
    output = null;

    try {
      if (selectedRun) {
        currentRunId = selectedRun.run_id;
        let state;

        try {
          state = JSON.parse(inputJson || "{}");
        } catch (parseError) {
          throw new Error(`Invalid JSON in input: ${parseError}`);
        }

        const startIdx = Math.max(0, steps.indexOf(startStepName));
        const endIdx = Math.max(startIdx, steps.indexOf(endStepName));
        const stepsToRun = steps.slice(startIdx, endIdx + 1);

        const res = await fetchWithAuth(
          `${API_BASE}/runs/${selectedRun.run_id}/continue`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ steps: stepsToRun, state }),
          }
        ); // No timeout for pipeline execution

        if (!res.ok) {
          const errorText = await res.text().catch(() => 'Unknown error');
          throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
        }

        const result = await res.json();
        output = result;

        try {
          inputJson = JSON.stringify(result.state ?? {}, null, 2);
        } catch (stringifyError) {
          console.warn("Result too large for JSON display:", stringifyError);
          inputJson = JSON.stringify({
            _note: "Result too large to display",
            _size: JSON.stringify(result.state ?? {}).length
          }, null, 2);
        }

        const last = result.runs?.[result.runs.length - 1];
        if (last) {
          selectedRunId = last.run_id;
        }

        // Use Promise.allSettled to prevent cascading failures
        const [historyResult, artifactsResult] = await Promise.allSettled([
          loadRunHistory(),
          loadArtifacts()
        ]);

        if (historyResult.status === 'rejected') {
          console.error('Failed to load run history:', historyResult.reason);
          addLog("warning", "Failed to refresh run history");
        }

        if (artifactsResult.status === 'rejected') {
          console.error('Failed to load artifacts:', artifactsResult.reason);
          addLog("warning", "Failed to refresh artifacts");
        }

        if (selectedRunId && historyResult.status === 'fulfilled') {
          const run = runHistory.find((r) => r.run_id === selectedRunId);
          if (run) {
            selectedRun = run;
          }
        }
      } else {
        // For new runs, start with the first step and run up to end step
        const step = startStepName || steps[0] || "step01a_metadata";
        await executeStep(step);
      }
    } catch (err) {
      console.error("Execution failed:", err);
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
      startAutoRefresh(); // Start auto-refresh for execution
    } else {
      stopElapsedTimer();
      stopAutoRefresh(); // Stop auto-refresh when execution ends
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

    // Use a web worker or defer processing for large outputs
    requestIdleCallback(() => {
      try {
        const next = (output as any)?.output ?? output;
        const jsonString = JSON.stringify(next, null, 2);

        // Check if the JSON is too large (>100KB)
        if (jsonString.length > 100000) {
          addLog("warning", "Output too large for input field. Using summary.");
          inputJson = JSON.stringify({
            _note: "Output too large to display in input. Will be handled automatically.",
            _size: `${(jsonString.length / 1024).toFixed(1)}KB`
          }, null, 2);
        } else {
          inputJson = jsonString;
        }
      } catch (error) {
        console.error("Failed to convert output to input:", error);
        addLog("error", "Failed to convert output to input JSON");
      }
    }, { timeout: 5000 });
  }

  function clearLogs() {
    logs = [];
  }

  function copyOutput() {
    if (output !== null && output !== undefined) {
      try {
        const jsonString = JSON.stringify(output, null, 2);

        // Check size before copying (Chrome has ~5MB clipboard limit)
        if (jsonString.length > 5000000) { // 5MB limit
          addLog("warning", `Output too large to copy (${(jsonString.length / 1024 / 1024).toFixed(1)}MB). Use download instead.`);
          return;
        }

        navigator.clipboard.writeText(jsonString);
        addLog("info", "Output copied to clipboard");
      } catch (error) {
        console.error("Failed to copy output:", error);
        addLog("error", "Failed to copy output to clipboard");
      }
    }
  }

  function downloadOutput() {
    if (output !== null && output !== undefined) {
      try {
        const jsonString = JSON.stringify(output, null, 2);
        const blob = new Blob([jsonString], {
          type: "application/json",
        });

        // Log the file size for user awareness
        const sizeMB = (blob.size / 1024 / 1024).toFixed(1);
        addLog("info", `Downloading output (${sizeMB}MB)`);

        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `pipeline-result-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (error) {
        console.error("Failed to download output:", error);
        addLog("error", "Failed to create download file");
      }
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

  // Safe output display with size limits
  $: safeOutputDisplay = (() => {
    if (output === null || output === undefined) return "";

    try {
      // Quick size check first to avoid expensive stringify on huge objects
      if (typeof output === 'object' && output !== null) {
        // Rough heuristic: if object has many keys or deep nesting, it might be large
        const keys = Object.keys(output);
        if (keys.length > 1000) {
          return `[LARGE OBJECT DETECTED]\nObject has ${keys.length} top-level keys\nUse "Download" to get complete output\nType: ${typeof output}`;
        }
      }

      const jsonString = JSON.stringify(output, null, 2);
      const maxDisplaySize = 500000; // 500KB for display

      if (jsonString.length > maxDisplaySize) {
        const truncated = jsonString.substring(0, maxDisplaySize);
        const sizeMB = (jsonString.length / 1024 / 1024).toFixed(1);
        return `${truncated}\n\n... [TRUNCATED - Output too large for display]\n... Full size: ${sizeMB}MB\n... Use "Download" to get complete output`;
      }

      return jsonString;
    } catch (error) {
      console.error("Failed to stringify output for display:", error);

      // If stringify fails, try to provide useful info about the object
      if (typeof output === 'object' && output !== null) {
        const keys = Object.keys(output);
        return `[ERROR: Unable to display output]\nReason: ${error}\nType: ${typeof output}\nKeys: ${keys.length > 10 ? keys.slice(0, 10).join(', ') + '...' : keys.join(', ')}\nUse "Download" to save raw output`;
      }

      return `[ERROR: Unable to display output]\nReason: ${error}\nType: ${typeof output}\nUse "Download" to save raw output`;
    }
  })();

  // Safe modal data display with size limits
  $: safeModalDisplay = (() => {
    if (!modalData) return "";

    try {
      // Quick size check first for modal data
      if (typeof modalData === 'object' && modalData !== null) {
        const keys = Object.keys(modalData);
        if (keys.length > 500) { // Lower threshold for modals
          return `[LARGE OBJECT DETECTED]\nObject has ${keys.length} top-level keys\nToo large for modal display\nType: ${typeof modalData}`;
        }
      }

      const jsonString = JSON.stringify(modalData, null, 2);
      const maxModalSize = 200000; // 200KB for modal display

      if (jsonString.length > maxModalSize) {
        const truncated = jsonString.substring(0, maxModalSize);
        const sizeMB = (jsonString.length / 1024 / 1024).toFixed(1);
        return `${truncated}\n\n... [TRUNCATED - Content too large for modal]\n... Full size: ${sizeMB}MB\n... Use main output display or download for complete data`;
      }

      return jsonString;
    } catch (error) {
      console.error("Failed to stringify modal data:", error);

      // Provide helpful info for modal errors
      if (typeof modalData === 'object' && modalData !== null) {
        const keys = Object.keys(modalData);
        return `[ERROR: Unable to display modal content]\nReason: ${error}\nType: ${typeof modalData}\nKeys: ${keys.length > 5 ? keys.slice(0, 5).join(', ') + '...' : keys.join(', ')}`;
      }

      return `[ERROR: Unable to display modal content]\nReason: ${error}\nType: ${typeof modalData}`;
    }
  })();

  // Check if modal content is too large
  $: modalDataTooLarge = (() => {
    if (!modalData) return false;
    try {
      const jsonString = JSON.stringify(modalData, null, 2);
      return jsonString.length > 200000; // 200KB threshold for modal
    } catch {
      return true;
    }
  })();

  // Check if output is too large for safe operations
  $: outputTooLarge = (() => {
    if (output === null || output === undefined) return false;
    try {
      const jsonString = JSON.stringify(output, null, 2);
      return jsonString.length > 5000000; // 5MB threshold
    } catch {
      return true; // If it can't be stringified, consider it too large
    }
  })();

  onMount(async () => {
    try {
      auth0 = await getAuth0Client();
      token = await auth0.getTokenSilently();

      // Load data in parallel but handle failures gracefully
      const [stepsResult, artifactsResult, historyResult] = await Promise.allSettled([
        loadSteps(),
        loadArtifacts(),
        loadRunHistory()
      ]);

      // Log any initialization failures
      if (stepsResult.status === 'rejected') {
        console.error('Failed to load steps:', stepsResult.reason);
        addLog("error", "Failed to load pipeline steps during initialization");
      }

      if (artifactsResult.status === 'rejected') {
        console.error('Failed to load artifacts:', artifactsResult.reason);
        addLog("warning", "Failed to load artifacts during initialization");
      }

      if (historyResult.status === 'rejected') {
        console.error('Failed to load run history:', historyResult.reason);
        addLog("warning", "Failed to load run history during initialization");
      }

      // Always try to connect WebSocket, even if other loading failed
      connectWebSocket();

      addLog("info", "Pipeline dashboard initialized");
    } catch (error) {
      console.error('Failed to initialize pipeline dashboard:', error);
      addLog("error", `Initialization failed: ${error}`);
      // Continue anyway - some functionality might still work
    }
  });

  onDestroy(() => {
    // Clean up WebSocket
    if (ws) {
      ws.close(1000, "Component unmounting"); // Normal closure
    }

    // Clear reconnection timeout
    if (wsReconnectTimeout) {
      clearTimeout(wsReconnectTimeout);
    }

    // Clear timer
    stopElapsedTimer();

    // Clean up auto-refresh timer
    stopAutoRefresh();

    // Clear WebSocket message processing timer
    if (wsProcessingTimer) {
      clearTimeout(wsProcessingTimer);
      wsProcessingTimer = null;
    }
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

  async function handleRunListClick(run: RunHistoryItem) {
    // Select the run for execution
    selectedRunId = run.run_id;
    await selectRun(run);

    // Also show the modal for details
    await handleRunClick(run);
  }

  async function handleRunClick(run: RunHistoryItem) {
    modalLoading = true;
    showModal = true;
    modalTitle = "Run Details";
    modalData = null;
    try {
      const runId = run.run_id;
      if (runId) {
        const res = await fetchWithAuth(`${API_BASE}/run/${runId}`, {}, 15000); // 15 second timeout for run details
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
        const res = await fetchWithAuth(`${API_BASE}/artifact/${artifactId}`, {}, 20000); // 20 second timeout for artifacts (can be large)
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
      const res = await fetchWithAuth(`${API_BASE}/run/${runId}`, {}, 15000); // 15 second timeout for run selection
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
          const artRes = await fetchWithAuth(`${API_BASE}/artifact/${(runData as any).artifact_id}`, {}, 20000); // 20 second timeout for artifacts
          if (artRes.ok) {
            const artifact = await artRes.json();
            payload = { ...payload };
            switch (stepName) {
              case "step01a_metadata":
                // Extract the actual race_json from the artifact output
                (payload as any).race_json = artifact.output?.race_json || artifact.output;
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

      // Use requestIdleCallback for non-blocking JSON processing
      requestIdleCallback(() => {
        try {
          const jsonString = JSON.stringify(payload, null, 2);
          if (jsonString.length > 100000) { // 100KB limit
            inputJson = JSON.stringify({
              _note: "Payload too large to display in input editor",
              _size: `${(jsonString.length / 1024).toFixed(1)}KB`,
              _artifact_id: (runData as any).artifact_id,
              _step_name: stepName
            }, null, 2);
            addLog("info", `Large payload detected (${(jsonString.length / 1024).toFixed(1)}KB). Using summary in input editor.`);
          } else {
            inputJson = jsonString;
          }
        } catch (stringifyError) {
          console.error("Failed to stringify payload:", stringifyError);
          inputJson = JSON.stringify({
            _note: "Failed to serialize payload - too complex",
            _error: String(stringifyError),
            _artifact_id: (runData as any).artifact_id
          }, null, 2);
          addLog("warning", "Payload too complex to display, using reference");
        }
      }, { timeout: 3000 });

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

  async function handleSetStartStep(stepName: string) {
    startStep = stepName;

    // Update input JSON based on the selected step's prerequisites
    if (selectedRun && selectedRun.steps) {
      const stepIndex = selectedRun.steps.findIndex(s => s.name === stepName);
      if (stepIndex > 0) {
        // Find the previous step that has an artifact
        for (let i = stepIndex - 1; i >= 0; i--) {
          const prevStep = selectedRun.steps[i];
          if (prevStep.artifact_id) {
            try {
              const artRes = await fetchWithAuth(`${API_BASE}/artifact/${prevStep.artifact_id}`, {}, 20000); // 20 second timeout for artifacts
              if (artRes.ok) {
                const artifact = await artRes.json();
                let payload: Record<string, unknown> = {};

                // Check if the artifact output is too large
                let artifactString: string;
                try {
                  artifactString = JSON.stringify(artifact.output);
                } catch (stringifyError) {
                  console.warn("Artifact too complex to stringify:", stringifyError);
                  payload = {
                    _note: `Artifact too complex to serialize. Will be loaded automatically during execution.`,
                    _artifact_id: prevStep.artifact_id,
                    _step_name: prevStep.name,
                    _truncated: true,
                    _error: "Serialization failed"
                  };
                  inputJson = JSON.stringify(payload, null, 2);
                  addLog("warning", `Artifact for ${prevStep.name} too complex to display. Using reference.`);
                  break;
                }

                const maxSize = 50000; // 50KB limit for JSON editor

                if (artifactString.length > maxSize) {
                  // For large artifacts, create a summary or reference
                  payload = {
                    _note: `Large artifact detected (${(artifactString.length / 1024).toFixed(1)}KB). Artifact will be loaded automatically during execution.`,
                    _artifact_id: prevStep.artifact_id,
                    _step_name: prevStep.name,
                    _truncated: true
                  };

                  // Add a small sample for some step types
                  try {
                    switch (stepName) {
                      case "step01b_discovery":
                        if (artifact.output?.race_json) {
                          payload.race_json = artifact.output.race_json;
                        }
                        break;
                      case "step01c_fetch":
                        if (Array.isArray(artifact.output) && artifact.output.length > 0) {
                          payload.sources_sample = artifact.output.slice(0, 2); // First 2 sources
                          payload.total_sources = artifact.output.length;
                        }
                        break;
                      case "step01d_extract":
                        if (Array.isArray(artifact.output) && artifact.output.length > 0) {
                          payload.content_sample = artifact.output.slice(0, 1); // First content item
                          payload.total_items = artifact.output.length;
                        }
                        break;
                    }
                  } catch (sampleError) {
                    console.warn("Failed to create sample from artifact:", sampleError);
                  }
                } else {
                  // Set up the payload based on what this step needs (normal size)
                  try {
                    switch (stepName) {
                      case "step01b_discovery":
                        payload.race_json = artifact.output?.race_json || artifact.output;
                        break;
                      case "step01c_fetch":
                        payload.sources = artifact.output;
                        break;
                      case "step01d_extract":
                        payload.raw_content = artifact.output;
                        break;
                      case "step02a_analyze":
                        payload.content = artifact.output;
                        break;
                      default:
                        // For other steps, use the artifact output directly
                        payload = artifact.output || {};
                    }
                  } catch (payloadError) {
                    console.warn("Failed to set up payload:", payloadError);
                    payload = {
                      _note: "Failed to process artifact output",
                      _artifact_id: prevStep.artifact_id,
                      _step_name: prevStep.name,
                      _error: String(payloadError)
                    };
                  }
                }

                try {
                  inputJson = JSON.stringify(payload, null, 2);

                  // Add a log message if we truncated the data
                  if (artifactString.length > maxSize) {
                    addLog("info", `Large artifact detected for ${prevStep.name}. Input JSON shows summary only. Full data will be loaded during execution.`);
                  }
                } catch (finalStringifyError) {
                  console.error("Failed to stringify final payload:", finalStringifyError);
                  inputJson = JSON.stringify({
                    _note: "Failed to serialize payload",
                    _artifact_id: prevStep.artifact_id,
                    _error: String(finalStringifyError)
                  }, null, 2);
                  addLog("error", "Failed to serialize payload for input editor");
                }

                break;
              }
            } catch (e) {
              console.error("Failed to load artifact for step setup", e);
              addLog("error", `Failed to load artifact for step setup: ${e}`);
              // Continue to try other steps or fall back
            }
          }
        }
      } else {
        // If it's the first step, use the original payload
        try {
          const originalPayload = (selectedRun as any).payload || {};
          inputJson = JSON.stringify(originalPayload, null, 2);
        } catch (originalError) {
          console.error("Failed to serialize original payload:", originalError);
          inputJson = JSON.stringify({
            _note: "Failed to serialize original payload",
            _error: String(originalError)
          }, null, 2);
          addLog("error", "Failed to serialize original payload");
        }
      }
    }
  }
</script>

<div class="container mx-auto px-4 py-6 max-w-7xl">
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
      {#if isRefreshing}
        <div class="flex items-center space-x-1">
          <svg class="animate-spin h-3 w-3 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span class="text-xs text-blue-600">Refreshing...</span>
        </div>
      {/if}
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
        <div class="block text-sm font-medium text-gray-700 mb-2">Run Selection</div>
        <div class="space-y-3">
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
                class="px-3 py-2 border border-gray-300 rounded-md bg-white text-sm min-w-0 flex-1"
                bind:value={selectedRunId}
                on:change={handleRunSelect}
              >
                <option value="" selected>Select existing run...</option>
                {#each runHistory as run}
                  <option value={run.run_id}>
                    Run {run.display_id} · {run.last_step || "Unknown Step"} ·
                    {new Date(run.updated_at).toLocaleDateString()} {new Date(run.updated_at).toLocaleTimeString()}
                  </option>
                {/each}
              </select>
            {:else}
              <span class="text-sm text-gray-500 italic">No previous runs available</span>
            {/if}
          </div>
          {#if selectedRun}
            <div class="bg-blue-50 border border-blue-200 rounded-md p-3">
              <div class="flex items-center justify-between">
                <div>
                  <p class="text-sm font-medium text-blue-900">
                    Continuing Run {selectedRun.display_id}
                  </p>
                  <p class="text-xs text-blue-700">
                    Last step: <span class="font-mono">{selectedRun.last_step || "Unknown"}</span>
                    {#if selectedRun.status}
                      · Status: <span class="capitalize">{selectedRun.status}</span>
                    {/if}
                  </p>
                </div>
                <span class="px-2 py-1 rounded-full text-xs font-medium {getStatusClass(selectedRun.status || 'unknown')}">
                  {(selectedRun.status || "unknown").charAt(0).toUpperCase() + (selectedRun.status || "unknown").slice(1)}
                </span>
              </div>
            </div>
          {:else}
            <div class="bg-green-50 border border-green-200 rounded-md p-3">
              <p class="text-sm font-medium text-green-900">Ready to start new run</p>
              <p class="text-xs text-green-700">A fresh pipeline execution will be initiated</p>
            </div>
          {/if}
        </div>
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
            placeholder="{`{\"race_id\": \"example_race_2024\"}`}"
          />
        </div>

        <!-- Options -->
        <details class="options border border-gray-200 rounded-lg p-4">
          <summary class="cursor-pointer font-medium text-gray-700 mb-3"
            >Storage Options</summary
          >
          <div class="space-y-3">
            <label class="flex items-center justify-between">
              <span class="text-sm text-gray-700">Storage Location</span>
              <div class="flex items-center space-x-2">
                <span class="text-xs text-gray-500">Local</span>
                <input
                  type="checkbox"
                  bind:checked={use_cloud_storage}
                  class="toggle-switch"
                />
                <span class="text-xs text-gray-500">Cloud</span>
              </div>
            </label>
            <p class="text-xs text-gray-500">
              {#if use_cloud_storage}
                Artifacts will be stored in cloud services (GCS, etc.)
              {:else}
                Artifacts will be stored locally on the filesystem
              {/if}
            </p>
          </div>
        </details>

        <!-- Execution Mode Options -->
        <details class="options border border-gray-200 rounded-lg p-4">
          <summary class="cursor-pointer font-medium text-gray-700 mb-3"
            >Execution Mode</summary
          >
          <div class="space-y-3">
            <div class="space-y-2">
              <label class="flex items-center">
                <input type="radio" bind:group={executionMode} value="single" class="mr-2" />
                <span class="text-sm text-gray-700">Run Single Step</span>
              </label>
              <label class="flex items-center">
                <input type="radio" bind:group={executionMode} value="range" class="mr-2" />
                <span class="text-sm text-gray-700">Run Step Range</span>
              </label>
            </div>
            <div class="text-xs text-gray-500">
              <p><strong>Single Step:</strong> Executes only the selected step and stops for user approval.</p>
              <p><strong>Step Range:</strong> Executes from start step to end step continuously.</p>
            </div>
          </div>
        </details>

        {#if selectedRun}
          <div class="mb-4">
            <h4 class="text-md font-semibold text-gray-900 mb-3 flex items-center">
              Pipeline Steps
              {#if currentStep}
                <span class="ml-2 px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                  Currently at: {currentStep}
                </span>
              {/if}
            </h4>
            <RunStepList
              {API_BASE}
              {currentStep}
              steps={selectedRun.steps}
              setStartStep={handleSetStartStep}
            />
          </div>
        {/if}

        <!-- Action Buttons -->
        <div class="flex space-x-3">
          <button
            disabled={isExecuting}
            on:click={() => executionMode === "single" ? runFromStep(startStep) : runStepsRange(startStep, endStep)}
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
            {:else if executionMode === "single"}
              Execute Step {startStep}
            {:else}
              Execute Steps {startStep} → {endStep}
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
            class="px-3 py-1 rounded-full text-xs font-medium border {getStatusClass(runStatus)}"
          >{runStatus.charAt(0).toUpperCase() + runStatus.slice(1)}</span>
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
            <button
              on:click={copyOutput}
              class="btn-secondary text-sm"
              disabled={outputTooLarge}
              title={outputTooLarge ? "Output too large to copy safely" : "Copy to clipboard"}
            >
              Copy
            </button>
            <button on:click={downloadOutput} class="btn-secondary text-sm"
              >Download</button
            >
            <button on:click={useAsInput} class="btn-secondary text-sm"
              >Use as Input</button
            >
          </div>
        </div>

        <!-- Warning for large outputs -->
        {#if outputTooLarge}
          <div class="mb-4 bg-yellow-50 border border-yellow-200 rounded-md p-3">
            <div class="flex items-start">
              <svg class="w-5 h-5 text-yellow-600 mt-0.5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
              </svg>
              <div>
                <h4 class="text-sm font-medium text-yellow-800">Large Output Detected</h4>
                <p class="text-sm text-yellow-700 mt-1">
                  This output is very large and has been truncated for display.
                  Use the "Download" button to get the complete result.
                </p>
              </div>
            </div>
          </div>
        {/if}

        <div class="output-display custom-scrollbar">
          {safeOutputDisplay}
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
          on:click={debouncedRefresh}
          disabled={isRefreshing}
          class="text-sm text-blue-600 hover:text-blue-800 disabled:text-gray-400 flex items-center space-x-1"
        >
          {#if isRefreshing}
            <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          {/if}
          <span>Refresh</span>
        </button>
      </div>
      <div class="divide-y divide-gray-200 max-h-64 overflow-auto custom-scrollbar">
        {#each runHistory.slice(0, 10) as run}
          <button
            type="button"
            class="w-full text-left p-4 transition-colors duration-200 {selectedRun && selectedRun.run_id === run.run_id
              ? 'bg-blue-50 border-l-4 border-l-blue-500'
              : 'hover:bg-gray-50'}"
            on:click={async () => {
              selectedRunId = run.run_id;
              await selectRun(run);
            }}
          >
            <div class="flex items-center justify-between">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <div class="text-sm font-medium text-gray-900">
                    Run {run.display_id}
                  </div>
                  {#if selectedRun && selectedRun.run_id === run.run_id}
                    <div class="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0" title="Currently selected"></div>
                  {/if}
                </div>
                <div class="text-xs text-gray-600 truncate">
                  {run.last_step || "Unknown Step"}
                </div>
                <div class="text-xs text-gray-500">
                  {new Date(run.started_at).toLocaleString()}
                </div>
              </div>
              <div class="flex items-center gap-2">
                <span
                  class="px-2 py-1 rounded-full text-xs font-medium flex-shrink-0 {getStatusClass(run.status || 'unknown')}"
                >
                  {(run.status || "unknown").charAt(0).toUpperCase() +
                    (run.status || "unknown").slice(1)}
                </span>
                <button
                  type="button"
                  class="px-2 py-1 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
                  on:click|stopPropagation={() => handleRunClick(run)}
                  title="View run details"
                >
                  Details
                </button>
              </div>
            </div>
          </button>
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
          disabled={isRefreshing}
          class="text-sm text-blue-600 hover:text-blue-800 disabled:text-gray-400 flex items-center space-x-1"
        >
          {#if isRefreshing}
            <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          {/if}
          <span>Refresh</span>
        </button>
      </div>
      <ul class="artifacts-list custom-scrollbar">
        {#each artifacts as artifact}
          <li>
            <button
              type="button"
              class="cursor-pointer w-full flex justify-between items-center px-0 py-0 bg-transparent border-none text-inherit"
              on:click={() => handleArtifactClick(artifact)}
            >
              <span class="font-mono text-sm">{artifact.id}</span>
              <span class="text-xs text-gray-500">
                {artifact.size ? `${(artifact.size / 1024).toFixed(1)} KB` : "—"}
              </span>
            </button>
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
</div>

{#if showModal}
  <div class="modal-bg" role="dialog" tabindex="-1">
    <div class="modal-backdrop" role="button" tabindex="0" on:click={closeModal} on:keydown={(e) => e.key === 'Escape' && closeModal()}></div>
    <div class="modal-content">
      <button class="modal-close" on:click={closeModal} title="Close"
        >&times;</button
      >
      <div class="modal-title">{modalTitle}</div>
      {#if modalLoading}
        <div class="text-gray-500 text-center py-8">Loading...</div>
      {:else}
        <!-- Warning for large modal content -->
        {#if modalDataTooLarge}
          <div class="mb-4 bg-yellow-50 border border-yellow-200 rounded-md p-3">
            <div class="flex items-start">
              <svg class="w-4 h-4 text-yellow-600 mt-0.5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
              </svg>
              <div>
                <h4 class="text-xs font-medium text-yellow-800">Large Content</h4>
                <p class="text-xs text-yellow-700 mt-1">Content has been truncated for display.</p>
              </div>
            </div>
          </div>
        {/if}
        <div class="modal-json">{safeModalDisplay}</div>
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
    word-wrap: break-word;
    word-break: break-word;
    background: #0f172a;
    color: #e2e8f0;
    padding: 1rem;
    border-radius: 0.5rem;
    max-height: 400px;
    overflow: auto;
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 12px;
    line-height: 1.4;
    /* Prevent horizontal scrolling issues */
    overflow-x: auto;
    overflow-y: auto;
    /* Ensure container doesn't grow beyond bounds */
    max-width: 100%;
    min-height: 100px;
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

  /* Toggle Switch */
  .toggle-switch {
    appearance: none;
    width: 44px;
    height: 24px;
    background: #cbd5e1;
    border-radius: 12px;
    position: relative;
    cursor: pointer;
    transition: background-color 0.2s;
  }

  .toggle-switch:checked {
    background: #3b82f6;
  }

  .toggle-switch::before {
    content: '';
    position: absolute;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: white;
    top: 2px;
    left: 2px;
    transition: transform 0.2s;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  }

  .toggle-switch:checked::before {
    transform: translateX(20px);
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

  .artifacts-list li:hover { background-color: #f8fafc; }

  /* Modal */
  .modal-bg {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.35);
    z-index: 50; display: flex; align-items: center; justify-content: center;
  }
  .modal-backdrop {
    position: absolute; inset: 0; cursor: pointer;
  }
  .modal-content {
    background: #fff; border-radius: 0.75rem; box-shadow: 0 8px 32px rgba(0,0,0,0.18);
    max-width: 600px; width: 90vw; max-height: 80vh; overflow-y: auto; padding: 2rem; position: relative; z-index: 1;
  }
  .modal-close {
    position: absolute; top: 1rem; right: 1rem; background: none; border: none; font-size: 1.5rem; color: #64748b; cursor: pointer;
  }
  .modal-title { font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; color: #1e293b; }
  .modal-json {
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 13px;
    background: #f8fafc;
    color: #334155;
    border-radius: 0.5rem;
    padding: 1rem;
    white-space: pre-wrap;
    word-wrap: break-word;
    word-break: break-word;
    max-height: 50vh;
    overflow-y: auto;
    overflow-x: auto;
    line-height: 1.4;
    /* Prevent modal from growing beyond viewport */
    max-width: 100%;
    /* Ensure scrollbars are always visible when needed */
    scrollbar-width: thin;
  }
</style>
