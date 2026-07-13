<script lang="ts">
  import { onMount, tick } from "svelte";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import type {
    AdminChatMessage,
    AdminChatAction,
    AdminChatRaceRecord,
  } from "$lib/services/pipelineApiService";

  export let apiService: PipelineApiService;

  // ---- types ---------------------------------------------------------------
  interface ChatMessage {
    role: "user" | "assistant" | "system";
    content: string;
    ts: number;
    thinkingSteps?: string[];
  }

  // ---- constants -----------------------------------------------------------
  const SESSION_KEY = "admin-chat-messages";

  // ---- state ---------------------------------------------------------------
  const SUGGESTIONS = [
    "Which races are stale or haven\u2019t been updated recently?",
    "Show me races with a low quality grade",
    "Which races have candidates missing issue data? Suggest targeted completion runs.",
    "What candidates are in the GA governor race?",
  ];

  const INITIAL_MESSAGE: ChatMessage = {
    role: "assistant",
    content:
      "Hi! I\u2019m your SmarterVote admin assistant.\n\nI can help you:\n- Review race quality, freshness, and candidate details\n- Identify races that need updating\n- Kick off pipeline runs with custom settings\n\nWhat would you like to do?",
    ts: 0,
  };

  function loadMessages(): ChatMessage[] {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as ChatMessage[];
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // ignore storage errors
    }
    return [{ ...INITIAL_MESSAGE, ts: Date.now() }];
  }

  let messages: ChatMessage[] = loadMessages();
  let copiedTs: number | null = null;

  let input = "";
  let sending = false;
  let thinkingLabel = "Thinking\u2026";

  // Pending action waiting for user confirmation
  let pendingAction: AdminChatAction | null = null;
  let pendingActionDescription = "";
  let pendingRaceRecords: AdminChatRaceRecord[] = [];
  let confirmingAction = false;
  let actionResult = "";

  // Pending question from AI
  let pendingQuestion: string | null = null;

  // Editable action options (shown in approval card)
  let editCheapMode = true;
  let editCandidateNames = "";
  let editNote = "";
  let editGoal = "";
  let showAdvancedEdit = false;
  let selectedRaceIds: Set<string> = new Set();

  let scrollEl: HTMLElement;
  let textareaEl: HTMLTextAreaElement;
  let userScrolledUp = false;

  // ---- scroll management ---------------------------------------------------
  function onScroll() {
    if (!scrollEl) return;
    const atBottom =
      scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 60;
    userScrolledUp = !atBottom;
  }

  async function scrollToBottom(force = false) {
    await tick();
    if (scrollEl && (force || !userScrolledUp)) {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
  }

  // ---- helpers -------------------------------------------------------------
  function formatOptions(opts: Record<string, unknown> | undefined): string {
    if (!opts || !Object.keys(opts).length) return "default options";
    const parts: string[] = [];
    if (opts.force_fresh) parts.push("force fresh");
    if (opts.cheap_mode === false) parts.push("high-quality mode");
    if (Array.isArray(opts.enabled_steps) && opts.enabled_steps.length) {
      parts.push(`steps: ${(opts.enabled_steps as string[]).join(", ")}`);
    }
    if (opts.research_model) parts.push(`model: ${opts.research_model}`);
    if (opts.max_candidates)
      parts.push(`max candidates: ${opts.max_candidates}`);
    if (Array.isArray(opts.candidate_names) && opts.candidate_names.length) {
      parts.push(
        `candidates: ${(opts.candidate_names as string[]).join(", ")}`,
      );
    }
    if (opts.target_no_info) parts.push("target no-info candidates");
    if (opts.note) parts.push(`note: \u201c${opts.note}\u201d`);
    return parts.length ? parts.join(" \u00b7 ") : "default options";
  }

  function gradeColor(grade?: string): string {
    if (!grade)
      return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
    if (grade === "A")
      return "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300";
    if (grade === "B")
      return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300";
    if (grade === "C")
      return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300";
    if (grade === "D")
      return "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300";
    return "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300";
  }

  function freshnessColor(f?: string): string {
    if (!f)
      return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
    if (f === "fresh")
      return "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300";
    if (f === "recent")
      return "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300";
    if (f === "aging")
      return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300";
    return "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300";
  }

  function statusColor(s: string): string {
    if (s === "published")
      return "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300";
    if (s === "draft")
      return "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300";
    if (s === "queued")
      return "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300";
    if (s === "running")
      return "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300";
    if (s === "failed")
      return "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300";
    return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  }

  // ---- copy to clipboard ---------------------------------------------------
  async function copyMessage(content: string, ts: number) {
    try {
      await navigator.clipboard.writeText(content);
      copiedTs = ts;
      setTimeout(() => {
        copiedTs = null;
      }, 1500);
    } catch {
      /* ignore */
    }
  }

  function formatTs(ts: number): string {
    if (!ts) return "";
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // ---- markdown renderer ---------------------------------------------------
  function renderContent(text: string): string {
    // Step 1: extract fenced code blocks and protect them from further processing
    const codeBlocks: string[] = [];
    let s = text.replace(
      /```([^\n]*)\n?([\s\S]*?)```/g,
      (_m, lang: string, inner: string) => {
        const langLabel = lang.trim()
          ? `<div class="text-[10px] text-content-subtle mb-1 font-mono">${escapeHtml(
              lang.trim(),
            )}</div>`
          : "";
        const placeholder = `@@CODE${codeBlocks.length}@@`;
        codeBlocks.push(
          `<pre class="my-2 p-2.5 rounded-lg bg-surface-alt text-xs overflow-x-auto border border-stroke leading-relaxed">${langLabel}<code>${escapeHtml(
            inner.replace(/\n$/, ""),
          )}</code></pre>`,
        );
        return placeholder;
      },
    );

    // Step 2: escape HTML in remaining text
    s = escapeHtml(s);

    // Step 3: restore code block placeholders (already escaped inside)
    s = s.replace(
      /@@CODE(\d+)@@/g,
      (_m, idx: string) => codeBlocks[Number(idx)],
    );

    // Inline code
    s = s.replace(
      /`([^`\n]+)`/g,
      '<code class="bg-surface-alt border border-stroke px-1 py-0.5 rounded text-xs font-mono">$1</code>',
    );

    // Bold + italic (order matters: *** before ** before *)
    s = s.replace(/\*\*\*([\s\S]*?)\*\*\*/g, "<strong><em>$1</em></strong>");
    s = s.replace(/\*\*([\s\S]*?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/__([\s\S]*?)__/g, "<strong>$1</strong>");
    s = s.replace(/\*([\s\S]*?)\*/g, "<em>$1</em>");
    s = s.replace(/_([\s\S]*?)_/g, "<em>$1</em>");
    // Strikethrough
    s = s.replace(/~~([\s\S]*?)~~/g, "<del>$1</del>");

    // Links [text](url)
    s = s.replace(
      /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 dark:text-blue-400 underline hover:opacity-80">$1</a>',
    );

    // Process lines for block-level elements
    const lines = s.split("\n");
    const out: string[] = [];
    // Stack: each entry is { tag: "ul"|"ol", indent: number }
    type ListFrame = { tag: "ul" | "ol"; indent: number };
    const listStack: ListFrame[] = [];

    function closeListsToIndent(targetIndent: number) {
      while (
        listStack.length > 0 &&
        listStack[listStack.length - 1].indent > targetIndent
      ) {
        out.push(`</${listStack.pop()!.tag}>`);
      }
    }

    function closeAllLists() {
      while (listStack.length > 0) out.push(`</${listStack.pop()!.tag}>`);
    }

    // Collect paragraph lines to group into <p> tags
    let paraLines: string[] = [];

    function flushParagraph() {
      if (paraLines.length > 0) {
        out.push(
          `<p class="mb-1 leading-relaxed">${paraLines.join("<br>")}</p>`,
        );
        paraLines = [];
      }
    }

    let i = 0;
    while (i < lines.length) {
      const raw = lines[i];
      const trimmed = raw.trim();

      // Blank line
      if (trimmed === "") {
        flushParagraph();
        closeAllLists();
        i++;
        continue;
      }

      // ATX headers
      const hMatch = raw.match(/^(#{1,6})\s+(.+)$/);
      if (hMatch) {
        flushParagraph();
        closeAllLists();
        const lvl = hMatch[1].length;
        const cls =
          lvl === 1
            ? "text-base font-bold mt-3 mb-1"
            : lvl === 2
              ? "text-sm font-bold mt-2 mb-0.5"
              : "text-sm font-semibold mt-1";
        out.push(`<p class="${cls}">${hMatch[2]}</p>`);
        i++;
        continue;
      }

      // Horizontal rule
      if (/^[-*_]{3,}$/.test(trimmed)) {
        flushParagraph();
        closeAllLists();
        out.push('<hr class="my-2 border-stroke">');
        i++;
        continue;
      }

      // Blockquote
      const bqMatch = raw.match(/^>\s?(.*)/);
      if (bqMatch) {
        flushParagraph();
        closeAllLists();
        out.push(
          `<blockquote class="border-l-2 border-blue-400 pl-3 my-1 text-content-muted italic text-sm">${bqMatch[1]}</blockquote>`,
        );
        i++;
        continue;
      }

      // Table detection (line starts with |)
      if (
        trimmed.startsWith("|") &&
        i + 1 < lines.length &&
        /^\|[\s|:-]+\|/.test(lines[i + 1].trim())
      ) {
        flushParagraph();
        closeAllLists();
        // Parse header row
        const headerCells = trimmed
          .split("|")
          .filter((_, idx, arr) => idx > 0 && idx < arr.length - 1)
          .map((c) => c.trim());
        i += 2; // skip header + separator
        const rows: string[][] = [];
        while (i < lines.length && lines[i].trim().startsWith("|")) {
          const cells = lines[i]
            .trim()
            .split("|")
            .filter((_, idx, arr) => idx > 0 && idx < arr.length - 1)
            .map((c) => c.trim());
          rows.push(cells);
          i++;
        }
        const thead = `<thead class="bg-surface-alt"><tr>${headerCells
          .map(
            (c) =>
              `<th class="px-2 py-1 text-left text-xs font-semibold text-content-muted border-b border-stroke">${c}</th>`,
          )
          .join("")}</tr></thead>`;
        const tbody = `<tbody>${rows
          .map(
            (row) =>
              `<tr class="border-b border-stroke/50 hover:bg-surface-alt/50">${row
                .map(
                  (c) => `<td class="px-2 py-1 text-xs text-content">${c}</td>`,
                )
                .join("")}</tr>`,
          )
          .join("")}</tbody>`;
        out.push(
          `<div class="overflow-x-auto my-2"><table class="w-full text-left border border-stroke rounded-lg overflow-hidden text-xs">${thead}${tbody}</table></div>`,
        );
        continue;
      }

      // List items (unordered or ordered), with indent support
      const ulMatch = raw.match(/^(\s*)[-*+]\s+(.*)/);
      const olMatch = raw.match(/^(\s*)\d+\.\s+(.*)/);
      const listMatch = ulMatch || olMatch;

      if (listMatch) {
        flushParagraph();
        const indent = listMatch[1].length;
        const content = listMatch[2];
        const tag = ulMatch ? "ul" : "ol";
        const ulCls = 'class="list-disc pl-4 space-y-0.5 my-1"';
        const olCls = 'class="list-decimal pl-4 space-y-0.5 my-1"';

        // Close deeper lists
        closeListsToIndent(indent);

        // Open new list if needed at this indent
        if (
          listStack.length === 0 ||
          listStack[listStack.length - 1].indent < indent ||
          listStack[listStack.length - 1].tag !== tag
        ) {
          out.push(`<${tag} ${tag === "ul" ? ulCls : olCls}>`);
          listStack.push({ tag, indent });
        }

        out.push(`<li class="leading-relaxed">${content}</li>`);
        i++;
        continue;
      }

      // Regular text line
      closeAllLists();

      // Pre-formatted code block placeholder lines pass through unchanged
      if (raw.includes("\x00")) {
        flushParagraph();
        out.push(raw);
        i++;
        continue;
      }

      paraLines.push(raw);
      i++;
    }

    flushParagraph();
    closeAllLists();
    return out.join("");
  }

  function escapeHtml(s: string): string {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---- build final options for queuing ------------------------------------
  function buildFinalOptions(): Record<string, unknown> {
    const base = { ...(pendingAction?.options ?? {}) };
    base.cheap_mode = editCheapMode;
    const names = editCandidateNames
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (names.length) base.candidate_names = names;
    else delete base.candidate_names;
    const note = editNote.trim();
    if (note) base.note = note;
    else delete base.note;
    const goal = editGoal.trim();
    if (goal) base.goal = goal;
    else delete base.goal;
    return base;
  }

  // ---- send message --------------------------------------------------------
  async function sendMessage(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || sending) return;
    if (!text) {
      input = "";
      await tick();
      if (textareaEl) {
        textareaEl.style.height = "auto";
        textareaEl.style.height = "42px";
      }
    }

    messages = [...messages, { role: "user", content: msg, ts: Date.now() }];
    userScrolledUp = false;
    await scrollToBottom(true);

    sending = true;
    thinkingLabel = "Thinking\u2026";
    pendingAction = null;
    pendingQuestion = null;
    pendingRaceRecords = [];
    actionResult = "";
    showAdvancedEdit = false;

    try {
      const history: AdminChatMessage[] = messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        }));

      // Show a brief "fetching race data" label update after a short pause
      const labelTimer = setTimeout(() => {
        thinkingLabel = "Fetching race data\u2026";
      }, 800);

      const res = await apiService.adminChat(history);
      clearTimeout(labelTimer);

      const thinkingSteps = res.thinking_steps ?? [];

      messages = [
        ...messages,
        {
          role: "assistant",
          content: res.reply,
          ts: Date.now(),
          thinkingSteps: thinkingSteps.length ? thinkingSteps : undefined,
        },
      ];

      if (res.action?.type === "queue_run") {
        pendingAction = res.action;
        pendingActionDescription =
          res.action.description || "Queue a pipeline run";
        pendingRaceRecords = res.race_records ?? [];
        editCheapMode = res.action.options?.cheap_mode !== false;
        editCandidateNames = Array.isArray(res.action.options?.candidate_names)
          ? (res.action.options!.candidate_names as string[]).join(", ")
          : "";
        editNote =
          typeof res.action.options?.note === "string"
            ? res.action.options.note
            : "";
        editGoal =
          typeof res.action.options?.goal === "string"
            ? res.action.options.goal
            : "";
        selectedRaceIds = new Set(res.action.race_ids ?? []);
      } else if (res.question) {
        pendingQuestion = res.question;
      }
    } catch (e) {
      messages = [
        ...messages,
        { role: "system", content: `\u26a0\ufe0f Error: ${e}`, ts: Date.now() },
      ];
    } finally {
      sending = false;
      thinkingLabel = "Thinking\u2026";
      await scrollToBottom();
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function formatQueueErrors(
    errors: Array<{ race_id: string; error: string }>,
  ) {
    return errors.map((e) => `${e.race_id}: ${e.error}`).join("; ");
  }

  // ---- action confirm/dismiss ----------------------------------------------
  async function confirmAction() {
    if (!pendingAction || selectedRaceIds.size === 0) return;
    confirmingAction = true;
    actionResult = "";
    try {
      const finalOpts = buildFinalOptions();
      const raceIdsToQueue = Array.from(selectedRaceIds);
      const result = await apiService.queueRaces(raceIdsToQueue, finalOpts);
      if (result.errors.length > 0 || result.added.length === 0) {
        const detail = result.errors.length
          ? formatQueueErrors(result.errors)
          : "No queue items were created.";
        actionResult = `Queued ${result.added.length} of ${raceIdsToQueue.length}.`;
        messages = [
          ...messages,
          {
            role: "system",
            content: `Queue completed with failures. Added ${result.added.length} of ${raceIdsToQueue.length}: ${detail}`,
            ts: Date.now(),
          },
        ];
        await scrollToBottom(true);
        return;
      }
      actionResult = "\u2713 Queued";
      messages = [
        ...messages,
        {
          role: "system",
          content: `\u2713 Run queued for: ${raceIdsToQueue.join(", ")}`,
          ts: Date.now(),
        },
      ];
      await scrollToBottom(true);
      setTimeout(() => {
        pendingAction = null;
        actionResult = "";
        pendingRaceRecords = [];
        showAdvancedEdit = false;
        editGoal = "";
        selectedRaceIds = new Set();
      }, 2000);
    } catch (e) {
      actionResult = `Failed: ${e}`;
    } finally {
      confirmingAction = false;
    }
  }

  function dismissAction() {
    pendingAction = null;
    actionResult = "";
    pendingRaceRecords = [];
    showAdvancedEdit = false;
    editGoal = "";
    selectedRaceIds = new Set();
  }

  function dismissQuestion() {
    pendingQuestion = null;
  }

  function clearConversation() {
    messages = [{ ...INITIAL_MESSAGE, ts: Date.now() }];
    pendingAction = null;
    pendingQuestion = null;
    actionResult = "";
    pendingRaceRecords = [];
    input = "";
    userScrolledUp = false;
    showAdvancedEdit = false;
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
    scrollToBottom(true);
  }

  $: showSuggestions = messages.length <= 1 && !sending;

  // Persist conversation to sessionStorage whenever messages change
  $: try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(messages));
  } catch {
    /* ignore */
  }

  onMount(() => scrollToBottom(true));
</script>

<div class="flex flex-col gap-3 flex-1 min-h-0">
  <!-- Header bar -->
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2">
      <div
        class="w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-900/40 flex items-center justify-center"
        aria-hidden="true"
      >
        <svg
          class="w-3.5 h-3.5 text-blue-600 dark:text-blue-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          stroke-width="2"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"
          />
        </svg>
      </div>
      <span class="text-sm font-medium text-content">Admin Agent</span>
      <span class="text-xs text-content-subtle">Powered by AI</span>
    </div>
    {#if messages.length > 1}
      <button
        type="button"
        class="text-xs text-content-subtle hover:text-content transition-colors px-2 py-1 rounded hover:bg-surface-alt"
        on:click={clearConversation}
      >
        Clear chat
      </button>
    {/if}
  </div>

  <!-- Message list -->
  <div
    bind:this={scrollEl}
    on:scroll={onScroll}
    class="flex-1 overflow-y-auto space-y-3 p-4 rounded-xl bg-surface-alt border border-stroke"
  >
    {#each messages as msg (msg.ts)}
      {#if msg.role === "user"}
        <div class="flex justify-end">
          <div
            class="max-w-[78%] bg-blue-600 text-white rounded-2xl rounded-br-none px-4 py-2.5 text-sm shadow-sm leading-relaxed"
            title={formatTs(msg.ts)}
          >
            <!-- eslint-disable-next-line svelte/no-at-html-tags -->
            {@html renderContent(msg.content)}
          </div>
        </div>
      {:else if msg.role === "assistant"}
        <div class="flex justify-start items-start gap-2.5 group">
          <div
            class="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm"
            aria-hidden="true"
          >
            <svg
              class="w-3.5 h-3.5 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              stroke-width="2.5"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3"
              />
            </svg>
          </div>
          <div class="max-w-[78%] flex flex-col gap-1">
            {#if msg.thinkingSteps && msg.thinkingSteps.length}
              <div class="flex flex-wrap gap-1 mb-0.5">
                {#each msg.thinkingSteps as step}
                  <span
                    class="text-[10px] text-content-subtle border border-stroke rounded-full px-2 py-0.5 bg-surface flex items-center gap-1"
                  >
                    <svg
                      class="w-2.5 h-2.5 text-blue-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      stroke-width="2"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    {step}
                  </span>
                {/each}
              </div>
            {/if}
            <div
              class="bg-surface border border-stroke rounded-2xl rounded-bl-none px-4 py-2.5 text-sm text-content shadow-sm leading-relaxed"
              title={formatTs(msg.ts)}
            >
              <!-- eslint-disable-next-line svelte/no-at-html-tags -->
              {@html renderContent(msg.content)}
            </div>
            <button
              type="button"
              class="self-start opacity-0 group-hover:opacity-100 transition-opacity text-xs text-content-subtle hover:text-content flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-surface-alt"
              on:click={() => copyMessage(msg.content, msg.ts)}
              aria-label="Copy message"
            >
              {#if copiedTs === msg.ts}
                <svg
                  class="w-3 h-3 text-green-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  stroke-width="2.5"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    d="M5 13l4 4L19 7"
                  />
                </svg>
                <span class="text-green-500">Copied</span>
              {:else}
                <svg
                  class="w-3 h-3"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  stroke-width="2"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
                Copy
              {/if}
            </button>
          </div>
        </div>
      {:else}
        <!-- System / status pill -->
        <div class="flex justify-center">
          <span
            class="text-xs text-content-subtle bg-surface border border-stroke rounded-full px-3 py-1 flex items-center gap-1.5"
          >
            <!-- eslint-disable-next-line svelte/no-at-html-tags -->
            {@html renderContent(msg.content)}
          </span>
        </div>
      {/if}
    {/each}

    <!-- Typing indicator -->
    {#if sending}
      <div class="flex justify-start items-center gap-2.5">
        <div
          class="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow-sm"
          aria-hidden="true"
        >
          <svg
            class="w-3.5 h-3.5 text-white animate-pulse"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <circle cx="10" cy="10" r="4" />
          </svg>
        </div>
        <div
          class="bg-surface border border-stroke rounded-2xl rounded-bl-none px-4 py-3 flex items-center gap-2"
        >
          <span class="inline-flex items-center gap-1">
            <span
              class="w-1.5 h-1.5 rounded-full bg-content-subtle animate-bounce"
              style="animation-delay:0ms"
            ></span>
            <span
              class="w-1.5 h-1.5 rounded-full bg-content-subtle animate-bounce"
              style="animation-delay:150ms"
            ></span>
            <span
              class="w-1.5 h-1.5 rounded-full bg-content-subtle animate-bounce"
              style="animation-delay:300ms"
            ></span>
          </span>
          <span class="text-xs text-content-subtle">{thinkingLabel}</span>
        </div>
      </div>
    {/if}

    <!-- Suggestion chips (shown only before first user message) -->
    {#if showSuggestions}
      <div class="pt-2 flex flex-wrap gap-2">
        {#each SUGGESTIONS as s}
          <button
            type="button"
            class="text-xs px-3 py-1.5 rounded-full border border-stroke bg-surface hover:bg-blue-50 hover:border-blue-300 dark:hover:bg-blue-900/20 dark:hover:border-blue-700 text-content-muted hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
            on:click={() => sendMessage(s)}
          >
            {s}
          </button>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Pending action card -->
  {#if pendingAction}
    <div
      class="rounded-xl border border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950/30 p-4 space-y-3"
    >
      <!-- Header -->
      <div class="flex items-center gap-2">
        <svg
          class="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          stroke-width="2"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
          />
        </svg>
        <p class="text-sm font-semibold text-blue-900 dark:text-blue-100">
          Awaiting your approval
        </p>
      </div>
      <p class="text-sm text-blue-700 dark:text-blue-300">
        {pendingActionDescription}
      </p>

      <!-- Race metadata: compact table for large batches, cards for small batches -->
      {#if pendingRaceRecords.length > 0}
        {#if pendingRaceRecords.length > 5}
          <!-- Large batch: scrollable table with per-row checkboxes -->
          <div>
            <div class="flex items-center justify-between mb-1.5 px-0.5">
              <span class="text-xs text-content-subtle"
                >{selectedRaceIds.size} of {pendingRaceRecords.length} selected</span
              >
              <div class="flex gap-3">
                <button
                  type="button"
                  class="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  on:click={() => {
                    selectedRaceIds = new Set(
                      pendingRaceRecords.map((r) => r.race_id),
                    );
                  }}>Select all</button
                >
                <button
                  type="button"
                  class="text-xs text-content-subtle hover:underline"
                  on:click={() => {
                    selectedRaceIds = new Set();
                  }}>Deselect all</button
                >
              </div>
            </div>
            <div
              class="max-h-64 overflow-y-auto rounded-lg border border-blue-200 dark:border-blue-800 text-xs"
            >
              <table class="w-full">
                <thead class="bg-blue-50 dark:bg-blue-900/30 sticky top-0">
                  <tr>
                    <th class="w-8 px-2 py-1.5 text-left">
                      <input
                        type="checkbox"
                        checked={selectedRaceIds.size ===
                          pendingRaceRecords.length &&
                          pendingRaceRecords.length > 0}
                        on:change={(e) => {
                          selectedRaceIds = e.currentTarget.checked
                            ? new Set(pendingRaceRecords.map((r) => r.race_id))
                            : new Set();
                        }}
                        class="rounded"
                      />
                    </th>
                    <th
                      class="px-2 py-1.5 text-left font-medium text-content-subtle"
                      >Race</th
                    >
                    <th
                      class="px-2 py-1.5 text-left font-medium text-content-subtle"
                      >Grade</th
                    >
                    <th
                      class="px-2 py-1.5 text-left font-medium text-content-subtle"
                      >Fresh</th
                    >
                    <th
                      class="px-2 py-1.5 text-left font-medium text-content-subtle"
                      >Status</th
                    >
                  </tr>
                </thead>
                <tbody
                  class="divide-y divide-blue-100 dark:divide-blue-900 bg-white dark:bg-blue-950/10"
                >
                  {#each pendingRaceRecords as rec}
                    <tr
                      class="hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-opacity {!selectedRaceIds.has(
                        rec.race_id,
                      )
                        ? 'opacity-40'
                        : ''}"
                    >
                      <td class="px-2 py-1.5">
                        <input
                          type="checkbox"
                          checked={selectedRaceIds.has(rec.race_id)}
                          on:change={(e) => {
                            const next = new Set(selectedRaceIds);
                            if (e.currentTarget.checked) next.add(rec.race_id);
                            else next.delete(rec.race_id);
                            selectedRaceIds = next;
                          }}
                          class="rounded"
                        />
                      </td>
                      <td class="px-2 py-1.5">
                        <div
                          class="font-mono font-medium text-blue-800 dark:text-blue-200"
                        >
                          {rec.race_id}
                        </div>
                        {#if rec.title}<div
                            class="text-content-subtle truncate max-w-[180px]"
                          >
                            {rec.title}
                          </div>{/if}
                      </td>
                      <td class="px-2 py-1.5">
                        {#if rec.quality_grade}
                          <span
                            class="rounded px-1.5 py-0.5 font-semibold {gradeColor(
                              rec.quality_grade,
                            )}">{rec.quality_grade}</span
                          >
                        {/if}
                      </td>
                      <td class="px-2 py-1.5">
                        {#if rec.freshness}
                          <span
                            class="rounded px-1.5 py-0.5 {freshnessColor(
                              rec.freshness,
                            )}">{rec.freshness}</span
                          >
                        {/if}
                      </td>
                      <td class="px-2 py-1.5">
                        <span
                          class="rounded px-1.5 py-0.5 {statusColor(
                            rec.status,
                          )}">{rec.status}</span
                        >
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        {:else}
          <!-- Small batch: card layout -->
          <div class="flex flex-wrap gap-2 max-h-52 overflow-y-auto pr-0.5">
            {#each pendingRaceRecords as rec}
              <div
                class="flex-1 min-w-[180px] rounded-lg border border-blue-200 dark:border-blue-800 bg-white dark:bg-blue-950/20 p-2.5 text-xs space-y-1.5"
              >
                <div
                  class="font-mono font-semibold text-blue-800 dark:text-blue-200 truncate"
                >
                  {rec.race_id}
                </div>
                {#if rec.title}
                  <div class="text-content-muted truncate">{rec.title}</div>
                {/if}
                <div class="flex flex-wrap gap-1">
                  {#if rec.discovery_only}
                    <span
                      class="rounded px-1.5 py-0.5 text-xs font-semibold bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300 border border-violet-300 dark:border-violet-700"
                    >
                      discovery only
                    </span>
                  {/if}
                  {#if rec.quality_grade}
                    <span
                      class="rounded px-1.5 py-0.5 font-semibold {gradeColor(
                        rec.quality_grade,
                      )}"
                    >
                      Grade {rec.quality_grade}
                    </span>
                  {/if}
                  {#if rec.freshness}
                    <span
                      class="rounded px-1.5 py-0.5 {freshnessColor(
                        rec.freshness,
                      )}">{rec.freshness}</span
                    >
                  {/if}
                  <span class="rounded px-1.5 py-0.5 {statusColor(rec.status)}"
                    >{rec.status}</span
                  >
                </div>
                {#if rec.candidate_count}
                  <div class="text-content-subtle">
                    {rec.candidate_count} candidate{rec.candidate_count !== 1
                      ? "s"
                      : ""}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      {:else}
        <div class="flex flex-wrap gap-1.5">
          {#each pendingAction.race_ids ?? [] as raceId}
            <span
              class="text-xs font-mono bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 rounded px-1.5 py-0.5 border border-blue-200 dark:border-blue-800"
            >
              {raceId}
            </span>
          {/each}
        </div>
      {/if}

      <!-- Editable run options -->
      <div
        class="border border-blue-200 dark:border-blue-800 rounded-lg bg-white dark:bg-blue-950/10 divide-y divide-blue-100 dark:divide-blue-900"
      >
        <!-- cheap_mode toggle — always shown -->
        <label
          class="flex items-center justify-between px-3 py-2.5 gap-3 cursor-pointer select-none"
        >
          <div>
            <span class="text-xs font-medium text-content">Quality mode</span>
            <p class="text-[10px] text-content-subtle mt-0.5">
              {editCheapMode
                ? "Fast & cheap (default) — good for most cases"
                : "High quality — slower, uses better models, costs more"}
            </p>
          </div>
          <div class="flex items-center gap-1.5 flex-shrink-0">
            <span class="text-[10px] text-content-subtle"
              >{editCheapMode ? "Fast" : "High-Q"}</span
            >
            <button
              type="button"
              role="switch"
              aria-label="Toggle quality mode"
              aria-checked={!editCheapMode}
              class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/30 {!editCheapMode
                ? 'bg-blue-600'
                : 'bg-gray-300 dark:bg-gray-600'}"
              on:click={() => (editCheapMode = !editCheapMode)}
            >
              <span
                class="inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform {!editCheapMode
                  ? 'translate-x-4'
                  : 'translate-x-0.5'}"
              ></span>
            </button>
          </div>
        </label>

        <!-- Expand for more options -->
        <button
          type="button"
          class="w-full flex items-center justify-between px-3 py-2 text-xs text-content-subtle hover:text-content hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
          on:click={() => (showAdvancedEdit = !showAdvancedEdit)}
        >
          <span>Advanced options</span>
          <svg
            class="w-3.5 h-3.5 transition-transform {showAdvancedEdit
              ? 'rotate-180'
              : ''}"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            stroke-width="2"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </button>

        {#if showAdvancedEdit}
          <div class="px-3 py-2.5 space-y-2.5">
            <div>
              <label
                for="edit-candidate-names"
                class="block text-[10px] font-medium text-content-subtle mb-1"
              >
                Candidate names (comma-separated, leave blank for all)
              </label>
              <input
                id="edit-candidate-names"
                type="text"
                bind:value={editCandidateNames}
                placeholder="e.g. Jordan Koteras, Paul Berry III"
                class="w-full text-xs bg-surface border border-stroke rounded-lg px-2.5 py-1.5 text-content placeholder-content-subtle focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
              />
            </div>
            <div>
              <label
                for="edit-note"
                class="block text-[10px] font-medium text-content-subtle mb-1"
                >Note</label
              >
              <input
                id="edit-note"
                type="text"
                bind:value={editNote}
                placeholder="Short label for this run"
                class="w-full text-xs bg-surface border border-stroke rounded-lg px-2.5 py-1.5 text-content placeholder-content-subtle focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
              />
            </div>
            <div>
              <label
                for="edit-goal"
                class="block text-[10px] font-medium text-content-subtle mb-1"
                >Goal</label
              >
              <input
                id="edit-goal"
                type="text"
                bind:value={editGoal}
                placeholder="Why is this run being triggered? (e.g. Update after primary)"
                class="w-full text-xs bg-surface border border-stroke rounded-lg px-2.5 py-1.5 text-content placeholder-content-subtle focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
              />
            </div>
            {#if pendingAction.options && Object.keys(pendingAction.options).length}
              <p class="text-[10px] text-content-subtle">
                Other options from AI: {formatOptions(pendingAction.options)}
              </p>
            {/if}
          </div>
        {/if}
      </div>

      <!-- Action buttons -->
      <div class="flex items-center gap-2">
        {#if actionResult}
          <span
            class="text-sm font-medium {actionResult.startsWith('\u2713')
              ? 'text-green-600 dark:text-green-400'
              : 'text-red-600 dark:text-red-400'}"
          >
            {actionResult}
          </span>
        {:else}
          <button
            type="button"
            class="px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors disabled:opacity-50 flex items-center gap-1.5"
            on:click={confirmAction}
            disabled={confirmingAction || selectedRaceIds.size === 0}
          >
            {#if confirmingAction}
              <svg
                class="w-3.5 h-3.5 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  class="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  stroke-width="4"
                />
                <path
                  class="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Queuing\u2026
            {:else}
              <svg
                class="w-3.5 h-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                stroke-width="2"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                />
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              Approve &amp; queue
            {/if}
          </button>
          <button
            type="button"
            class="px-3 py-1.5 text-sm font-medium rounded-lg border border-stroke hover:bg-surface-alt text-content transition-colors"
            on:click={dismissAction}
            disabled={confirmingAction}
          >
            Cancel
          </button>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Pending question card -->
  {#if pendingQuestion}
    <div
      class="rounded-xl border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-4 space-y-3"
    >
      <div class="flex items-start gap-2">
        <svg
          class="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          stroke-width="2"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01"
          />
        </svg>
        <p class="text-sm text-amber-900 dark:text-amber-100">
          {pendingQuestion}
        </p>
      </div>
      <button
        type="button"
        class="text-xs text-amber-600 dark:text-amber-400 hover:underline"
        on:click={dismissQuestion}
      >
        Dismiss
      </button>
    </div>
  {/if}

  <!-- Input area -->
  <div class="flex gap-2 items-end">
    <textarea
      bind:this={textareaEl}
      bind:value={input}
      on:keydown={handleKeydown}
      on:input={() => {
        if (textareaEl) {
          textareaEl.style.height = "auto";
          textareaEl.style.height =
            Math.min(textareaEl.scrollHeight, 160) + "px";
        }
      }}
      rows="1"
      style="min-height: 42px;"
      placeholder={sending
        ? "Thinking\u2026"
        : "Ask about races or request a run\u2026 (Enter to send, Shift+Enter for newline)"}
      class="flex-1 resize-none rounded-xl border border-stroke bg-surface px-3.5 py-2.5 text-sm text-content placeholder-content-subtle focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-colors disabled:opacity-50"
      disabled={sending}></textarea>
    <button
      type="button"
      class="flex-shrink-0 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors flex items-center gap-1.5 shadow-sm"
      on:click={() => sendMessage()}
      disabled={sending || !input.trim()}
    >
      {#if sending}
        <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle
            class="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            stroke-width="4"
          />
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
      {:else}
        <svg
          class="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          stroke-width="2"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
          />
        </svg>
      {/if}
      Send
    </button>
  </div>
</div>
