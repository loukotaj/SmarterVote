<script lang="ts">
  export let active = false;
  export let onClick: () => void;
  export let disabled = false;
</script>

<button
  class="tab-button"
  class:active
  class:disabled
  on:click={onClick}
  {disabled}
>
  <slot />
</button>

<style lang="postcss">
  .tab-button {
    @apply px-3 py-2 text-sm font-medium border-b-2 border-transparent text-gray-500;
    @apply hover:text-gray-700 hover:border-gray-300 transition-colors duration-200;
  }

  .tab-button.active {
    @apply text-blue-600 border-blue-600;
  }

  .tab-button:disabled,
  .tab-button.disabled {
    @apply text-gray-400 cursor-not-allowed;
  }

  .tab-button:disabled:hover,
  .tab-button.disabled:hover {
    @apply text-gray-400 border-transparent;
  }
</style>
