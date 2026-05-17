/**
 * Run-progress polling store.
 *
 * Polls the races-api REST endpoints while a run is active instead of keeping
 * a persistent socket open.
 */

import { writable } from "svelte/store";

type PipelineEvent =
  | { type: "log"; level: string; message: string; timestamp?: string; run_id?: string }
  | { type: "run_started"; run_id: string; step: string }
  | { type: "run_progress"; run_id: string; progress?: number; message?: string }
  | { type: "run_completed"; run_id: string; result?: unknown; artifact_id?: string; duration_ms?: number }
  | { type: "run_failed"; run_id: string; error?: string }
  | { type: "run_status"; data: { run_id: string; status: string; [key: string]: unknown } }
  | { type: "buffered_logs"; data: { level: string; message: string; timestamp?: string; run_id?: string }[] };

interface PollingState {
  connected: boolean;
  reconnectAttempts: number;
  maxReconnectAttempts: number;
}

const initialState: PollingState = {
  connected: false,
  reconnectAttempts: 0,
  maxReconnectAttempts: 20,
};

export const runPollingStore = writable<PollingState>(initialState);

let apiBase = "";
let token = "";
const watchedRuns = new Map<string, {
  runPollTimer: ReturnType<typeof setInterval> | null;
  logPollTimer: ReturnType<typeof setInterval> | null;
  logsSeen: number;
}>();

let onMessage: ((event: PipelineEvent) => void) | null = null;
let onLog: ((level: string, msg: string, ts?: string, run_id?: string) => void) | null = null;

function authHeaders(): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function pollRunStatus(runId: string): Promise<void> {
  if (!apiBase) return;
  try {
    const res = await fetch(`${apiBase}/runs/${runId}`, {
      headers: authHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return;
    const run = await res.json();

    const status: string = run.status ?? "";
    const progress: number = run.progress ?? 0;
    const currentStep: string | undefined = run.current_step ?? undefined;
    const progressMessage: string | undefined = run.progress_message ?? undefined;

    onMessage?.({
      type: "run_progress",
      run_id: runId,
      progress,
      message: progressMessage ?? (currentStep ? `Running: ${currentStep}` : undefined),
    });

    onMessage?.({
      type: "run_status",
      data: { run_id: runId, status, progress, current_step: currentStep ?? null, ...run },
    });

    if (status === "completed") {
      stopPolling(runId);
      onMessage?.({ type: "run_completed", run_id: runId, result: run });
      if (watchedRuns.size === 0) runPollingStore.update((s) => ({ ...s, connected: false }));
    } else if (status === "failed") {
      stopPolling(runId);
      onMessage?.({ type: "run_failed", run_id: runId, error: run.error ?? "Run failed" });
      if (watchedRuns.size === 0) runPollingStore.update((s) => ({ ...s, connected: false }));
    } else if (status === "cancelled" || status === "continued") {
      stopPolling(runId);
      if (watchedRuns.size === 0) runPollingStore.update((s) => ({ ...s, connected: false }));
    }
  } catch {
    // Transient poll failures are expected during deploys and cold starts.
  }
}

async function pollLogs(runId: string): Promise<void> {
  if (!apiBase) return;
  const watched = watchedRuns.get(runId);
  if (!watched) return;
  try {
    const res = await fetch(`${apiBase}/runs/${runId}/logs?since=${watched.logsSeen}`, {
      headers: authHeaders(),
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return;
    const data = await res.json();
    const entries: { level?: string; message?: string; timestamp?: string; run_id?: string }[] =
      data.logs ?? [];
    if (entries.length === 0) return;

    watched.logsSeen += entries.length;

    for (const entry of entries) {
      onLog?.(entry.level ?? "info", entry.message ?? "", entry.timestamp, entry.run_id ?? runId);
    }
  } catch {
    // Transient poll failures are expected during deploys and cold starts.
  }
}

function stopPolling(runId?: string): void {
  const entries = runId
    ? Array.from(watchedRuns.entries()).filter(([id]) => id === runId)
    : Array.from(watchedRuns.entries());
  for (const [id, watched] of entries) {
    if (watched.runPollTimer) clearInterval(watched.runPollTimer);
    if (watched.logPollTimer) clearInterval(watched.logPollTimer);
    watchedRuns.delete(id);
  }
}

export const runPollingActions = {
  setHandlers(handlers: {
    onMessage?: (event: PipelineEvent) => void;
    onLog?: (level: string, msg: string, ts?: string, run_id?: string) => void;
  }) {
    onMessage = handlers.onMessage ?? null;
    onLog = handlers.onLog ?? null;
  },

  connect(nextApiBase: string, nextToken: string) {
    apiBase = nextApiBase;
    token = nextToken;
    runPollingStore.update((s) => ({ ...s, connected: true, reconnectAttempts: 0 }));
    onLog?.("info", "Live updates active (polling mode)");
  },

  disconnect() {
    stopPolling();
    runPollingStore.update((s) => ({ ...s, connected: false }));
  },

  send(_message: Record<string, unknown>) {},

  watchRun(runId: string) {
    if (watchedRuns.has(runId)) return;
    runPollingStore.update((s) => ({ ...s, connected: true }));
    watchedRuns.set(runId, { runPollTimer: null, logPollTimer: null, logsSeen: 0 });
    void pollRunStatus(runId);
    void pollLogs(runId);
    const watched = watchedRuns.get(runId);
    if (watched) {
      watched.runPollTimer = setInterval(() => void pollRunStatus(runId), 2000);
      watched.logPollTimer = setInterval(() => void pollLogs(runId), 3000);
    }
  },

  stopWatching(runId?: string) {
    stopPolling(runId);
    if (watchedRuns.size === 0) {
      runPollingStore.update((s) => ({ ...s, connected: false }));
    }
  },

  updateToken(nextToken: string) {
    token = nextToken;
  },
};
