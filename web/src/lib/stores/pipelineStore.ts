/**
 * Pipeline execution state management store
 */
import { writable, derived } from "svelte/store";
import type {
  RunStatus,
  RunStep,
  Artifact,
  LogEntry,
  RunHistoryItem,
} from "$lib/types";

interface PipelineState {
  // Agent configuration
  raceId: string;

  // Current execution state
  isExecuting: boolean;
  currentRunId: string | null;
  runStatus: RunStatus | "idle";
  progress: number;
  progressMessage: string;
  currentStep: string | null;
  runStartTime: number | null;
  elapsedTime: number;

  // Data
  output: unknown;
  artifacts: Artifact[];
  logs: LogEntry[];
  runHistory: RunHistoryItem[];
  selectedRun: RunHistoryItem | null;
  selectedRunId: string;

  // UI state
  logFilter: "all" | "debug" | "info" | "warning" | "error";
  isRefreshing: boolean;
  lastRefreshTime: number;
}

const initialState: PipelineState = {
  raceId: "georgia-senate-2026",

  isExecuting: false,
  currentRunId: null,
  runStatus: "idle",
  progress: 0,
  progressMessage: "",
  currentStep: null,
  runStartTime: null,
  elapsedTime: 0,

  output: null,
  artifacts: [],
  logs: [],
  runHistory: [],
  selectedRun: null,
  selectedRunId: "",

  logFilter: "all",
  isRefreshing: false,
  lastRefreshTime: 0,
};

export const pipelineStore = writable<PipelineState>(initialState);

// Derived stores for computed values
export const filteredLogs = derived(pipelineStore, ($pipeline) =>
  $pipeline.logs.filter(
    (log) => $pipeline.logFilter === "all" || log.level === $pipeline.logFilter
  )
);

export const outputTooLarge = derived(pipelineStore, ($pipeline) => {
  if ($pipeline.output === null || $pipeline.output === undefined) return false;
  try {
    const jsonString = JSON.stringify($pipeline.output, null, 2);
    return jsonString.length > 5000000;
  } catch {
    return true;
  }
});

export const safeOutputDisplay = derived(pipelineStore, ($pipeline) => {
  if ($pipeline.output === null || $pipeline.output === undefined) return "";

  try {
    if (typeof $pipeline.output === "object" && $pipeline.output !== null) {
      const keys = Object.keys($pipeline.output);
      if (keys.length > 1000) {
        return `[LARGE OBJECT DETECTED]\nObject has ${keys.length} top-level keys\nUse "Download" to get complete output`;
      }
    }

    const jsonString = JSON.stringify($pipeline.output, null, 2);
    const maxDisplaySize = 500000;

    if (jsonString.length > maxDisplaySize) {
      const truncated = jsonString.substring(0, maxDisplaySize);
      const sizeMB = (jsonString.length / 1024 / 1024).toFixed(1);
      return `${truncated}\n\n... [TRUNCATED]\n... Full size: ${sizeMB}MB\n... Use "Download" to get complete output`;
    }

    return jsonString;
  } catch (error) {
    console.error("Failed to stringify output:", error);
    return `[ERROR: Unable to display output]\nReason: ${error}`;
  }
});

// Action creators
export const pipelineActions = {
  setRaceId: (raceId: string) => {
    pipelineStore.update((state) => ({ ...state, raceId: raceId }));
  },

  setExecutionState: (isExecuting: boolean) => {
    pipelineStore.update((state) => ({
      ...state,
      isExecuting,
      runStartTime: isExecuting ? Date.now() : null,
      runStatus: isExecuting ? "running" : state.runStatus,
    }));
  },

  updateRunProgress: (progress: number, message: string) => {
    pipelineStore.update((state) => ({
      ...state,
      progress,
      progressMessage: message,
    }));
  },

  setCurrentRun: (runId: string | null, step: string | null = null) => {
    pipelineStore.update((state) => ({
      ...state,
      currentRunId: runId,
      currentStep: step,
    }));
  },

  setRunStatus: (status: RunStatus | "idle") => {
    pipelineStore.update((state) => ({ ...state, runStatus: status }));
  },

  setOutput: (output: unknown) => {
    pipelineStore.update((state) => ({ ...state, output }));
  },

  setArtifacts: (artifacts: Artifact[]) => {
    pipelineStore.update((state) => ({ ...state, artifacts }));
  },

  addLog: (log: LogEntry) => {
    pipelineStore.update((state) => {
      const newLogs =
        state.logs.length >= 500
          ? [...state.logs.slice(-499), log]
          : [...state.logs, log];
      return { ...state, logs: newLogs };
    });
  },

  clearLogs: () => {
    pipelineStore.update((state) => ({ ...state, logs: [] }));
  },

  setLogFilter: (filter: "all" | "debug" | "info" | "warning" | "error") => {
    pipelineStore.update((state) => ({ ...state, logFilter: filter }));
  },

  setRunHistory: (runHistory: RunHistoryItem[]) => {
    pipelineStore.update((state) => ({ ...state, runHistory }));
  },

  setSelectedRun: (run: RunHistoryItem | null, runId: string = "") => {
    pipelineStore.update((state) => ({
      ...state,
      selectedRun: run,
      selectedRunId: runId,
    }));
  },

  setRefreshing: (isRefreshing: boolean) => {
    pipelineStore.update((state) => ({
      ...state,
      isRefreshing,
      lastRefreshTime: isRefreshing ? Date.now() : state.lastRefreshTime,
    }));
  },

  updateElapsedTime: (elapsedTime: number) => {
    pipelineStore.update((state) => ({ ...state, elapsedTime }));
  },

  updateStepStatus: (
    stepName: string,
    status: RunStatus,
    extras: Partial<RunStep> = {}
  ) => {
    pipelineStore.update((state) => {
      if (!state.selectedRun) return state;
      const updatedSelectedRun = {
        ...state.selectedRun,
        steps: state.selectedRun.steps.map((s) =>
          s.name === stepName ? { ...s, status, ...extras } : s
        ),
      };
      return { ...state, selectedRun: updatedSelectedRun };
    });
  },
};
