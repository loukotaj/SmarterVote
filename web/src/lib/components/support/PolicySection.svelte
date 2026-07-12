<script lang="ts">
  export let title: string;
</script>

<section
  class="rounded-xl border border-border bg-surface p-5 shadow-sm sm:p-7"
>
  <h2 class="mb-3 text-xl font-semibold text-content">{title}</h2>
  <div class="space-y-3 leading-7">
    <slot />
  </div>
</section>
