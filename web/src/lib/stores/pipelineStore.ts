/**
 * Pipeline execution state management store
 */
import { writable, derived } from 'svelte/store';
import type { 
  RunInfo, 
  RunStatus, 
  RunStep, 
  Artifact, 
  LogEntry, 
  RunHistoryItem, 
  RunOptions 
} from '$lib/types';

interface PipelineState {
  // Pipeline configuration
  steps: string[];
  inputJson: string;
  useCloudStorage: boolean;
  executionMode: 'single' | 'range';
  startStep: string;
  endStep: string;
  
  // Current execution state
  isExecuting: boolean;
  currentRunId: string | null;
  runStatus: RunStatus | 'idle';
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
  logFilter: 'all' | 'debug' | 'info' | 'warning' | 'error';
  isRefreshing: boolean;
  lastRefreshTime: number;
}

const initialState: PipelineState = {
  steps: [],
  inputJson: '{\n  "race_id": "mo-senate-2024"\n}',
  useCloudStorage: false,
  executionMode: 'single',
  startStep: '',
  endStep: '',
  
  isExecuting: false,
  currentRunId: null,
  runStatus: 'idle',
  progress: 0,
  progressMessage: '',
  currentStep: null,
  runStartTime: null,
  elapsedTime: 0,
  
  output: null,
  artifacts: [],
  logs: [],
  runHistory: [],
  selectedRun: null,
  selectedRunId: '',
  
  logFilter: 'all',
  isRefreshing: false,
  lastRefreshTime: 0
};

export const pipelineStore = writable<PipelineState>(initialState);

// Derived stores for computed values
export const filteredLogs = derived(
  pipelineStore,
  ($pipeline) => $pipeline.logs.filter(
    (log) => $pipeline.logFilter === 'all' || log.level === $pipeline.logFilter
  )
);

export const outputTooLarge = derived(
  pipelineStore,
  ($pipeline) => {
    if ($pipeline.output === null || $pipeline.output === undefined) return false;
    try {
      const jsonString = JSON.stringify($pipeline.output, null, 2);
      return jsonString.length > 5000000; // 5MB threshold
    } catch {
      return true; // If it can't be stringified, consider it too large
    }
  }
);

export const safeOutputDisplay = derived(
  pipelineStore,
  ($pipeline) => {
    if ($pipeline.output === null || $pipeline.output === undefined) return '';

    try {
      // Quick size check first to avoid expensive stringify on huge objects
      if (typeof $pipeline.output === 'object' && $pipeline.output !== null) {
        // Rough heuristic: if object has many keys or deep nesting, it might be large
        const keys = Object.keys($pipeline.output);
        if (keys.length > 1000) {
          return `[LARGE OBJECT DETECTED]\nObject has ${keys.length} top-level keys\nUse "Download" to get complete output\nType: ${typeof $pipeline.output}`;
        }
      }

      const jsonString = JSON.stringify($pipeline.output, null, 2);
      const maxDisplaySize = 500000; // 500KB for display

      if (jsonString.length > maxDisplaySize) {
        const truncated = jsonString.substring(0, maxDisplaySize);
        const sizeMB = (jsonString.length / 1024 / 1024).toFixed(1);
        return `${truncated}\n\n... [TRUNCATED - Output too large for display]\n... Full size: ${sizeMB}MB\n... Use "Download" to get complete output`;
      }

      return jsonString;
    } catch (error) {
      console.error('Failed to stringify output for display:', error);

      // If stringify fails, try to provide useful info about the object
      if (typeof $pipeline.output === 'object' && $pipeline.output !== null) {
        const keys = Object.keys($pipeline.output);
        return `[ERROR: Unable to display output]\nReason: ${error}\nType: ${typeof $pipeline.output}\nKeys: ${keys.length > 10 ? keys.slice(0, 10).join(', ') + '...' : keys.join(', ')}\nUse "Download" to save raw output`;
      }

      return `[ERROR: Unable to display output]\nReason: ${error}\nType: ${typeof $pipeline.output}\nUse "Download" to save raw output`;
    }
  }
);

// Action creators
export const pipelineActions = {
  setSteps: (steps: string[]) => {
    pipelineStore.update(state => ({
      ...state,
      steps,
      startStep: steps[0] || '',
      endStep: steps[steps.length - 1] || ''
    }));
  },

  setInputJson: (inputJson: string) => {
    pipelineStore.update(state => ({ ...state, inputJson }));
  },

  setExecutionMode: (mode: 'single' | 'range') => {
    pipelineStore.update(state => ({ ...state, executionMode: mode }));
  },

  setStepRange: (startStep: string, endStep: string) => {
    pipelineStore.update(state => ({ ...state, startStep, endStep }));
  },

  setExecutionState: (isExecuting: boolean) => {
    pipelineStore.update(state => ({
      ...state,
      isExecuting,
      runStartTime: isExecuting ? Date.now() : null,
      runStatus: isExecuting ? 'running' : state.runStatus
    }));
  },

  updateRunProgress: (progress: number, message: string) => {
    pipelineStore.update(state => ({ ...state, progress, progressMessage: message }));
  },

  setCurrentRun: (runId: string | null, step: string | null = null) => {
    pipelineStore.update(state => ({ ...state, currentRunId: runId, currentStep: step }));
  },

  setRunStatus: (status: RunStatus | 'idle') => {
    pipelineStore.update(state => ({ ...state, runStatus: status }));
  },

  setOutput: (output: unknown) => {
    pipelineStore.update(state => ({ ...state, output }));
  },

  setArtifacts: (artifacts: Artifact[]) => {
    pipelineStore.update(state => ({ ...state, artifacts }));
  },

  addLog: (log: LogEntry) => {
    pipelineStore.update(state => {
      // Keep last 500 entries to prevent memory issues
      const newLogs = state.logs.length >= 500 
        ? [...state.logs.slice(-499), log]
        : [...state.logs, log];
      
      return { ...state, logs: newLogs };
    });
  },

  clearLogs: () => {
    pipelineStore.update(state => ({ ...state, logs: [] }));
  },

  setLogFilter: (filter: 'all' | 'debug' | 'info' | 'warning' | 'error') => {
    pipelineStore.update(state => ({ ...state, logFilter: filter }));
  },

  setRunHistory: (runHistory: RunHistoryItem[]) => {
    pipelineStore.update(state => ({ ...state, runHistory }));
  },

  setSelectedRun: (run: RunHistoryItem | null, runId: string = '') => {
    pipelineStore.update(state => ({ ...state, selectedRun: run, selectedRunId: runId }));
  },

  setRefreshing: (isRefreshing: boolean) => {
    pipelineStore.update(state => ({ 
      ...state, 
      isRefreshing,
      lastRefreshTime: isRefreshing ? Date.now() : state.lastRefreshTime
    }));
  },

  updateElapsedTime: (elapsedTime: number) => {
    pipelineStore.update(state => ({ ...state, elapsedTime }));
  },

  updateStepStatus: (stepName: string, status: RunStatus, extras: Partial<RunStep> = {}) => {
    pipelineStore.update(state => {
      if (!state.selectedRun) return state;
      
      const updatedSelectedRun = {
        ...state.selectedRun,
        steps: state.selectedRun.steps.map((s) =>
          s.name === stepName ? { ...s, status, ...extras } : s
        ),
      };
      
      return { ...state, selectedRun: updatedSelectedRun };
    });
  }
};