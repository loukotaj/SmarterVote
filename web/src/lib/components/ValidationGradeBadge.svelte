<script lang="ts">
  import type { ValidationGrade } from "$lib/types";

  export let grade: ValidationGrade;

  let showPopover = false;

  function gradeColor(g: string): string {
    switch (g) {
      case "A":
        return "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200 border-green-300 dark:border-green-700";
      case "B":
        return "bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 border-blue-300 dark:border-blue-700";
      case "C":
        return "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-200 border-yellow-300 dark:border-yellow-700";
      case "D":
        return "bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-200 border-orange-300 dark:border-orange-700";
      case "F":
        return "bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200 border-red-300 dark:border-red-700";
      default:
        return "bg-surface-alt text-content border-stroke";
    }
  }

  function scrollToReview() {
    showPopover = false;
    const el = document.getElementById("ai-review");
    if (el) el.scrollIntoView({ behavior: "smooth" });
  }
</script>

<div class="grade-wrapper">
  <button
    class="grade-badge {gradeColor(grade.grade)}"
    on:click={() => (showPopover = !showPopover)}
    on:keydown={(e) => e.key === "Escape" && (showPopover = false)}
    aria-label="Validation Grade: {grade.grade}"
  >
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
    <span class="grade-letter">{grade.grade}</span>
    <span class="grade-label">Validation</span>
  </button>

  {#if showPopover}
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="popover-backdrop" on:click={() => (showPopover = false)}></div>
    <div class="popover" role="tooltip">
      <div class="popover-header">
        <span class="popover-title">AI Validation Grade</span>
        <span class="popover-grade {gradeColor(grade.grade)}">{grade.grade}</span>
      </div>
      <p class="popover-score">Score: {grade.score}/100</p>
      <p class="popover-summary">{grade.summary}</p>
      <p class="popover-explain">
        Multiple AI models independently review each race profile for factual accuracy,
        source quality, completeness, and neutrality. The grade reflects the average score
        across all reviewers.
      </p>
      <button class="popover-link" on:click={scrollToReview}>
        View Full Review
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
        </svg>
      </button>
    </div>
  {/if}
</div>

<style lang="postcss">
  .grade-wrapper {
    @apply relative inline-flex;
  }

  .grade-badge {
    @apply inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border
           text-sm font-semibold cursor-pointer transition-all duration-150
           hover:shadow-md active:scale-95;
  }

  .grade-letter {
    @apply text-base font-bold leading-none;
  }

  .grade-label {
    @apply text-xs font-medium opacity-75;
  }

  .popover-backdrop {
    @apply fixed inset-0 z-40;
  }

  .popover {
    @apply absolute top-full left-0 mt-2 z-50 w-72
           bg-surface border border-stroke rounded-lg shadow-lg p-4;
  }

  .popover-header {
    @apply flex items-center justify-between mb-2;
  }

  .popover-title {
    @apply text-sm font-semibold text-content;
  }

  .popover-grade {
    @apply px-2 py-0.5 rounded text-sm font-bold border;
  }

  .popover-score {
    @apply text-sm font-medium text-content-muted mb-1;
  }

  .popover-summary {
    @apply text-sm text-content-muted mb-3;
  }

  .popover-explain {
    @apply text-xs text-content-subtle mb-3 leading-relaxed;
  }

  .popover-link {
    @apply inline-flex items-center gap-1 text-sm font-medium
           text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300
           cursor-pointer transition-colors duration-150;
  }
</style>
