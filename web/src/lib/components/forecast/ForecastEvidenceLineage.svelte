<script lang="ts">
  import type { ForecastEvidence } from "$lib/types";
  import { isExternalUrl } from "$lib/utils/url";
  import { getHostname } from "$lib/utils/forecastPresentation";

  export let entries: ForecastEvidence[] | null | undefined = undefined;

  // Entries flagged `inferred` are category labels the pipeline attaches to a
  // source ("Finance input used by the forecast"), not claims. The source list
  // already covers those, so only directly stated claims are shown here.
  $: stated = (entries ?? []).filter((entry) => entry && !entry.inferred);
</script>

{#if stated.length > 0}
  <div class="pt-2 border-t border-stroke/20" data-testid="evidence-lineage">
    <span
      class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
      >Evidence Lineage</span
    >
    <ul class="grid gap-1.5">
      {#each stated as item}
        <li class="rounded-lg bg-surface border border-stroke/60 px-3 py-2">
          <p class="text-[11px] leading-snug font-medium text-content-muted">
            {item.claim}
          </p>
          {#if isExternalUrl(item.source_url)}
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              class="mt-1 inline-flex items-center text-[10px] text-blue-600 dark:text-blue-400 hover:underline bg-surface border border-stroke px-2 py-0.5 rounded-md truncate max-w-[180px]"
            >
              {getHostname(item.source_url)} ->
            </a>
          {:else if item.source_url}
            <span
              class="mt-1 block text-[10px] text-content-subtle truncate max-w-[180px]"
              >{item.source_url}</span
            >
          {/if}
        </li>
      {/each}
    </ul>
  </div>
{/if}
