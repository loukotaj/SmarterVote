<script lang="ts">
  import type { RunStep } from "$lib/types";
  export let steps: RunStep[] = [];
  export let currentStep: string | null = null;
  export let setStartStep: (name: string) => void;
  export let API_BASE: string;

  function getStepStatusClass(step: RunStep): string {
    if (step.name === currentStep || step.status === 'running') {
      return 'bg-blue-50 border-blue-200 border-l-4 border-l-blue-500';
    }
    switch (step.status) {
      case 'completed':
        return 'bg-green-50 border-green-200';
      case 'failed':
        return 'bg-red-50 border-red-200';
      case 'pending':
        return 'bg-gray-50 border-gray-200';
      default:
        return 'bg-white border-gray-200';
    }
  }

  function getStepStatusIcon(step: RunStep): string {
    if (step.name === currentStep || step.status === 'running') {
      return '⏳';
    }
    switch (step.status) {
      case 'completed':
        return '✅';
      case 'failed':
        return '❌';
      case 'pending':
        return '⏸️';
      default:
        return '○';
    }
  }
</script>

<ul class="divide-y divide-gray-200 border border-gray-200 rounded-lg">
  {#each steps as step}
    <li
      class="p-3 flex items-center justify-between transition-colors duration-200 {getStepStatusClass(step)}"
    >
      <div class="flex items-center space-x-3 flex-1 min-w-0">
        <span class="text-lg flex-shrink-0" title="{step.status}">{getStepStatusIcon(step)}</span>
        <div class="flex flex-col min-w-0 flex-1">
          <div class="flex items-center space-x-2">
            <span class="font-medium text-sm text-gray-900 truncate">{step.name}</span>
            {#if step.name === currentStep}
              <span class="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 flex-shrink-0">
                Current
              </span>
            {/if}
          </div>
          <div class="text-xs text-gray-600 flex items-center space-x-2">
            <span class="capitalize">{step.status}</span>
            {#if step.duration_ms}
              <span>•</span>
              <span>{(step.duration_ms / 1000).toFixed(1)}s</span>
            {/if}
            {#if step.artifact_id}
              <span>•</span>
              <a
                class="text-blue-600 hover:underline"
                href={`${API_BASE}/artifact/${step.artifact_id}`}
                target="_blank"
                >View artifact</a
              >
            {/if}
          </div>
        </div>
      </div>
      <button
        class="btn-secondary ml-3 whitespace-nowrap text-sm"
        on:click={() => setStartStep(step.name)}
        disabled={step.name === currentStep}
      >
        {#if step.name === currentStep}
          Running...
        {:else}
          Set as start
        {/if}
      </button>
    </li>
  {/each}
</ul>
