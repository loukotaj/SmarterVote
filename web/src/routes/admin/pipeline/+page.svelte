<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { browser } from '$app/environment';
  
  // Stores
  import { 
    pipelineStore, 
    pipelineActions, 
    filteredLogs, 
    safeOutputDisplay
  } from '$lib/stores/pipelineStore';
  import { 
    websocketStore, 
    websocketActions
  } from '$lib/stores/websocketStore';
  import { 
    apiStore, 
    initializeAuth
  } from '$lib/stores/apiStore';
  
  // Services
  import { PipelineApiService } from '$lib/services/pipelineApiService';
  
  // Components
  import PipelineControls from '$lib/components/PipelineControls.svelte';
  import RunProgress from '$lib/components/RunProgress.svelte';
  import OutputResults from '$lib/components/OutputResults.svelte';
  import LiveLogs from '$lib/components/LiveLogs.svelte';
  import RunHistory from '$lib/components/RunHistory.svelte';
  import ArtifactsList from '$lib/components/ArtifactsList.svelte';
  import PipelineModal from '$lib/components/PipelineModal.svelte';
  
  // Utilities
  import { validateJson, debounce, safeJsonStringify } from '$lib/utils/pipelineUtils';
  import type { RunHistoryItem, RunInfo, Artifact, RunStep, RunOptions } from '$lib/types';

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";
  
  let apiService: PipelineApiService;
  let elapsedTimer: ReturnType<typeof setInterval> | null = null;
  let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;
  
  // Modal state
  let showModal = false;
  let modalTitle = '';
  let modalData: unknown = null;
  let modalLoading = false;
  
  // Auto-refresh management
  const MIN_REFRESH_INTERVAL = 2000;
  let pendingRefresh = false;
  
  // Reactive subscriptions
  $: pipeline = $pipelineStore;
  $: websocket = $websocketStore;
  $: api = $apiStore;
  $: logs = $filteredLogs;
  $: outputDisplay = $safeOutputDisplay;

  onMount(async () => {
    if (!browser) return;
    
    try {
      // Initialize authentication and API service
      await initializeAuth();
      apiService = new PipelineApiService(API_BASE);
      
      // Set up WebSocket handlers
      websocketActions.setHandlers({
        onMessage: handleWebSocketMessage,
        onLog: addLog
      });
      
      // Load initial data
      await loadInitialData();
      
      // Connect WebSocket
      if (api.token) {
        websocketActions.connect(API_BASE, api.token);
      }
      
      addLog('info', 'Pipeline dashboard initialized');
    } catch (error) {
      console.error('Failed to initialize pipeline dashboard:', error);
      addLog('error', `Initialization failed: ${error}`);
    }
  });
  
  onDestroy(() => {
    // Clean up timers and connections
    stopElapsedTimer();
    stopAutoRefresh();
    websocketActions.disconnect();
  });

  /**
   * Load initial application data
   */
  async function loadInitialData() {
    try {
      const [stepsResult, artifactsResult, historyResult] = await Promise.allSettled([
        apiService.loadSteps(),
        apiService.loadArtifacts(),
        apiService.loadRunHistory()
      ]);

      if (stepsResult.status === 'fulfilled') {
        pipelineActions.setSteps(stepsResult.value);
      } else {
        console.error('Failed to load steps:', stepsResult.reason);
        addLog('error', 'Failed to load pipeline steps');
      }

      if (artifactsResult.status === 'fulfilled') {
        pipelineActions.setArtifacts(artifactsResult.value);
      } else {
        console.error('Failed to load artifacts:', artifactsResult.reason);
        addLog('warning', 'Failed to load artifacts');
      }

      if (historyResult.status === 'fulfilled') {
        pipelineActions.setRunHistory(historyResult.value);
      } else {
        console.error('Failed to load run history:', historyResult.reason);
        addLog('warning', 'Failed to load run history');
      }
    } catch (error) {
      console.error('Failed to load initial data:', error);
      addLog('error', 'Failed to load initial data');
    }
  }

  /**
   * Debounced refresh function
   */
  const debouncedRefresh = debounce(async () => {
    if (pendingRefresh) return;

    const now = Date.now();
    const timeSinceLastRefresh = now - pipeline.lastRefreshTime;

    if (timeSinceLastRefresh < MIN_REFRESH_INTERVAL) return;

    pendingRefresh = true;
    pipelineActions.setRefreshing(true);

    try {
      const [historyResult, artifactsResult] = await Promise.allSettled([
        apiService.loadRunHistory(),
        apiService.loadArtifacts()
      ]);

      if (historyResult.status === 'fulfilled') {
        pipelineActions.setRunHistory(historyResult.value);
        
        // Update selected run if it exists
        if (pipeline.selectedRun && pipeline.selectedRunId) {
          const updatedRun = historyResult.value.find(r => r.run_id === pipeline.selectedRunId);
          if (updatedRun) {
            pipelineActions.setSelectedRun(updatedRun, pipeline.selectedRunId);
          }
        }
      }

      if (artifactsResult.status === 'fulfilled') {
        pipelineActions.setArtifacts(artifactsResult.value);
      }
    } catch (error) {
      console.error('Debounced refresh failed:', error);
    } finally {
      pendingRefresh = false;
      pipelineActions.setRefreshing(false);
    }
  }, 1000);

  /**
   * Start auto-refresh for active runs
   */
  function startAutoRefresh() {
    if (autoRefreshTimer) return;

    autoRefreshTimer = setInterval(async () => {
      if (pipeline.isExecuting || (pipeline.selectedRun && pipeline.selectedRun.status === "running")) {
        await debouncedRefresh();
      }
    }, 5000);
  }

  /**
   * Stop auto-refresh
   */
  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }

  /**
   * Start elapsed time timer
   */
  function startElapsedTimer() {
    elapsedTimer = setInterval(() => {
      if (pipeline.runStartTime) {
        const elapsed = Math.floor((Date.now() - pipeline.runStartTime) / 1000);
        pipelineActions.updateElapsedTime(elapsed);
      }
    }, 1000);
  }

  /**
   * Stop elapsed time timer
   */
  function stopElapsedTimer() {
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  /**
   * Add log entry
   */
  function addLog(level: string, message: string, timestamp?: string, run_id?: string) {
    pipelineActions.addLog({
      level,
      message,
      timestamp: timestamp || new Date().toISOString(),
      run_id,
    });
  }

  /**
   * Handle WebSocket messages
   */
  function handleWebSocketMessage(data: any) {
    switch (data.type) {
      case "run_started":
        handleRunStarted(data);
        break;
      case "run_progress":
        handleRunProgress(data);
        break;
      case "run_completed":
        handleRunCompleted(data);
        break;
      case "run_failed":
        handleRunFailed(data);
        break;
      case "run_status":
        // Handle additional run status updates
        break;
    }
  }

  function handleRunStarted(data: { run_id: string; step: string }) {
    pipelineActions.setCurrentRun(data.run_id, data.step);
    pipelineActions.setRunStatus('running');
    pipelineActions.updateRunProgress(0, 'Initializing...');
    pipelineActions.updateStepStatus(data.step, 'running');
    startAutoRefresh();
  }

  function handleRunProgress(data: { progress?: number; message?: string }) {
    pipelineActions.updateRunProgress(
      data.progress ?? pipeline.progress,
      data.message ?? pipeline.progressMessage
    );
  }

  function handleRunCompleted(data: { result?: unknown; artifact_id?: string; duration_ms?: number }) {
    pipelineActions.setRunStatus('completed');
    pipelineActions.updateRunProgress(100, 'Completed successfully');
    pipelineActions.setExecutionState(false);

    if (pipeline.currentStep) {
      pipelineActions.updateStepStatus(pipeline.currentStep, 'completed', {
        artifact_id: data.artifact_id,
        duration_ms: data.duration_ms,
      });
      pipelineActions.setCurrentRun(pipeline.currentRunId, null);
    }

    if (data.result !== undefined) {
      pipelineActions.setOutput(data.result);
    }

    stopAutoRefresh();
    debouncedRefresh();
  }

  function handleRunFailed(data: { error?: string }) {
    pipelineActions.setRunStatus('failed');
    pipelineActions.setExecutionState(false);
    
    if (pipeline.currentStep) {
      pipelineActions.updateStepStatus(pipeline.currentStep, 'failed');
      pipelineActions.setCurrentRun(pipeline.currentRunId, null);
    }
    
    addLog('error', `Run failed: ${data.error || 'Unknown error'}`);
    stopAutoRefresh();
    debouncedRefresh();
  }

  // Event handlers for components
  async function handleNewRun() {
    pipelineActions.setSelectedRun(null, '');
    pipelineActions.setInputJson('{\n  "race_id": "mo-senate-2024"\n}');
    pipelineActions.setStepRange(pipeline.steps[0] || '', pipeline.steps[pipeline.steps.length - 1] || '');
  }

  async function handleRunSelect(event: CustomEvent<{ target: { value: string } }>) {
    const runId = event.detail.target.value;
    pipelineActions.setSelectedRun(null, runId);
    
    const run = pipeline.runHistory.find((r) => r.run_id === runId);
    if (run) {
      await selectRun(run);
    }
  }

  async function selectRun(run: RunHistoryItem) {
    try {
      const runData = await apiService.getRunDetails(run.run_id);
      const stepsData: RunStep[] = runData.steps || [];
      const stepName = stepsData[stepsData.length - 1]?.name || '';

      const selectedRunData = {
        ...(runData as any),
        display_id: (run as any).display_id,
        updated_at: (runData as any).completed_at ?? (runData as any).started_at,
        step: stepName,
        steps: stepsData,
      } as RunHistoryItem;

      pipelineActions.setSelectedRun(selectedRunData, run.run_id);

      const currentStepName = stepsData.find((s) => s.status === 'running')?.name || null;
      pipelineActions.setCurrentRun(pipeline.currentRunId, currentStepName);

      const lastIdx = Math.max(0, pipeline.steps.indexOf(stepName));
      const nextIndex = Math.min(lastIdx + 1, Math.max(0, pipeline.steps.length - 1));
      pipelineActions.setStepRange(
        pipeline.steps[nextIndex] || pipeline.steps[0] || '',
        pipeline.steps[pipeline.steps.length - 1] || ''
      );

      // Load payload data
      await loadRunPayload(runData, stepName);
    } catch (e) {
      console.error('Failed to select run:', e);
      addLog('error', 'Failed to select run');
    }
  }

  async function loadRunPayload(runData: RunInfo, stepName: string) {
    let payload: Record<string, unknown> = (runData as any).payload || {};
    
    if ((runData as any).artifact_id) {
      try {
        const artifact = await apiService.getArtifact((runData as any).artifact_id);
        payload = { ...payload };
        
        // Set payload based on step type
        switch (stepName) {
          case 'step01a_metadata':
            (payload as any).race_json = artifact.output?.race_json || artifact.output;
            break;
          case 'step01b_discovery':
            (payload as any).sources = artifact.output;
            break;
          case 'step01c_fetch':
            (payload as any).raw_content = artifact.output;
            break;
          case 'step01d_extract':
            (payload as any).content = artifact.output;
            break;
        }
      } catch (e) {
        console.error('Failed to load artifact for run', e);
      }
    }

    // Update input JSON safely
    const payloadResult = safeJsonStringify(payload, 100000);
    
    if (payloadResult.truncated) {
      pipelineActions.setInputJson(JSON.stringify({
        _note: 'Payload too large to display in input editor',
        _size: `${(JSON.stringify(payload).length / 1024).toFixed(1)}KB`,
        _artifact_id: (runData as any).artifact_id,
        _step_name: stepName
      }, null, 2));
      addLog('info', `Large payload detected. Using summary in input editor.`);
    } else {
      pipelineActions.setInputJson(payloadResult.content);
    }
  }

  async function handleExecute(event: { detail: { mode: 'single' | 'range'; startStep: string; endStep: string } }) {
    const { mode, startStep, endStep } = event.detail;
    
    if (pipeline.isExecuting) return;

    if (!websocket.connected) {
      websocketActions.connect(API_BASE, api.token);
    }

    pipelineActions.setExecutionState(true);
    pipelineActions.setOutput(null);
    startElapsedTimer();

    try {
      if (pipeline.selectedRun) {
        await continueExistingRun(mode, startStep, endStep);
      } else {
        await startNewRun(startStep);
      }
    } catch (err) {
      console.error('Execution failed:', err);
      pipelineActions.setOutput({ error: String(err) });
      addLog('error', `Execution failed: ${err}`);
      pipelineActions.setExecutionState(false);
      stopElapsedTimer();
    }
  }

  async function continueExistingRun(mode: 'single' | 'range', startStep: string, endStep: string) {
    const validation = validateJson(pipeline.inputJson || '{}');
    if (!validation.valid) {
      throw new Error(`Invalid JSON in input: ${validation.error}`);
    }

    pipelineActions.setCurrentRun(pipeline.selectedRun!.run_id);

    // Handle truncated artifacts
    if (validation.data && (validation.data as any)._truncated && (validation.data as any)._artifact_id) {
      addLog('info', `Loading full artifact data for execution (artifact: ${(validation.data as any)._artifact_id})`);
    }

    const stepsToRun = mode === 'single' ? [startStep] : pipeline.steps.slice(
      Math.max(0, pipeline.steps.indexOf(startStep)),
      pipeline.steps.indexOf(endStep) + 1
    );

    const result = await apiService.continueRun(pipeline.selectedRun!.run_id, stepsToRun, validation.data);
    pipelineActions.setOutput(result);

    const resultJson = safeJsonStringify(result.state ?? {}, 100000);
    if (resultJson.truncated) {
      pipelineActions.setInputJson(JSON.stringify({
        _note: 'Result too large to display',
        _size: JSON.stringify(result.state ?? {}).length
      }, null, 2));
    } else {
      pipelineActions.setInputJson(resultJson.content);
    }

    const last = result.runs?.[result.runs.length - 1];
    if (last) {
      pipelineActions.setSelectedRun(pipeline.selectedRun, last.run_id);
    }

    await debouncedRefresh();
  }

  async function startNewRun(stepName: string) {
    const validation = validateJson(pipeline.inputJson || '{}');
    if (!validation.valid) {
      throw new Error(`Invalid JSON in input: ${validation.error}`);
    }

    const options: RunOptions = {
      skip_cloud_services: !pipeline.useCloudStorage || undefined,
      save_artifact: true,
    };

    const result = await apiService.executeStep(stepName, validation.data, options);
    pipelineActions.setCurrentRun(result.run_id);
    addLog('info', `Started execution: ${stepName}`);

    await debouncedRefresh();
    
    const runId = result.meta?.run_id || result.run_id;
    const run = pipeline.runHistory.find((r) => r.run_id === runId);
    if (run) {
      await selectRun(run);
    }
    pipelineActions.setSelectedRun(pipeline.selectedRun, runId);
  }

  function handleStopExecution() {
    if (pipeline.currentRunId && websocket.ws && websocket.ws.readyState === WebSocket.OPEN) {
      websocketActions.send({
        type: 'stop_run',
        run_id: pipeline.currentRunId,
      });
    }
    pipelineActions.setExecutionState(false);
    stopElapsedTimer();
  }

  function handleInputChange(event: { detail: string }) {
    pipelineActions.setInputJson(event.detail);
  }

  function handleCloudStorageChange(event: { detail: boolean }) {
    pipelineStore.update(state => ({ ...state, useCloudStorage: event.detail }));
  }

  function handleExecutionModeChange(event: { detail: 'single' | 'range' }) {
    pipelineActions.setExecutionMode(event.detail);
  }

  function handleStepRangeChange(event: { detail: { start: string; end: string } }) {
    pipelineActions.setStepRange(event.detail.start, event.detail.end);
  }

  async function handleSetStartStep(event: { detail: string }) {
    const stepName = event.detail;
    pipelineActions.setStepRange(stepName, pipeline.endStep);

    // Update input JSON based on the selected step's prerequisites
    if (pipeline.selectedRun && pipeline.selectedRun.steps) {
      await updateInputForStep(stepName);
    }
  }

  async function updateInputForStep(stepName: string) {
    const stepIndex = pipeline.selectedRun!.steps.findIndex(s => s.name === stepName);
    if (stepIndex <= 0) {
      // If it's the first step, use the original payload
      try {
        const originalPayload = (pipeline.selectedRun as any).payload || {};
        pipelineActions.setInputJson(JSON.stringify(originalPayload, null, 2));
      } catch (error) {
        console.error('Failed to serialize original payload:', error);
        addLog('error', 'Failed to serialize original payload');
      }
      return;
    }

    // Find the previous step that has an artifact
    for (let i = stepIndex - 1; i >= 0; i--) {
      const prevStep = pipeline.selectedRun!.steps[i];
      if (prevStep.artifact_id) {
        try {
          const artifact = await apiService.getArtifact(prevStep.artifact_id);
          const payloadResult = safeJsonStringify(artifact.output, 50000);
          
          if (payloadResult.truncated) {
            const summaryPayload = {
              _note: `Large artifact detected. Artifact will be loaded automatically during execution.`,
              _artifact_id: prevStep.artifact_id,
              _step_name: prevStep.name,
              _truncated: true
            };
            pipelineActions.setInputJson(JSON.stringify(summaryPayload, null, 2));
            addLog('info', `Large artifact detected for ${prevStep.name}. Input JSON shows summary only.`);
          } else {
            let payload: Record<string, unknown> = {};
            
            // Set up the payload based on what this step needs
            switch (stepName) {
              case 'step01b_discovery':
                payload.race_json = artifact.output?.race_json || artifact.output;
                break;
              case 'step01c_fetch':
                payload.sources = artifact.output;
                break;
              case 'step01d_extract':
                payload.raw_content = artifact.output;
                break;
              case 'step02a_analyze':
                payload.content = artifact.output;
                break;
              default:
                payload = artifact.output || {};
            }
            
            pipelineActions.setInputJson(JSON.stringify(payload, null, 2));
          }
          break;
        } catch (e) {
          console.error('Failed to load artifact for step setup', e);
          addLog('error', `Failed to load artifact for step setup: ${e}`);
        }
      }
    }
  }

  function handleUseAsInput() {
    if (!pipeline.output) return;

    try {
      const next = (pipeline.output as any)?.output ?? pipeline.output;
      const result = safeJsonStringify(next, 100000);
      
      if (result.truncated) {
        addLog('warning', 'Output too large for input field. Using summary.');
        pipelineActions.setInputJson(JSON.stringify({
          _note: 'Output too large to display in input. Will be handled automatically.',
          _size: `${(JSON.stringify(next).length / 1024).toFixed(1)}KB`
        }, null, 2));
      } else {
        pipelineActions.setInputJson(result.content);
      }
    } catch (error) {
      console.error('Failed to convert output to input:', error);
      addLog('error', 'Failed to convert output to input JSON');
    }
  }

  function handleLogFilterChange(event: { detail: 'all' | 'debug' | 'info' | 'warning' | 'error' }) {
    pipelineActions.setLogFilter(event.detail);
  }

  function handleClearLogs() {
    pipelineActions.clearLogs();
  }

  async function handleArtifactClick(event: { detail: Artifact }) {
    const artifact = event.detail;
    modalLoading = true;
    showModal = true;
    modalTitle = 'Artifact Details';
    modalData = null;
    
    try {
      const artifactId = artifact.id || (artifact as any).artifact_id || (artifact as any)._id;
      if (artifactId) {
        modalData = await apiService.getArtifact(artifactId);
      } else {
        modalData = artifact;
      }
    } catch (e) {
      modalData = { error: String(e), ...artifact };
    }
    modalLoading = false;
  }

  async function handleRunDetails(event: { detail: RunHistoryItem }) {
    const run = event.detail;
    modalLoading = true;
    showModal = true;
    modalTitle = 'Run Details';
    modalData = null;
    
    try {
      const runId = run.run_id;
      if (runId) {
        modalData = await apiService.getRunDetails(runId);
      } else {
        modalData = run;
      }
    } catch (e) {
      modalData = { error: String(e), ...run };
    }
    modalLoading = false;
  }

  function closeModal() {
    showModal = false;
    modalData = null;
    modalTitle = '';
    modalLoading = false;
  }

  // Modal data safety check
  $: modalDataTooLarge = (() => {
    if (!modalData) return false;
    try {
      const jsonString = JSON.stringify(modalData, null, 2);
      return jsonString.length > 200000; // 200KB threshold for modal
    } catch {
      return true;
    }
  }

  async function handleSetStartStep(stepName: string) {
    startStep = stepName;

    // Update input JSON based on the selected step's prerequisites
    if (selectedRun && selectedRun.steps) {
      const stepIndex = selectedRun.steps.findIndex(s => s.name === stepName);
      if (stepIndex > 0) {
        // Find the previous step that has an artifact
        for (let i = stepIndex - 1; i >= 0; i--) {
          const prevStep = selectedRun.steps[i];
          if (prevStep.artifact_id) {
            try {
              const artRes = await fetchWithAuth(`${API_BASE}/artifact/${prevStep.artifact_id}`, {}, 20000); // 20 second timeout for artifacts
              if (artRes.ok) {
                const artifact = await artRes.json();
                let payload: Record<string, unknown> = {};

                // Check if the artifact output is too large
                let artifactString: string;
                try {
                  artifactString = JSON.stringify(artifact.output);
                } catch (stringifyError) {
                  console.warn("Artifact too complex to stringify:", stringifyError);
                  payload = {
                    _note: `Artifact too complex to serialize. Will be loaded automatically during execution.`,
                    _artifact_id: prevStep.artifact_id,
                    _step_name: prevStep.name,
                    _truncated: true,
                    _error: "Serialization failed"
                  };
                  inputJson = JSON.stringify(payload, null, 2);
                  addLog("warning", `Artifact for ${prevStep.name} too complex to display. Using reference.`);
                  break;
                }

                const maxSize = 50000; // 50KB limit for JSON editor

                if (artifactString.length > maxSize) {
                  // For large artifacts, create a summary or reference
                  payload = {
                    _note: `Large artifact detected (${(artifactString.length / 1024).toFixed(1)}KB). Artifact will be loaded automatically during execution.`,
                    _artifact_id: prevStep.artifact_id,
                    _step_name: prevStep.name,
                    _truncated: true
                  };

                  // Add a small sample for some step types
                  try {
                    switch (stepName) {
                      case "step01b_discovery":
                        if (artifact.output?.race_json) {
                          payload.race_json = artifact.output.race_json;
                        }
                        break;
                      case "step01c_fetch":
                        if (artifact.output?.type === "content_collection_refs") {
                          // Handle reference collection from step01c_fetch
                          payload.references_summary = {
                            type: artifact.output.type,
                            count: artifact.output.count,
                            race_id: artifact.output.race_id
                          };
                          payload.total_sources = artifact.output.count;
                        } else if (Array.isArray(artifact.output) && artifact.output.length > 0) {
                          payload.sources_sample = artifact.output.slice(0, 2); // First 2 sources
                          payload.total_sources = artifact.output.length;
                        }
                        break;
                      case "step01d_extract":
                        if (artifact.output?.type === "content_collection_refs") {
                          // Handle reference collection from step01d_extract
                          payload.references_summary = {
                            type: artifact.output.type,
                            count: artifact.output.count,
                            race_id: artifact.output.race_id
                          };
                          payload.total_items = artifact.output.count;
                        } else if (Array.isArray(artifact.output) && artifact.output.length > 0) {
                          payload.content_sample = artifact.output.slice(0, 1); // First content item
                          payload.total_items = artifact.output.length;
                        }
                        break;
                    }
                  } catch (sampleError) {
                    console.warn("Failed to create sample from artifact:", sampleError);
                  }
                } else {
                  // Set up the payload based on what this step needs (normal size)
                  try {
                    switch (stepName) {
                      case "step01b_discovery":
                        payload.race_json = artifact.output?.race_json || artifact.output;
                        break;
                      case "step01c_fetch":
                        payload.sources = artifact.output;
                        break;
                      case "step01d_extract":
                        payload.raw_content = artifact.output;
                        break;
                      case "step02a_analyze":
                        payload.content = artifact.output;
                        break;
                      default:
                        // For other steps, use the artifact output directly
                        payload = artifact.output || {};
                    }
                  } catch (payloadError) {
                    console.warn("Failed to set up payload:", payloadError);
                    payload = {
                      _note: "Failed to process artifact output",
                      _artifact_id: prevStep.artifact_id,
                      _step_name: prevStep.name,
                      _error: String(payloadError)
                    };
                  }
                }

                try {
                  inputJson = JSON.stringify(payload, null, 2);

                  // Add a log message if we truncated the data
                  if (artifactString.length > maxSize) {
                    addLog("info", `Large artifact detected for ${prevStep.name}. Input JSON shows summary only. Full data will be loaded during execution.`);
                  }
                } catch (finalStringifyError) {
                  console.error("Failed to stringify final payload:", finalStringifyError);
                  inputJson = JSON.stringify({
                    _note: "Failed to serialize payload",
                    _artifact_id: prevStep.artifact_id,
                    _error: String(finalStringifyError)
                  }, null, 2);
                  addLog("error", "Failed to serialize payload for input editor");
                }

  $: safeModalDisplay = (() => {
    if (!modalData) return '';
    const result = safeJsonStringify(modalData, 200000);
    return result.content;
  })();
</script>

<svelte:head>
  <title>Pipeline Dashboard - SmarterVote</title>
</svelte:head>

<div class="container mx-auto px-4 py-6 max-w-7xl">
  <!-- Header -->
  <div class="mt-2 mb-6 card p-4">
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-4">
        <h1 class="text-xl font-bold text-gray-900">Pipeline Dashboard</h1>
        <div class="text-sm text-gray-500">
          Advanced pipeline execution and monitoring
        </div>
      </div>
      <div class="flex items-center space-x-2">
        <div class="w-3 h-3 rounded-full {websocket.connected ? 'bg-green-500' : 'bg-red-500'}" />
        <span class="text-sm text-gray-600">
          {websocket.connected ? 'Connected' : 'Disconnected'}
        </span>
        {#if pipeline.isRefreshing}
          <div class="flex items-center space-x-1">
            <svg class="animate-spin h-3 w-3 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span class="text-xs text-blue-600">Refreshing...</span>
          </div>
        {/if}
      </div>
    </div>
  </div>

  <div class="dashboard-grid">
    <!-- Left Panel: Controls & Progress -->
    <div class="space-y-6">
      <!-- Pipeline Controls -->
      <PipelineControls
        steps={pipeline.steps}
        inputJson={pipeline.inputJson}
        useCloudStorage={pipeline.useCloudStorage}
        executionMode={pipeline.executionMode}
        startStep={pipeline.startStep}
        endStep={pipeline.endStep}
        selectedRun={pipeline.selectedRun}
        selectedRunId={pipeline.selectedRunId}
        runHistory={pipeline.runHistory}
        isExecuting={pipeline.isExecuting}
        currentStep={pipeline.currentStep}
        {API_BASE}
        on:new-run={handleNewRun}
        on:run-select={handleRunSelect}
        on:input-change={handleInputChange}
        on:cloud-storage-change={handleCloudStorageChange}
        on:execution-mode-change={handleExecutionModeChange}
        on:step-range-change={handleStepRangeChange}
        on:execute={handleExecute}
        on:set-start-step={handleSetStartStep}
      />

      <!-- Run Progress -->
      <RunProgress
        isExecuting={pipeline.isExecuting}
        runStatus={pipeline.runStatus}
        progress={pipeline.progress}
        progressMessage={pipeline.progressMessage}
        elapsedTime={pipeline.elapsedTime}
        currentRunId={pipeline.currentRunId}
        errorCount={logs.filter(l => l.level === 'error').length}
        on:stop-execution={handleStopExecution}
      />

      <!-- Output Results -->
      <OutputResults
        output={pipeline.output}
        onAddLog={addLog}
        on:use-as-input={handleUseAsInput}
      />
    </div>

    <!-- Right Panel: Logs & History -->
    <div class="space-y-6">
      <!-- Live Logs -->
      <LiveLogs
        {logs}
        logFilter={pipeline.logFilter}
        connected={websocket.connected}
        on:filter-change={handleLogFilterChange}
        on:clear-logs={handleClearLogs}
      />

      <!-- Run History -->
      <RunHistory
        runHistory={pipeline.runHistory}
        selectedRunId={pipeline.selectedRunId}
        isRefreshing={pipeline.isRefreshing}
        on:run-select={({ detail }) => selectRun(detail)}
        on:run-details={handleRunDetails}
        on:refresh={debouncedRefresh}
      />

      <!-- Artifacts -->
      <ArtifactsList
        artifacts={pipeline.artifacts}
        isRefreshing={pipeline.isRefreshing}
        on:artifact-click={handleArtifactClick}
        on:refresh={() => apiService.loadArtifacts().then(artifacts => pipelineActions.setArtifacts(artifacts))}
      />
    </div>
  </div>
</div>

<!-- Modal -->
<PipelineModal
  show={showModal}
  title={modalTitle}
  loading={modalLoading}
  contentTooLarge={modalDataTooLarge}
  on:close={closeModal}
>
  {safeModalDisplay}
</PipelineModal>

<style>
  .dashboard-grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: 1fr 400px;
  }

  @media (max-width: 1024px) {
    .dashboard-grid {
      grid-template-columns: 1fr;
    }
  }
</style>