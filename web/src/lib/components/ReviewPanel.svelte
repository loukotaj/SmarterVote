<script lang="ts">
  import type { AgentReview } from "$lib/types";

  export let reviews: AgentReview[] = [];

  let collapsed = true;

  function verdictColor(verdict: string): string {
    switch (verdict) {
      case "approved":
        return "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200";
      case "needs_revision":
        return "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200";
      case "flagged":
        return "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200";
      default:
        return "bg-surface-alt text-content";
    }
  }

  function severityIcon(severity: string): string {
    switch (severity) {
      case "error":
        return "🔴";
      case "warning":
        return "🟡";
      default:
        return "🔵";
    }
  }
</script>

<div class="review-panel">
  <button class="review-title" on:click={() => (collapsed = !collapsed)} aria-expanded={!collapsed}>
    <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
    AI Review Status
    {#if reviews && reviews.length > 0}
      <span class="review-count">{reviews.length} review{reviews.length !== 1 ? "s" : ""}</span>
    {/if}
    <svg
      class="w-4 h-4 ml-auto transition-transform duration-200"
      class:rotate-180={!collapsed}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
    </svg>
  </button>

  {#if !collapsed}
    {#if !reviews || reviews.length === 0}
      <p class="review-empty">No AI review has been run for this race yet.</p>
    {:else}
      <div class="review-cards">
        {#each reviews as review}
        <div class="review-card">
          <div class="review-header">
            <span class="review-model">{review.model}</span>
            <span class="review-verdict {verdictColor(review.verdict)}">
              {review.verdict.replace("_", " ")}
            </span>
          </div>
          {#if review.summary}
            <p class="review-summary">{review.summary}</p>
          {/if}
          {#if review.flags && review.flags.length > 0}
            <details class="review-flags">
              <summary class="flags-toggle">
                {review.flags.length} flag{review.flags.length !== 1 ? "s" : ""}
              </summary>
              <ul class="flags-list">
                {#each review.flags as flag}
                  <li class="flag-item">
                    <span class="flag-severity">{severityIcon(flag.severity)}</span>
                    <div>
                      <span class="flag-field">{flag.field}</span>
                      <span class="flag-concern">{flag.concern}</span>
                      {#if flag.suggestion}
                        <span class="flag-suggestion">💡 {flag.suggestion}</span>
                      {/if}
                    </div>
                  </li>
                {/each}
              </ul>
            </details>
          {:else}
            <p class="review-all-clear">No issues found — profile looks good.</p>
          {/if}
          <span class="review-date">
            Reviewed: {(() => {
              try {
                const d = new Date(review.reviewed_at);
                return isNaN(d.getTime()) ? review.reviewed_at : d.toLocaleDateString();
              } catch {
                return review.reviewed_at;
              }
            })()}
          </span>
        </div>
      {/each}
    </div>
  {/if}
  {/if}
</div>

<style lang="postcss">
  .review-panel {
    @apply bg-page border border-stroke rounded-lg p-4 sm:p-6 mb-6;
  }

  .review-title {
    @apply flex items-center gap-2 text-base font-semibold text-content w-full
           text-left cursor-pointer hover:text-content-muted transition-colors duration-150;
  }

  .review-count {
    @apply text-xs font-normal text-content-subtle bg-surface-alt px-2 py-0.5 rounded-full;
  }

  .review-cards {
    @apply grid gap-4 sm:grid-cols-2 mt-4;
  }

  .review-card {
    @apply bg-surface rounded-lg border border-stroke p-4;
  }

  .review-header {
    @apply flex items-center justify-between mb-2;
  }

  .review-model {
    @apply text-sm font-medium text-content-muted;
  }

  .review-verdict {
    @apply px-2 py-1 rounded-full text-xs font-medium capitalize;
  }

  .review-summary {
    @apply text-sm text-content-muted mb-3;
  }

  .review-flags {
    @apply mb-2;
  }

  .flags-toggle {
    @apply text-xs font-medium text-content-subtle cursor-pointer hover:text-content-muted;
  }

  .flags-list {
    @apply mt-2 space-y-2;
  }

  .flag-item {
    @apply flex items-start gap-2 text-xs;
  }

  .flag-severity {
    @apply flex-shrink-0;
  }

  .flag-field {
    @apply font-mono text-content-subtle block;
  }

  .flag-concern {
    @apply text-content-muted block;
  }

  .flag-suggestion {
    @apply text-blue-600 block mt-1;
  }

  .review-date {
    @apply text-xs text-content-faint;
  }

  .review-empty {
    @apply text-sm text-content-subtle italic;
  }

  .review-all-clear {
    @apply text-sm text-green-600 font-medium mb-2;
  }
</style>
