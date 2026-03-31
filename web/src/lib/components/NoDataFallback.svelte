<script lang="ts">
  /**
   * NoDataFallback component displays a friendly message when data is unavailable
   * and provides a link to create a GitHub issue to contribute missing data.
   */

  export let dataType: "issues" | "donors" | "voting" | "general" = "general";
  export let raceId: string = "";
  export let candidateName: string = "";

  const GITHUB_REPO = "loukotaj/SmarterVote";

  const dataTypeMessages: Record<string, string> = {
    issues: "We haven't found any issue stances for this candidate yet.",
    donors: "We haven't found donor information for this candidate yet.",
    voting:
      "We haven't found voting record information for this candidate yet. This could mean the candidate hasn't held public office or records aren't available.",
    general: "We haven't found this information for this candidate yet.",
  };

  function buildGitHubIssueUrl(): string {
    const baseUrl = `https://github.com/${GITHUB_REPO}/issues/new`;
    const params = new URLSearchParams({
      template: "missing-data.yml",
      title: `[Data] Missing data for: ${candidateName || "Unknown Candidate"}`,
      "race-id": raceId,
      "candidate-name": candidateName,
    });

    return `${baseUrl}?${params.toString()}`;
  }

  $: issueUrl = buildGitHubIssueUrl();
  $: message = dataTypeMessages[dataType] || dataTypeMessages.general;
</script>

<div class="no-data-fallback">
  <div class="icon-container">
    <svg
      class="icon"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      stroke-width="1.5"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z"
      />
    </svg>
  </div>

  <p class="message">{message}</p>

  <a
    href={issueUrl}
    target="_blank"
    rel="noopener noreferrer"
    class="help-button"
  >
    <svg
      class="button-icon"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      stroke-width="2"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"
      />
    </svg>
    Help improve this data
  </a>

  <p class="help-text">
    Know a reliable source? Submit a link and help make voter information more
    complete.
  </p>
</div>

<style lang="postcss">
  .no-data-fallback {
    @apply flex flex-col items-center justify-center py-8 px-4 text-center;
    @apply bg-surface-alt rounded-lg border border-stroke;
  }

  .icon-container {
    @apply mb-4;
  }

  .icon {
    @apply w-12 h-12 text-content-faint;
  }

  .message {
    @apply text-content-muted text-sm sm:text-base mb-4 max-w-md;
  }

  .help-button {
    @apply inline-flex items-center gap-2 px-4 py-2;
    @apply bg-blue-600 text-white font-medium rounded-lg;
    @apply hover:bg-blue-700 transition-colors duration-200;
    @apply text-sm sm:text-base;
  }

  .button-icon {
    @apply w-4 h-4;
  }

  .help-text {
    @apply text-content-subtle text-xs sm:text-sm mt-3 max-w-sm;
  }
</style>
