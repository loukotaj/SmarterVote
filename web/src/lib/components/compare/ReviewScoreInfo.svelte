<script lang="ts">
  import { onMount } from "svelte";

  export let panelId: string;

  let open = false;
  let container: HTMLSpanElement;

  function toggleOpen(e: MouseEvent) {
    e.stopPropagation();
    open = !open;
  }

  function handleWindowKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape" && open) {
      open = false;
    }
  }

  function handleWindowClick(event: MouseEvent) {
    if (open && container && !container.contains(event.target as Node)) {
      open = false;
    }
  }

  onMount(() => {
    window.addEventListener("click", handleWindowClick);
    window.addEventListener("keydown", handleWindowKeyDown);
    return () => {
      window.removeEventListener("click", handleWindowClick);
      window.removeEventListener("keydown", handleWindowKeyDown);
    };
  });
</script>

<span
  bind:this={container}
  class="relative inline-flex items-center align-baseline mx-1"
>
  <button
    type="button"
    class="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-emerald-300 bg-emerald-100/80 text-emerald-800 transition-all hover:border-emerald-400 hover:bg-emerald-200 hover:scale-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 dark:border-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 dark:hover:bg-emerald-900"
    aria-label="About this AI review score"
    aria-expanded={open}
    aria-controls={panelId}
    title="About this AI review score"
    on:click={toggleOpen}
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      class="h-2.5 w-2.5"
      aria-hidden="true"
    >
      <path
        fill-rule="evenodd"
        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.25v4.25a.75.75 0 001.5 0v-5a.75.75 0 00-.75-.75H9z"
        clip-rule="evenodd"
      />
    </svg>
  </button>

  {#if open}
    <div
      id={panelId}
      role="note"
      class="absolute left-0 top-full z-50 mt-2 w-72 sm:w-80 max-w-[calc(100vw-3rem)] rounded-xl border border-emerald-200/90 bg-white/95 p-3.5 text-xs font-normal leading-5 text-content shadow-xl shadow-emerald-950/10 backdrop-blur-md dark:border-emerald-800/90 dark:bg-slate-900/95 dark:text-emerald-100"
    >
      <div
        class="absolute -top-1.5 left-1.5 h-3 w-3 rotate-45 border-l border-t border-emerald-200/90 bg-white dark:border-emerald-800/90 dark:bg-slate-900"
      ></div>
      <div
        class="relative z-10 flex items-center justify-between gap-2 border-b border-emerald-100 pb-2 mb-2 dark:border-emerald-900/60"
      >
        <span
          class="font-extrabold text-emerald-900 dark:text-emerald-200 flex items-center gap-1.5"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            class="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400"
          >
            <path
              fill-rule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.25v4.25a.75.75 0 001.5 0v-5a.75.75 0 00-.75-.75H9z"
              clip-rule="evenodd"
            />
          </svg>
          AI-generated research
        </span>
        <button
          type="button"
          on:click={() => (open = false)}
          class="rounded p-0.5 text-content-subtle hover:bg-emerald-100 hover:text-content dark:hover:bg-emerald-900/50"
          aria-label="Close note"
        >
          ✕
        </button>
      </div>
      <p class="relative z-10 text-content-muted dark:text-emerald-200/80">
        <strong>AI-generated research:</strong> This score comes from other AI models
        reviewing the generating model's methodology, sourcing, completeness, and
        signs of bias. It is not independent fact-checking and does not validate
        that the underlying information is correct.
      </p>
    </div>
  {/if}
</span>
