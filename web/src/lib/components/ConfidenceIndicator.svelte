<script lang="ts">
  import type { ConfidenceLevel } from "$lib/types";

  export let confidence: ConfidenceLevel;

  $: iconClass = getConfidenceClass(confidence);
  $: iconSymbol = getConfidenceSymbol(confidence);

  function getConfidenceClass(level: ConfidenceLevel): string {
    switch (level) {
      case "high":
        return "text-green-600";
      case "medium":
        return "text-yellow-600";
      case "low":
        return "text-red-600";
      case "unknown":
        return "text-gray-400";
      default:
        return "text-gray-400";
    }
  }

  function getConfidenceSymbol(level: ConfidenceLevel): string {
    switch (level) {
      case "high":
        return "●";
      case "medium":
        return "◐";
      case "low":
        return "○";
      case "unknown":
        return "?";
      default:
        return "?";
    }
  }
</script>

<span
  class="inline-flex items-center gap-1 text-xs sm:text-sm font-medium {iconClass}"
  title="Confidence: {confidence}"
>
  <span class="text-base sm:text-lg leading-none">{iconSymbol}</span>
  <span class="capitalize">{confidence}</span>
</span>
