<script lang="ts">
  import type { Source } from '../types';

  export let source: Source;
  export let text: string | undefined = undefined;

  // Extract domain from URL for display
  $: domain = getDomain(source.url);

  function getDomain(url: string): string {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname.replace("www.", "");
    } catch {
      return url;
    }
  }
</script>

<a
  href={source.url}
  target="_blank"
  rel="noopener noreferrer"
  class="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 text-xs sm:text-sm underline"
  title="{source.title || text || domain} - Open in new tab"
>
  <span>{text || source.title || domain}</span>
  <svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      stroke-linecap="round"
      stroke-linejoin="round"
      stroke-width="2"
      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
    />
  </svg>
</a>
