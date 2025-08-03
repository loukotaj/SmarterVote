<script lang="ts">
  export let tag: string = "div";
  export let className = "";
  export { className as class };
</script>

<svelte:element this={tag} class={`card ${className}`.trim()} {...$$restProps}>
  <slot />
</svelte:element>

<style lang="postcss">
  .card {
    @apply bg-white rounded-lg shadow;
  }
</style>
