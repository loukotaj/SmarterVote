<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  export let show = false;
  export let title = '';
  export let loading = false;
  export let contentTooLarge = false;
  
  const dispatch = createEventDispatcher();
  
  function close() {
    dispatch('close');
  }
  
  function handleBackdropClick() {
    close();
  }
  
  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      close();
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if show}
  <div class="modal-bg" role="dialog" tabindex="-1">
    <div class="modal-backdrop" role="button" tabindex="0" on:click={handleBackdropClick} on:keydown={() => {}}></div>
    <div class="modal-content">
      <button class="modal-close" on:click={close} title="Close">&times;</button>
      <div class="modal-title">{title}</div>
      
      {#if loading}
        <div class="text-gray-500 text-center py-8">Loading...</div>
      {:else}
        <!-- Warning for large content -->
        {#if contentTooLarge}
          <div class="mb-4 bg-yellow-50 border border-yellow-200 rounded-md p-3">
            <div class="flex items-start">
              <svg class="w-4 h-4 text-yellow-600 mt-0.5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
              </svg>
              <div>
                <h4 class="text-xs font-medium text-yellow-800">Large Content</h4>
                <p class="text-xs text-yellow-700 mt-1">Content has been truncated for display.</p>
              </div>
            </div>
          </div>
        {/if}
        
        <div class="modal-json">
          <slot />
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  /* Modal */
  .modal-bg {
    position: fixed; 
    inset: 0; 
    background: rgba(0, 0, 0, 0.35);
    z-index: 50; 
    display: flex; 
    align-items: center; 
    justify-content: center;
  }
  
  .modal-backdrop {
    position: absolute; 
    inset: 0; 
    cursor: pointer;
  }
  
  .modal-content {
    background: #fff; 
    border-radius: 0.75rem; 
    box-shadow: 0 8px 32px rgba(0,0,0,0.18);
    max-width: 600px; 
    width: 90vw; 
    max-height: 80vh; 
    overflow-y: auto; 
    padding: 2rem; 
    position: relative; 
    z-index: 1;
  }
  
  .modal-close {
    position: absolute; 
    top: 1rem; 
    right: 1rem; 
    background: none; 
    border: none; 
    font-size: 1.5rem; 
    color: #64748b; 
    cursor: pointer;
  }
  
  .modal-title { 
    font-size: 1.25rem; 
    font-weight: 600; 
    margin-bottom: 1rem; 
    color: #1e293b; 
  }
  
  .modal-json {
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 13px;
    background: #f8fafc;
    color: #334155;
    border-radius: 0.5rem;
    padding: 1rem;
    white-space: pre-wrap;
    word-wrap: break-word;
    word-break: break-word;
    max-height: 50vh;
    overflow-y: auto;
    overflow-x: auto;
    line-height: 1.4;
    /* Prevent modal from growing beyond viewport */
    max-width: 100%;
    /* Ensure scrollbars are always visible when needed */
    scrollbar-width: thin;
  }
</style>