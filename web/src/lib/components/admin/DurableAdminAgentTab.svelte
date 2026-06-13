<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import {
    PipelineApiService,
    type AdminAgentConversation,
    type AdminAgentTask,
  } from "$lib/services/pipelineApiService";

  export let apiService: PipelineApiService;

  const STORAGE_KEY = "smartervote-admin-agent-conversation";
  const ACTIVE_STATUSES = new Set(["queued", "running"]);

  let data: AdminAgentConversation | null = null;
  let conversations: AdminAgentConversation["conversation"][] = [];
  let isDeletingConversationId: string | null = null;
  let input = "";
  let loading = true;
  let sending = false;
  let actionPending = false;
  let error = "";
  let timer: ReturnType<typeof setInterval> | null = null;
  let messagesElement: HTMLDivElement;

  $: latestTask = data?.tasks?.[0] ?? null;
  $: isActive = !!latestTask && ACTIVE_STATUSES.has(latestTask.status);
  $: waitingApproval = latestTask?.status === "waiting_approval";

  onMount(async () => {
    await loadConversations();
    await initialize();
    timer = setInterval(() => {
      if (!document.hidden && (isActive || waitingApproval)) void refresh(false);
    }, 2000);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  async function loadConversations() {
    if (!apiService || typeof apiService.listAdminAgentConversations !== "function") {
      conversations = [];
      return;
    }
    try {
      conversations = await apiService.listAdminAgentConversations();
    } catch (e) {
      console.error("Failed to load conversations:", e);
    }
  }

  export async function initialize() {
    loading = true;
    error = "";
    try {
      let conversationId = localStorage.getItem(STORAGE_KEY);
      if (conversationId) {
        try {
          data = await apiService.getAdminAgentConversation(conversationId);
        } catch (e) {
          localStorage.removeItem(STORAGE_KEY);
          conversationId = null;
        }
      }
      if (!conversationId) {
        if (conversations.length > 0) {
          conversationId = conversations[0].conversation_id;
          localStorage.setItem(STORAGE_KEY, conversationId);
          data = await apiService.getAdminAgentConversation(conversationId);
        } else {
          const conversation = await apiService.createAdminAgentConversation();
          localStorage.setItem(STORAGE_KEY, conversation.conversation_id);
          data = { conversation, messages: [], tasks: [] };
          await loadConversations();
        }
      }
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
      await scrollToBottom();
    }
  }

  async function refresh(scroll = true) {
    if (!data) return;
    try {
      data = await apiService.getAdminAgentConversation(data.conversation.conversation_id);
      error = "";
      if (scroll) await scrollToBottom();
    } catch (e) {
      error = String(e);
    }
  }

  async function selectConversation(id: string) {
    if (isActive || waitingApproval) {
      if (!confirm("There is an active task running. Switch anyway?")) {
        return;
      }
    }
    loading = true;
    error = "";
    try {
      localStorage.setItem(STORAGE_KEY, id);
      data = await apiService.getAdminAgentConversation(id);
      await scrollToBottom();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function deleteConversation(id: string, event: Event) {
    event.stopPropagation();
    if (!confirm("Are you sure you want to delete this conversation?")) {
      return;
    }
    isDeletingConversationId = id;
    try {
      if (apiService && typeof apiService.deleteAdminAgentConversation === "function") {
        await apiService.deleteAdminAgentConversation(id);
      }
      const activeId = data?.conversation.conversation_id;
      await loadConversations();
      if (activeId === id) {
        localStorage.removeItem(STORAGE_KEY);
        data = null;
        await initialize();
      }
    } catch (e) {
      error = "Failed to delete conversation: " + e;
    } finally {
      isDeletingConversationId = null;
    }
  }

  async function handleNewConversation() {
    if (isActive || waitingApproval) {
      if (!confirm("There is an active task running. Switch anyway?")) {
        return;
      }
    }
    loading = true;
    error = "";
    try {
      const conversation = await apiService.createAdminAgentConversation();
      localStorage.setItem(STORAGE_KEY, conversation.conversation_id);
      data = { conversation, messages: [], tasks: [] };
      await loadConversations();
      await scrollToBottom();
    } catch (e) {
      error = "Failed to create conversation: " + e;
    } finally {
      loading = false;
    }
  }

  async function send() {
    const content = input.trim();
    if (!data || !content || sending || isActive || waitingApproval) return;
    sending = true;
    error = "";
    input = "";
    try {
      await apiService.submitAdminAgentMessage(data.conversation.conversation_id, content);
      await refresh();
    } catch (e) {
      error = String(e);
      input = content;
    } finally {
      sending = false;
    }
  }

  async function approve(task: AdminAgentTask) {
    actionPending = true;
    error = "";
    try {
      await apiService.approveAdminAgentTask(task.task_id);
      await refresh();
    } catch (e) {
      error = String(e);
    } finally {
      actionPending = false;
    }
  }

  async function cancel(task: AdminAgentTask): Promise<boolean> {
    actionPending = true;
    error = "";
    try {
      await apiService.cancelAdminAgentTask(task.task_id);
      await refresh();
      return true;
    } catch (e) {
      error = String(e);
      return false;
    } finally {
      actionPending = false;
    }
  }

  async function applySuggestion(text: string) {
    if (sending || isActive || waitingApproval) return;
    input = text;
    await send();
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  async function scrollToBottom() {
    await tick();
    if (messagesElement) messagesElement.scrollTop = messagesElement.scrollHeight;
  }

  function statusLabel(task: AdminAgentTask | null): string {
    if (!task) return "Ready";
    if (task.status === "waiting_approval") return "Waiting for approval";
    if (task.status === "queued") return "Queued";
    if (task.status === "running") return `Working${task.iteration ? ` - step ${task.iteration}` : ""}`;
    if (task.status === "failed") return "Failed";
    if (task.status === "cancelled") return "Cancelled";
    return "Ready";
  }
</script>

<div class="card h-[calc(100dvh-13rem)] min-h-[540px] flex overflow-hidden bg-surface border border-stroke rounded-xl shadow-lg">
  <!-- Sidebar -->
  <div class="w-64 border-r border-stroke flex flex-col bg-surface-alt/40 dark:bg-surface-alt/10">
    <div class="p-3 border-b border-stroke flex items-center justify-between">
      <span class="text-xs font-semibold uppercase tracking-wider text-content-subtle">Conversations</span>
      <button
        type="button"
        class="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium px-2 py-1 rounded hover:bg-blue-50 dark:hover:bg-blue-950/20 transition-all duration-200"
        on:click={handleNewConversation}
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        New Chat
      </button>
    </div>
    <div class="flex-1 overflow-y-auto p-2 space-y-1">
      {#each conversations as conv (conv.conversation_id)}
        <button
          type="button"
          class="w-full text-left px-3 py-2.5 rounded-lg flex items-center justify-between gap-2 transition-all duration-200 group relative
            {data?.conversation.conversation_id === conv.conversation_id
              ? 'bg-blue-50 dark:bg-blue-950/20 border-l-4 border-blue-500 text-blue-900 dark:text-blue-200 font-medium shadow-sm'
              : 'hover:bg-surface-alt/60 text-content-subtle hover:text-content'}"
          on:click={() => selectConversation(conv.conversation_id)}
        >
          <div class="flex items-center gap-2 min-w-0 flex-1">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 shrink-0 {data?.conversation.conversation_id === conv.conversation_id ? 'text-blue-500' : 'text-content-faint'}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <span class="truncate text-sm">{conv.title || 'Conversation'}</span>
          </div>

          <button
            type="button"
            class="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50 dark:hover:bg-red-950/40 text-red-500 transition-opacity duration-200 shrink-0"
            on:click={(e) => deleteConversation(conv.conversation_id, e)}
            disabled={isDeletingConversationId === conv.conversation_id}
            title="Delete conversation"
          >
            {#if isDeletingConversationId === conv.conversation_id}
              <svg class="animate-spin h-3.5 w-3.5 text-red-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            {:else}
              <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            {/if}
          </button>
        </button>
      {/each}
    </div>
  </div>

  <!-- Main Chat Pane -->
  <div class="flex-1 flex flex-col bg-surface overflow-hidden">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-stroke flex items-center justify-between gap-3 bg-surface-alt/10">
      <div>
        <h2 class="text-sm font-semibold text-content flex items-center gap-2">
          {data?.conversation.title || 'New Admin Conversation'}
        </h2>
        <p class="text-xs text-content-subtle flex items-center gap-1.5 mt-0.5">
          {#if isActive}
            <span class="relative flex h-2 w-2">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
          {:else if waitingApproval}
            <span class="relative flex h-2 w-2">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
            </span>
          {/if}
          {statusLabel(latestTask)}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium px-2 py-1 rounded hover:bg-blue-50 dark:hover:bg-blue-950/20 transition-all duration-200"
          type="button"
          on:click={() => refresh(false)}
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H17" />
          </svg>
          Refresh
        </button>
      </div>
    </div>

    <!-- Messages Container -->
    <div bind:this={messagesElement} class="flex-1 overflow-y-auto p-4 space-y-4 bg-surface-alt/10">
      {#if loading}
        <div class="flex flex-col items-center justify-center h-full space-y-2 py-12">
          <svg class="animate-spin h-8 w-8 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <p class="text-sm text-content-subtle font-medium">Loading conversation...</p>
        </div>
      {:else if !data || data.messages.length === 0}
        <div class="max-w-xl mx-auto text-center py-16 px-4 flex flex-col items-center justify-center h-full">
          <div class="h-16 w-16 bg-blue-50 dark:bg-blue-950/20 rounded-full flex items-center justify-center text-blue-600 mb-4 shadow-inner">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h3 class="text-lg font-bold text-content">SmarterVote AI Admin Agent</h3>
          <p class="mt-2 text-sm text-content-subtle max-w-sm">
            I can inspect state elections, view research drafts, check tasks and logs, publish data changes, or trigger deployments.
          </p>
          <p class="mt-4 text-xs text-content-faint">
            Select a suggestion below to get started.
          </p>
        </div>
      {:else}
        {#each data.messages as message (message.message_id)}
          {#if message.role === "tool"}
            <div class="max-w-4xl mx-auto my-2">
              <details class="group rounded-xl border border-stroke bg-surface-alt/30 dark:bg-surface-alt/5 overflow-hidden transition-all duration-300">
                <summary class="cursor-pointer text-xs font-semibold text-content-subtle px-4 py-2.5 flex items-center justify-between hover:bg-surface-alt/50 transition-colors duration-200">
                  <div class="flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-blue-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <span>Tool executed: <code class="bg-surface border border-stroke px-1.5 py-0.5 rounded text-blue-600 font-mono text-[11px]">{message.tool_name ?? "operation"}</code></span>
                  </div>
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-content-faint transition-transform duration-200 group-open:rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <div class="px-4 pb-3 pt-1 border-t border-stroke/40 bg-surface dark:bg-surface-alt/5">
                  <pre class="text-[11px] text-content-subtle font-mono p-3 bg-surface-alt/60 dark:bg-surface-alt/20 rounded-lg max-h-64 overflow-auto border border-stroke/20 whitespace-pre-wrap break-all shadow-inner">{message.content}</pre>
                </div>
              </details>
            </div>
          {:else}
            <div class="max-w-4xl mx-auto flex {message.role === 'user' ? 'justify-end' : 'justify-start'}">
              <div class="flex gap-2.5 max-w-[85%]">
                {#if message.role !== 'user'}
                  <div class="h-8 w-8 rounded-lg bg-blue-500 flex items-center justify-center text-white shrink-0 shadow-md">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                  </div>
                {/if}
                <div class="rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words shadow-sm border
                  {message.role === 'user'
                    ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-tr-sm border-blue-700 shadow-blue-500/10'
                    : 'bg-surface border-stroke text-content rounded-tl-sm'}"
                >
                  {message.content || (message.metadata?.tool_calls ? "Executing operation..." : "")}
                </div>
              </div>
            </div>
          {/if}
        {/each}
      {/if}

      {#if isActive}
        <div class="max-w-4xl mx-auto flex items-center gap-3 text-xs text-blue-600 dark:text-blue-400 pl-10">
          <div class="flex space-x-1 items-center">
            <span class="h-1.5 w-1.5 rounded-full bg-blue-500 animate-bounce" style="animation-delay: 0ms"></span>
            <span class="h-1.5 w-1.5 rounded-full bg-blue-500 animate-bounce" style="animation-delay: 150ms"></span>
            <span class="h-1.5 w-1.5 rounded-full bg-blue-500 animate-bounce" style="animation-delay: 300ms"></span>
          </div>
          <span class="font-medium">{statusLabel(latestTask)}...</span>
        </div>
      {/if}

      {#if waitingApproval && latestTask}
        <div class="max-w-4xl mx-auto rounded-xl border border-amber-300 bg-amber-50/50 dark:border-amber-900/40 dark:bg-amber-950/20 p-4 shadow-sm pl-10 relative">
          <div class="absolute left-3 top-4 text-amber-600">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <p class="text-sm font-bold text-amber-900 dark:text-amber-200">Approval Required</p>
          <p class="mt-1 text-sm text-amber-800 dark:text-amber-300">
            {latestTask.approval_summary ?? "The agent requested approval for a protected operation."}
          </p>
          {#if latestTask.pending_tool_call}
            <div class="mt-2 text-xs font-mono bg-amber-100/40 dark:bg-amber-950/40 p-2.5 rounded border border-amber-200/50 dark:border-amber-900/20 max-h-36 overflow-auto">
              <span class="font-bold text-amber-950 dark:text-amber-100">Tool:</span> {latestTask.pending_tool_call.name}<br/>
              <span class="font-bold text-amber-950 dark:text-amber-100">Args:</span> {JSON.stringify(latestTask.pending_tool_call.arguments, null, 2)}
            </div>
          {/if}
          <div class="mt-3 flex gap-2">
            <button
              type="button"
              class="px-4 py-1.5 text-xs font-semibold rounded-lg bg-amber-600 hover:bg-amber-700 text-white shadow transition-colors duration-200 disabled:opacity-50"
              disabled={actionPending}
              on:click={() => approve(latestTask)}
            >
              Approve Execution
            </button>
            <button
              type="button"
              class="px-4 py-1.5 text-xs font-semibold rounded-lg border border-stroke text-content hover:bg-surface-alt transition-colors duration-200 disabled:opacity-50 bg-surface"
              disabled={actionPending}
              on:click={() => cancel(latestTask)}
            >
              Reject / Cancel
            </button>
          </div>
        </div>
      {/if}
    </div>

    {#if error}
      <div class="px-4 py-2.5 text-xs text-red-600 dark:text-red-400 border-t border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-900/30 flex items-center gap-2">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>{error}</span>
      </div>
    {/if}

    <!-- Suggestions and Input Area -->
    <div class="p-3 border-t border-stroke bg-surface-alt/25 dark:bg-surface-alt/5 flex flex-col gap-2">
      <!-- Suggestion chips -->
      {#if !sending && !isActive && !waitingApproval}
        <div class="flex flex-wrap gap-1.5 pb-1 max-w-4xl mx-auto w-full">
          <button
            type="button"
            class="text-[11px] font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/20 hover:bg-blue-100 dark:hover:bg-blue-900/30 border border-blue-200/40 dark:border-blue-900/40 rounded-full px-2.5 py-1 transition-all duration-200"
            on:click={() => applySuggestion("Check pipeline status")}
          >
            Check pipeline status
          </button>
          <button
            type="button"
            class="text-[11px] font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/20 hover:bg-blue-100 dark:hover:bg-blue-900/30 border border-blue-200/40 dark:border-blue-900/40 rounded-full px-2.5 py-1 transition-all duration-200"
            on:click={() => applySuggestion("List unpublished drafts")}
          >
            List unpublished drafts
          </button>
          <button
            type="button"
            class="text-[11px] font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/20 hover:bg-blue-100 dark:hover:bg-blue-900/30 border border-blue-200/40 dark:border-blue-900/40 rounded-full px-2.5 py-1 transition-all duration-200"
            on:click={() => applySuggestion("Trigger Web Deploy")}
          >
            Trigger Web Deploy
          </button>
        </div>
      {/if}

      <div class="flex items-end gap-2 max-w-4xl mx-auto w-full">
        <textarea
          bind:value={input}
          rows="2"
          on:keydown={handleKeydown}
          disabled={sending || isActive || waitingApproval}
          placeholder={waitingApproval ? "Approve or reject the pending operation above" : isActive ? "Agent is working..." : "Ask the admin agent..."}
          class="flex-1 resize-none rounded-xl border border-stroke bg-surface px-4 py-2.5 text-sm text-content focus:outline-none focus:ring-2 focus:ring-blue-500/30 disabled:opacity-50 transition-all shadow-sm"
        ></textarea>
        <button
          type="button"
          class="btn-primary rounded-xl px-5 py-2.5 text-sm disabled:opacity-50 flex items-center justify-center gap-1.5 h-[42px] shrink-0 font-semibold shadow-md bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 border-none transition-all duration-200"
          disabled={sending || isActive || waitingApproval || !input.trim()}
          on:click={send}
        >
          {#if sending}
            <svg class="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          {:else}
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          {/if}
          Send
        </button>
      </div>
    </div>
  </div>
</div>
