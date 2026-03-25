<script lang="ts">
  import type { AgentReview } from "$lib/types";

  export let reviews: AgentReview[] = [];

  function verdictColor(verdict: string): string {
    switch (verdict) {
      case "approved":
        return "bg-green-100 text-green-800";
      case "needs_revision":
        return "bg-yellow-100 text-yellow-800";
      case "flagged":
        return "bg-red-100 text-red-800";
      default:
        return "bg-gray-100 text-gray-800";
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

{#if reviews && reviews.length > 0}
  <div class="review-panel">
    <h3 class="review-title">
      <svg
        class="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      AI Review Status
    </h3>

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
                {review.flags.length} flag{review.flags.length !== 1
                  ? "s"
                  : ""}
              </summary>
              <ul class="flags-list">
                {#each review.flags as flag}
                  <li class="flag-item">
                    <span class="flag-severity"
                      >{severityIcon(flag.severity)}</span
                    >
                    <div>
                      <span class="flag-field">{flag.field}</span>
                      <span class="flag-concern">{flag.concern}</span>
                      {#if flag.suggestion}
                        <span class="flag-suggestion"
                          >💡 {flag.suggestion}</span
                        >
                      {/if}
                    </div>
                  </li>
                {/each}
              </ul>
            </details>
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
  </div>
{/if}

<style lang="postcss">
  .review-panel {
    @apply bg-gray-50 border border-gray-200 rounded-lg p-4 sm:p-6 mb-6;
  }

  .review-title {
    @apply flex items-center gap-2 text-lg font-semibold text-gray-900 mb-4;
  }

  .review-cards {
    @apply grid gap-4 sm:grid-cols-2;
  }

  .review-card {
    @apply bg-white rounded-lg border border-gray-200 p-4;
  }

  .review-header {
    @apply flex items-center justify-between mb-2;
  }

  .review-model {
    @apply text-sm font-medium text-gray-700;
  }

  .review-verdict {
    @apply px-2 py-1 rounded-full text-xs font-medium capitalize;
  }

  .review-summary {
    @apply text-sm text-gray-600 mb-3;
  }

  .review-flags {
    @apply mb-2;
  }

  .flags-toggle {
    @apply text-xs font-medium text-gray-500 cursor-pointer hover:text-gray-700;
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
    @apply font-mono text-gray-500 block;
  }

  .flag-concern {
    @apply text-gray-700 block;
  }

  .flag-suggestion {
    @apply text-blue-600 block mt-1;
  }

  .review-date {
    @apply text-xs text-gray-400;
  }
</style>
