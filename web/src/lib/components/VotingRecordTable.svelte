<script lang="ts">
  import NoDataFallback from "./NoDataFallback.svelte";
  import type { Source } from "$lib/types";
  import { isExternalUrl } from "$lib/utils/url";

  export let votingSummary: string = "";
  export let votingSourceUrl: string = "";
  export let votingSources: Source[] = [];
  export let raceId: string = "";
  export let candidateName: string = "";

  type SourceLink = { url: string; title: string };

  function titleForUrl(url: string): string {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return url;
    }
  }

  function stripInlineSources(summary: string): string {
    const markerIndex = summary.search(/\bSources:\s*https?:\/\//i);
    return (markerIndex >= 0 ? summary.slice(0, markerIndex) : summary).trim();
  }

  function extractInlineSourceUrls(summary: string): string[] {
    return (summary.match(/https?:\/\/[^\s;,]+/g) ?? []).map((url) =>
      url.replace(/[.)\]]+$/, ""),
    );
  }

  function mergeSourceLinks(
    sources: Source[],
    sourceUrl: string,
    legacyUrls: string[],
  ): SourceLink[] {
    const links: SourceLink[] = [];
    const seen = new Set<string>();
    const add = (url: string | undefined, title?: string) => {
      if (!isExternalUrl(url)) return;
      const safeUrl = url.trim();
      if (seen.has(safeUrl)) return;
      seen.add(safeUrl);
      links.push({ url: safeUrl, title: title || titleForUrl(safeUrl) });
    };

    add(sourceUrl, "View full voting record");
    for (const source of sources) add(source.url, source.title ?? undefined);
    for (const url of legacyUrls) add(url);
    return links;
  }

  $: cleanVotingSummary = stripInlineSources(votingSummary);
  $: votingSourceLinks = mergeSourceLinks(
    votingSources,
    votingSourceUrl,
    extractInlineSourceUrls(votingSummary),
  );
</script>

<div class="voting-container">
  {#if !cleanVotingSummary && votingSourceLinks.length === 0}
    <NoDataFallback dataType="voting" {raceId} {candidateName} />
  {:else}
    {#if cleanVotingSummary}
      <div class="voting-summary">
        <p class="summary-text">{cleanVotingSummary}</p>
      </div>
    {/if}

    {#if votingSourceLinks.length > 0}
      <div class="source-list" aria-label="Voting record sources">
        <p class="source-list-title">Sources</p>
        <div class="source-links">
          {#each votingSourceLinks as source}
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              class="source-link-btn"
            >
              {source.title}
              <span aria-hidden="true">→</span>
            </a>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</div>

<style lang="postcss">
  .voting-container {
    @apply space-y-4;
  }

  .voting-summary {
    background-color: rgb(var(--sv-surface-alt));
    border: 1px solid rgb(var(--sv-border));
    @apply rounded-lg p-4;
  }

  .summary-text {
    color: rgb(var(--sv-text));
    @apply text-sm leading-relaxed;
  }

  .source-list {
    @apply space-y-2;
  }

  .source-list-title {
    color: rgb(var(--sv-text-muted));
    @apply text-xs font-semibold uppercase tracking-wide;
  }

  .source-links {
    @apply flex flex-wrap gap-2;
  }

  .source-link-btn {
    @apply inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors;
    background-color: rgb(var(--sv-primary) / 0.1);
    color: rgb(var(--sv-primary));
    border: 1px solid rgb(var(--sv-primary) / 0.3);
  }
  .source-link-btn:hover {
    background-color: rgb(var(--sv-primary) / 0.2);
  }
</style>
