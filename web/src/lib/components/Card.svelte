<script lang="ts">
  export let tag: string = "div";
</script>

<svelte:element this={tag} class="bg-white rounded-lg shadow" {...$$restProps}>
  <slot />
</svelte:element>
