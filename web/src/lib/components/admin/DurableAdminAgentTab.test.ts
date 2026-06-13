import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PipelineApiService } from "$lib/services/pipelineApiService";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("DurableAdminAgentTab", () => {
  it("creates a persisted conversation and submits work", async () => {
    vi.resetModules();
    const { default: DurableAdminAgentTab } = await import("./DurableAdminAgentTab.svelte");
    const api = {
      createAdminAgentConversation: vi.fn().mockResolvedValue({
        conversation_id: "conversation-1",
        title: "New admin conversation",
        status: "active",
        created_at: "2026-06-13T00:00:00Z",
        updated_at: "2026-06-13T00:00:00Z",
      }),
      getAdminAgentConversation: vi.fn().mockResolvedValue({
        conversation: {
          conversation_id: "conversation-1",
          title: "New admin conversation",
          status: "active",
          created_at: "2026-06-13T00:00:00Z",
          updated_at: "2026-06-13T00:00:00Z",
        },
        messages: [],
        tasks: [],
      }),
      submitAdminAgentMessage: vi.fn().mockResolvedValue({
        task_id: "task-1",
        conversation_id: "conversation-1",
        status: "queued",
        created_at: "2026-06-13T00:00:01Z",
        updated_at: "2026-06-13T00:00:01Z",
      }),
    } as unknown as PipelineApiService;

    const { component, getByPlaceholderText, getByText } = render(DurableAdminAgentTab, { props: { apiService: api } });
    await component.initialize();
    await waitFor(() => expect(getByText("Manage SmarterVote through the deployed agent")).toBeTruthy());

    await fireEvent.input(getByPlaceholderText("Ask the admin agent..."), {
      target: { value: "Review stale races" },
    });
    await fireEvent.click(getByText("Send"));

    expect(api.submitAdminAgentMessage).toHaveBeenCalledWith("conversation-1", "Review stale races");
    expect(localStorage.getItem("smartervote-admin-agent-conversation")).toBe("conversation-1");
  });
});
