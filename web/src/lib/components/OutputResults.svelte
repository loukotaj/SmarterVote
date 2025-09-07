<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { copyToClipboard, downloadAsJson, safeJsonStringify } from '$lib/utils/pipelineUtils';
  
  export let output: unknown = null;
  export let onAddLog: (level: string, message: string) => void = () => {};
  
  const dispatch = createEventDispatcher<{
    'use-as-input': void;
  }>();
  
  $: outputResult = safeJsonStringify(output, 500000);
  $: outputTooLarge = output !== null && output !== undefined && (() => {
    try {
      const jsonString = JSON.stringify(output, null, 2);
      return jsonString.length > 5000000; // 5MB threshold
    } catch {
      return true;
    }
  })();
  
  async function copyOutput() {
    if (output !== null && output !== undefined) {
      try {
        const jsonString = JSON.stringify(output, null, 2);
        const success = await copyToClipboard(jsonString);
        
        if (success) {
          onAddLog('info', 'Output copied to clipboard');
        } else {
          onAddLog('warning', `Output too large to copy (${(jsonString.length / 1024 / 1024).toFixed(1)}MB). Use download instead.`);
        }
      } catch (error) {
        console.error('Failed to copy output:', error);
        onAddLog('error', 'Failed to copy output to clipboard');
      }
    }
  }
  
  function downloadOutput() {
    if (output !== null && output !== undefined) {
      const success = downloadAsJson(output);
      
      if (success) {
        try {
          const jsonString = JSON.stringify(output, null, 2);
          const sizeMB = (new Blob([jsonString]).size / 1024 / 1024).toFixed(1);
          onAddLog('info', `Downloading output (${sizeMB}MB)`);
        } catch {
          onAddLog('info', 'Downloading output');
        }
      } else {
        onAddLog('error', 'Failed to create download file');
      }
    }
  }
  
  function useAsInput() {
    dispatch('use-as-input');
  }
</script>

{#if output !== null}
  <div class="card p-6">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-gray-900">Results</h3>
      <div class="flex space-x-2">
        <button
          on:click={copyOutput}
          class="btn-secondary text-sm"
          disabled={outputTooLarge}
          title={outputTooLarge ? "Output too large to copy safely" : "Copy to clipboard"}
        >
          Copy
        </button>
        <button 
          on:click={downloadOutput} 
          class="btn-secondary text-sm"
        >
          Download
        </button>
        <button 
          on:click={useAsInput} 
          class="btn-secondary text-sm"
        >
          Use as Input
        </button>
      </div>
    </div>

    <!-- Warning for large outputs -->
    {#if outputTooLarge}
      <div class="mb-4 bg-yellow-50 border border-yellow-200 rounded-md p-3">
        <div class="flex items-start">
          <svg class="w-5 h-5 text-yellow-600 mt-0.5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
          <div>
            <h4 class="text-sm font-medium text-yellow-800">Large Output Detected</h4>
            <p class="text-sm text-yellow-700 mt-1">
              This output is very large and has been truncated for display.
              Use the "Download" button to get the complete result.
            </p>
          </div>
        </div>
      </div>
    {/if}

    <div class="output-display custom-scrollbar">
      {outputResult.content}
    </div>
  </div>
{/if}

<style>
  .output-display {
    white-space: pre-wrap;
    word-wrap: break-word;
    word-break: break-word;
    background: #0f172a;
    color: #e2e8f0;
    padding: 1rem;
    border-radius: 0.5rem;
    max-height: 400px;
    overflow: auto;
    font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
    font-size: 12px;
    line-height: 1.4;
    /* Prevent horizontal scrolling issues */
    overflow-x: auto;
    overflow-y: auto;
    /* Ensure container doesn't grow beyond bounds */
    max-width: 100%;
    min-height: 100px;
  }

  .custom-scrollbar::-webkit-scrollbar { 
    width: 6px; 
  }
  
  .custom-scrollbar::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 3px;
  }
  
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;
  }
  
  .custom-scrollbar::-webkit-scrollbar-thumb:hover { 
    background: #94a3b8; 
  }
</style>