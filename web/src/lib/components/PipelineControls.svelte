<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import RunStepList from '$lib/components/RunStepList.svelte';
  import { getStatusClass } from '$lib/utils/pipelineUtils';
  import type { RunHistoryItem } from '$lib/types';
  
  // Note: steps prop is passed to RunStepList component when selectedRun is available
  export let steps: string[] = [];
  export let inputJson = '';
  export let useCloudStorage = false;
  export let executionMode: 'single' | 'range' = 'single';
  export let startStep = '';
  export let endStep = '';
  export let selectedRun: RunHistoryItem | null = null;
  export let selectedRunId = '';
  export let runHistory: RunHistoryItem[] = [];
  export let isExecuting = false;
  export let currentStep: string | null = null;
  export let API_BASE = '';
  
  const dispatch = createEventDispatcher<{
    'new-run': void;
    'run-select': { target: { value: string } };
    'input-change': string;
    'cloud-storage-change': boolean;
    'execution-mode-change': 'single' | 'range';
    'step-range-change': { start: string; end: string };
    'execute': { mode: 'single' | 'range'; startStep: string; endStep: string };
    'set-start-step': string;
  }>();
  
  function handleNewRun() {
    dispatch('new-run');
  }
  
  function handleRunSelect(event: Event) {
    dispatch('run-select', { target: { value: (event.target as HTMLSelectElement).value } });
  }
  
  function handleInputChange(event: Event) {
    const value = (event.target as HTMLTextAreaElement).value;
    dispatch('input-change', value);
  }
  
  function handleCloudStorageChange(event: Event) {
    const checked = (event.target as HTMLInputElement).checked;
    dispatch('cloud-storage-change', checked);
  }
  
  function handleExecutionModeChange(mode: 'single' | 'range') {
    dispatch('execution-mode-change', mode);
  }
  
  function handleExecute() {
    dispatch('execute', { mode: executionMode, startStep, endStep });
  }
  
  function handleSetStartStep(stepName: string) {
    dispatch('set-start-step', stepName);
  }
</script>

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
          on:click={handleNewRun}
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
      >Input JSON</label>
      <textarea
        id="inputJson"
        value={inputJson}
        on:input={handleInputChange}
        class="json-editor"
        spellcheck="false"
        placeholder="{`{\"race_id\": \"example_race_2024\"}`}"
      />
    </div>

    <!-- Options -->
    <details class="options border border-gray-200 rounded-lg p-4">
      <summary class="cursor-pointer font-medium text-gray-700 mb-3">
        Storage Options
      </summary>
      <div class="space-y-3">
        <label class="flex items-center justify-between">
          <span class="text-sm text-gray-700">Storage Location</span>
          <div class="flex items-center space-x-2">
            <span class="text-xs text-gray-500">Local</span>
            <input
              type="checkbox"
              checked={useCloudStorage}
              on:change={handleCloudStorageChange}
              class="toggle-switch"
            />
            <span class="text-xs text-gray-500">Cloud</span>
          </div>
        </label>
        <p class="text-xs text-gray-500">
          {#if useCloudStorage}
            Artifacts will be stored in cloud services (GCS, etc.)
          {:else}
            Artifacts will be stored locally on the filesystem
          {/if}
        </p>
      </div>
    </details>

    <!-- Execution Mode Options -->
    <details class="options border border-gray-200 rounded-lg p-4">
      <summary class="cursor-pointer font-medium text-gray-700 mb-3">
        Execution Mode
      </summary>
      <div class="space-y-3">
        <div class="space-y-2">
          <label class="flex items-center">
            <input 
              type="radio" 
              checked={executionMode === 'single'}
              on:change={() => handleExecutionModeChange('single')}
              class="mr-2" 
            />
            <span class="text-sm text-gray-700">Run Single Step</span>
          </label>
          <label class="flex items-center">
            <input 
              type="radio" 
              checked={executionMode === 'range'}
              on:change={() => handleExecutionModeChange('range')}
              class="mr-2" 
            />
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
        on:click={handleExecute}
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
    </div>
  </div>
</div>

<style>
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

  .options label { 
    display: flex; 
    align-items: center; 
    gap: 0.5rem; 
    margin-bottom: 0.5rem; 
  }

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
</style>