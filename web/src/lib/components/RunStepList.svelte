<script lang="ts">
  import type { RunStep } from "$lib/types";
  export let steps: RunStep[] = [];
  export let currentStep: string | null = null;
  export let runFromStep: (name: string) => void;
  export let API_BASE: string;
  export let isStepRunning: boolean = false;

  // Determine if a step is ready to run (previous step completed or is first step)
  function isStepReadyToRun(step: RunStep, index: number): boolean {
    if (index === 0) return true; // First step is always ready
    const previousStep = steps[index - 1];
    return previousStep && previousStep.status === 'completed';
  }

  // Get visual styling for step status
  function getStepClasses(step: RunStep, index: number): string {
    if (step.name === currentStep || step.status === 'running') {
      return 'bg-yellow-50 border-l-4 border-yellow-400';
    }
    if (step.status === 'completed') {
      return 'bg-green-50 border-l-4 border-green-400';
    }
    if (step.status === 'failed') {
      return 'bg-red-50 border-l-4 border-red-400';
    }
    if (isStepReadyToRun(step, index)) {
      return 'bg-blue-50 border-l-4 border-blue-300 hover:bg-blue-100';
    }
    return 'bg-gray-50';
  }
</script>

<ul class="divide-y divide-gray-200 border border-gray-200 rounded-lg">
  {#each steps as step, index}
    <li class="p-3 flex items-center justify-between {getStepClasses(step, index)}">
      <div class="flex flex-col flex-1">
        <div class="flex items-center gap-2">
          <span class="font-medium text-sm">{step.name}</span>
          {#if step.status === 'completed'}
            <span class="text-green-600 text-xs">✓</span>
          {:else if step.status === 'running'}
            <span class="text-yellow-600 text-xs">⚙️</span>
          {:else if step.status === 'failed'}
            <span class="text-red-600 text-xs">✗</span>
          {:else if isStepReadyToRun(step, index)}
            <span class="text-blue-600 text-xs">→ Ready</span>
          {/if}
        </div>
        <span class="text-xs text-gray-600">
          {step.status}
          {#if step.duration_ms}
            · {(step.duration_ms / 1000).toFixed(1)}s
          {/if}
          {#if step.artifact_id}
            ·
            <a
              class="text-blue-600 hover:underline"
              href={`${API_BASE}/artifact/${step.artifact_id}`}
              target="_blank"
              >artifact</a
            >
          {/if}
        </span>
      </div>
      <button
        class="btn-secondary ml-2 whitespace-nowrap {isStepRunning ? 'opacity-50 cursor-not-allowed' : ''}"
        disabled={isStepRunning}
        on:click={() => runFromStep(step.name)}
      >
        {isStepReadyToRun(step, index) && step.status === 'pending' ? 'Run' : 'Run from this step'}
      </button>
    </li>
  {/each}
</ul>
