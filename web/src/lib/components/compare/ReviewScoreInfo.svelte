<script lang="ts">
  export let panelId: string;

  let open = false;
</script>

<span class="ml-1 inline-flex align-middle">
  <button
    type="button"
    class="inline-flex h-7 w-7 items-center justify-center rounded-full border border-amber-400 bg-amber-50 text-xs font-extrabold leading-none text-amber-800 transition hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200"
    aria-label="About this automated research score"
    aria-expanded={open}
    aria-controls={open ? panelId : undefined}
    title="About this automated research score"
    on:click={() => (open = !open)}
    on:keydown={(event) => event.key === "Escape" && (open = false)}>i</button
  >
</span>

{#if open}
  <span
    id={panelId}
    role="note"
    class="mt-2 block rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs font-normal leading-5 text-amber-950 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100"
  >
    <strong>Automated Research Score:</strong> Separate AI models review sourcing,
    completeness, consistency, and neutrality. The score summarizes those research
    checks; it is not a guarantee that every claim is correct.
  </span>
{/if}
