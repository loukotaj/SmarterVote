<script lang="ts">
  import type { RunStep } from "$lib/types";
  export let steps: RunStep[] = [];
  export let currentStep: string | null = null;
  export let runFromStep: (name: string) => void;
  export let API_BASE: string;
</script>

<ul class="divide-y divide-gray-200 border border-gray-200 rounded-lg">
  {#each steps as step}
    <li
      class="p-2 flex items-center justify-between {step.name === currentStep || step.status === 'running' ? 'bg-yellow-50' : ''}"
    >
      <div class="flex flex-col">
        <span class="font-medium text-sm">{step.name}</span>
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
        class="btn-secondary ml-2 whitespace-nowrap"
        on:click={() => runFromStep(step.name)}
      >
        Run from this step
      </button>
    </li>
  {/each}
</ul>
