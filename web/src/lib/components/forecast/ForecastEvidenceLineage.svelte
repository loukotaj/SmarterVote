<script lang="ts">
  import type { ForecastEvidence } from "$lib/types";
  import { isExternalUrl } from "$lib/utils/url";
  import {
    countInferredEvidence,
    getHostname,
    groupEvidenceByKind,
  } from "$lib/utils/forecastPresentation";

  export let entries: ForecastEvidence[] | null | undefined = undefined;

  $: groups = groupEvidenceByKind(entries);
  $: total = groups.reduce((sum, group) => sum + group.entries.length, 0);
  $: inferredCount = countInferredEvidence(entries);
</script>

<!--
  Per-claim attribution for a forecast. Entries flagged `inferred` had their
  source attached by the pipeline without that source stating the claim
  outright, so they are styled distinctly from directly stated evidence.
-->
{#if groups.length > 0}
  <div class="pt-2 border-t border-stroke/20" data-testid="evidence-lineage">
    <div class="flex items-center justify-between gap-2 mb-2">
      <span
        class="font-bold text-content uppercase tracking-wider text-[9px] block"
        >Evidence Lineage</span
      >
      <span class="text-[9px] text-content-subtle font-bold">
        {total} claim{total === 1 ? "" : "s"}{inferredCount > 0
          ? ` - ${inferredCount} inferred`
          : ""}
      </span>
    </div>

    <div class="grid gap-2">
      {#each groups as group (group.kind)}
        <div>
          <span
            class="block text-[9px] font-bold text-content-subtle uppercase tracking-wider mb-1"
            >{group.label}</span
          >
          <ul class="grid gap-1.5">
            {#each group.entries as item}
              <li
                class={`rounded-lg bg-surface px-3 py-2 border-l-2 ${
                  item.inferred
                    ? "border border-dashed border-amber-300 border-l-amber-500 dark:border-amber-700/70 dark:border-l-amber-500"
                    : "border border-stroke/60 border-l-emerald-500 dark:border-l-emerald-400"
                }`}
              >
                <p
                  class="text-[11px] leading-snug font-medium text-content-muted"
                >
                  {item.claim}
                </p>
                <div
                  class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px]"
                >
                  <span
                    class={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider leading-none ${
                      item.inferred
                        ? "bg-amber-50 text-amber-800 border-amber-300 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-700/60"
                        : "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-700/60"
                    }`}
                    title={item.inferred
                      ? "The source was used by the forecast, but does not state this claim outright."
                      : "The linked source states this claim directly."}
                  >
                    {item.inferred ? "Inferred" : "Stated in source"}
                  </span>
                  {#if isExternalUrl(item.source_url)}
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="inline-flex items-center text-[10px] text-blue-600 dark:text-blue-400 hover:underline bg-surface border border-stroke px-2 py-0.5 rounded-md truncate max-w-[180px]"
                    >
                      {getHostname(item.source_url)} ->
                    </a>
                  {:else if item.source_url}
                    <span class="text-content-subtle truncate max-w-[180px]"
                      >{item.source_url}</span
                    >
                  {/if}
                </div>
              </li>
            {/each}
          </ul>
        </div>
      {/each}
    </div>

    {#if inferredCount > 0}
      <p class="mt-2 text-[9px] text-content-subtle font-medium leading-snug">
        "Inferred" means the forecast used that source but the source does not
        state the claim outright.
      </p>
    {/if}
  </div>
{/if}
