<script lang="ts">
  import type { ConfidenceLevel } from "$lib/types";
  export let confidence: ConfidenceLevel;

  const themes: Record<
    ConfidenceLevel,
    { bg: string; border: string; text: string; dot: string }
  > = {
    high: {
      bg: "bg-emerald-50/70 dark:bg-emerald-950/20",
      border: "border-emerald-200/60 dark:border-emerald-800/40",
      text: "text-emerald-700 dark:text-emerald-400",
      dot: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]",
    },
    medium: {
      bg: "bg-amber-50/70 dark:bg-amber-950/20",
      border: "border-amber-200/60 dark:border-amber-800/40",
      text: "text-amber-700 dark:text-amber-400",
      dot: "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.6)]",
    },
    low: {
      bg: "bg-rose-50/70 dark:bg-rose-950/20",
      border: "border-rose-200/60 dark:border-rose-800/40",
      text: "text-rose-700 dark:text-rose-400",
      dot: "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]",
    },
    unknown: {
      bg: "bg-gray-50/70 dark:bg-gray-800/20",
      border: "border-gray-200/60 dark:border-gray-700/40",
      text: "text-gray-500 dark:text-gray-400",
      dot: "bg-gray-400",
    },
  };

  $: style = themes[confidence] ?? themes.unknown;
  $: description =
    (
      {
        high: "High evidence confidence: multiple corroborating sources or an official candidate position.",
        medium: "Medium evidence confidence: at least one credible source.",
        low: "Low evidence confidence: inferred, unverified, or unsupported by a source.",
        unknown: "Evidence confidence has not been assessed.",
      } satisfies Record<ConfidenceLevel, string>
    )[confidence] ?? "Evidence confidence has not been assessed.";
</script>

<span
  class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold select-none transition-all duration-300 {style.bg} {style.border} {style.text}"
  title={description}
  aria-label={description}
>
  <span class="w-1.5 h-1.5 rounded-full {style.dot} transition-all duration-300"
  ></span>
  <span class="capitalize">{confidence}</span>
</span>
