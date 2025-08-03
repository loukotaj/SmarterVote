<script lang="ts">
  export let tag: string = "div";
</script>

<svelte:element
  this={tag}
  class={`card ${$$props.class ?? ""}`}
  {...$$restProps}
>
  <slot />
</svelte:element>

<style lang="postcss">
  .card {
    @apply bg-white rounded-lg shadow;
  }
</style>
