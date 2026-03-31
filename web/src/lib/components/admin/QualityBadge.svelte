<script lang="ts">
  export let score: number = 0; // 0–100
  $: label = score >= 80 ? "High" : score >= 60 ? "Good" : score >= 40 ? "Fair" : "Low";
  $: colorClass =
    score >= 80
      ? "bg-green-100 text-green-800 border-green-200"
      : score >= 60
        ? "bg-yellow-100 text-yellow-800 border-yellow-200"
        : score >= 40
          ? "bg-orange-100 text-orange-800 border-orange-200"
          : "bg-red-100 text-red-800 border-red-200";
</script>

<span class="inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded-full border {colorClass}">
  {label} · {score}
</span>
