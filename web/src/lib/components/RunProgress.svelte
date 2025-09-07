<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { formatDuration, getStatusClass } from '$lib/utils/pipelineUtils';
  import type { RunStatus } from '$lib/types';
  
  export let isExecuting = false;
  export let runStatus: RunStatus | 'idle' = 'idle';
  export let progress = 0;
  export let progressMessage = '';
  export let elapsedTime = 0;
  export let currentRunId: string | null = null;
  export let errorCount = 0;
  
  const dispatch = createEventDispatcher<{
    'stop-execution': void;
  }>();
  
  function stopExecution() {
    dispatch('stop-execution');
  }
</script>

{#if isExecuting || runStatus !== "idle"}
  <div class="card p-6">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-gray-900">Current Run</h3>
      <div class="flex items-center space-x-2">
        <span
          class="px-3 py-1 rounded-full text-xs font-medium border {getStatusClass(runStatus)}"
        >
          {runStatus.charAt(0).toUpperCase() + runStatus.slice(1)}
        </span>
        {#if isExecuting}
          <button on:click={stopExecution} class="btn-danger text-sm">
            Stop
          </button>
        {/if}
      </div>
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
          {errorCount}
        </div>
        <div class="text-gray-600">Errors</div>
      </div>
    </div>
  </div>
{/if}

<style>
  .progress-bar {
    transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
  }
</style>