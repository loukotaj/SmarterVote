<script lang="ts">
  export let panelId: string;

  let open = false;
</script>

<span class="ml-1 inline-flex align-middle">
  <button
    type="button"
    class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-amber-400 bg-amber-50 text-[11px] font-extrabold leading-none text-amber-800 transition hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200"
    aria-label="About this AI review score"
    aria-expanded={open}
    aria-controls={panelId}
    title="About this AI review score"
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
    <strong>AI-generated research:</strong> This score comes from other AI models
    reviewing the generating model's methodology, sourcing, completeness, and signs
    of bias. It is not independent fact-checking and does not validate that the underlying
    information is correct.
  </span>
{/if}
