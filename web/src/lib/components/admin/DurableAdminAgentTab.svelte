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
    await initialize();
    timer = setInterval(() => {
      if (!document.hidden && (isActive || waitingApproval)) void refresh(false);
    }, 2000);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

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
        const conversation = await apiService.createAdminAgentConversation();
        localStorage.setItem(STORAGE_KEY, conversation.conversation_id);
        data = { conversation, messages: [], tasks: [] };
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

  async function cancel(task: AdminAgentTask) {
    actionPending = true;
    error = "";
    try {
      await apiService.cancelAdminAgentTask(task.task_id);
      await refresh();
    } catch (e) {
      error = String(e);
    } finally {
      actionPending = false;
    }
  }

  async function newConversation() {
    if (isActive && latestTask) await cancel(latestTask);
    localStorage.removeItem(STORAGE_KEY);
    data = null;
    await initialize();
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

<div class="card h-[calc(100dvh-13rem)] min-h-[540px] flex flex-col overflow-hidden">
  <div class="px-4 py-3 border-b border-stroke flex items-center justify-between gap-3">
    <div>
      <h2 class="text-sm font-semibold text-content">Admin Agent</h2>
      <p class="text-xs text-content-subtle">{statusLabel(latestTask)}</p>
    </div>
    <div class="flex items-center gap-2">
      <button class="text-xs text-blue-600 hover:underline" type="button" on:click={() => refresh(false)}>Refresh</button>
      <button class="text-xs text-content-muted hover:underline" type="button" on:click={newConversation}>New conversation</button>
    </div>
  </div>

  <div bind:this={messagesElement} class="flex-1 overflow-y-auto p-4 space-y-3 bg-surface-alt/30">
    {#if loading}
      <p class="text-sm text-content-faint text-center py-12">Loading conversation...</p>
    {:else if !data || data.messages.length === 0}
      <div class="max-w-xl mx-auto text-center py-12">
        <h3 class="text-base font-semibold text-content">Manage SmarterVote through the deployed agent</h3>
        <p class="mt-2 text-sm text-content-muted">
          Ask it to inspect races, review drafts, queue research, check runs and logs, publish with approval, or analyze traffic.
        </p>
      </div>
    {:else}
      {#each data.messages as message (message.message_id)}
        {#if message.role === "tool"}
          <details class="max-w-4xl mx-auto rounded-lg border border-stroke bg-surface px-3 py-2">
            <summary class="cursor-pointer text-xs font-medium text-content-muted">
              Tool: {message.tool_name ?? "operation"}
            </summary>
            <pre class="mt-2 text-xs text-content-subtle whitespace-pre-wrap break-words max-h-64 overflow-auto">{message.content}</pre>
          </details>
        {:else}
          <div class="max-w-4xl mx-auto flex {message.role === 'user' ? 'justify-end' : 'justify-start'}">
            <div class="max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words
              {message.role === 'user'
                ? 'bg-blue-600 text-white rounded-br-sm'
                : 'bg-surface border border-stroke text-content rounded-bl-sm'}">
              {message.content || (message.metadata?.tool_calls ? "Selecting an operation..." : "")}
            </div>
          </div>
        {/if}
      {/each}
    {/if}

    {#if isActive}
      <div class="max-w-4xl mx-auto flex items-center gap-2 text-xs text-blue-600">
        <span class="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
        {statusLabel(latestTask)}
      </div>
    {/if}

    {#if waitingApproval && latestTask}
      <div class="max-w-4xl mx-auto rounded-xl border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30 p-4">
        <p class="text-sm font-semibold text-amber-900 dark:text-amber-100">Approval required</p>
        <p class="mt-1 text-sm text-amber-800 dark:text-amber-200">
          {latestTask.approval_summary ?? "The agent requested a protected operation."}
        </p>
        <div class="mt-3 flex gap-2">
          <button
            type="button"
            class="btn-primary px-3 py-1.5 text-sm rounded-lg disabled:opacity-50"
            disabled={actionPending}
            on:click={() => approve(latestTask)}
          >Approve</button>
          <button
            type="button"
            class="px-3 py-1.5 text-sm rounded-lg border border-stroke text-content disabled:opacity-50"
            disabled={actionPending}
            on:click={() => cancel(latestTask)}
          >Cancel</button>
        </div>
      </div>
    {/if}
  </div>

  {#if error}
    <div class="px-4 py-2 text-xs text-red-600 border-t border-red-200 bg-red-50 dark:bg-red-950/20">{error}</div>
  {/if}

  <div class="p-3 border-t border-stroke bg-surface">
    <div class="flex items-end gap-2">
      <textarea
        bind:value={input}
        rows="2"
        on:keydown={handleKeydown}
        disabled={sending || isActive || waitingApproval}
        placeholder={waitingApproval ? "Approve or cancel the pending operation" : isActive ? "Agent is working..." : "Ask the admin agent..."}
        class="flex-1 resize-none rounded-xl border border-stroke bg-surface px-3 py-2 text-sm text-content focus:outline-none focus:ring-2 focus:ring-blue-500/30 disabled:opacity-50"
      ></textarea>
      <button
        type="button"
        class="btn-primary rounded-xl px-4 py-2 text-sm disabled:opacity-50"
        disabled={sending || isActive || waitingApproval || !input.trim()}
        on:click={send}
      >Send</button>
    </div>
  </div>
</div>
