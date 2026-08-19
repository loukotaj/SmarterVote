import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PipelineApiService } from "$lib/services/pipelineApiService";
import type { ResearchProgramRow, ResearchProgramStatus } from "$lib/types";
import ResearchProgramTab from "./ResearchProgramTab.svelte";

const { getTraffic } = vi.hoisted(() => ({ getTraffic: vi.fn() }));

vi.mock("$lib/services/analyticsService", () => ({
  analyticsService: { getTraffic },
}));

function row(
  raceId: string,
  overrides: Partial<ResearchProgramRow> = {},
): ResearchProgramRow {
  const base: ResearchProgramRow = {
    race_id: raceId,
    manifest: {
      race_id: raceId,
      state: "Georgia",
      office: "us_senate",
      event_type: "regular_primary",
      primary_date: "2026-05-19",
      runoff_date: "2026-06-16",
      general_election_date: "2026-11-03",
      schedule_source_url: "https://example.gov/schedule",
    },
    checkpoint: {
      result_state: "stable",
      operator: "operator@example.com",
      official_result_url: "https://example.gov/results",
      first_checked_at: "2026-06-16T12:00:00Z",
      second_checked_at: "2026-06-16T18:30:00Z",
      advancing_names: ["Alex One", "Blair Two"],
      event_type: "primary_runoff",
      event_date: "2026-06-16",
      result_fingerprint: "fingerprint-1",
      last_reviewed_discovery_fingerprint: "fingerprint-1",
    },
    catalog: { source: "catalog", status: "published" },
    published: {
      source: "published",
      exists: true,
      contest_stage: "general_election",
    },
    draft: { source: "draft", exists: false, contest_stage: "unknown" },
    latest: {
      source: "published",
      exists: true,
      contest_stage: "general_election",
    },
    latest_source: "published",
    discovery_state: "complete",
    issue_state: "ready",
    cost: {
      run_count: 2,
      total_usd: 0.42,
      by_workflow: { discovery: 0.12, issues: 0.3 },
    },
  };
  return { ...base, ...overrides };
}

function programStatus(rows: ResearchProgramRow[]): ResearchProgramStatus {
  return {
    rows,
    summary: {
      coverage_count: 506,
      catalog_present_count: rows.length,
      checkpoint_count: 1,
      orphaned_catalog_count: 1,
      result_states: { stable: 1 },
      discovery_states: { review_required: 1 },
      issue_states: { ready: 1 },
      workflow_spend_usd: { discovery: 0.12, issues: 0.3 },
      total_pipeline_spend_usd: 0.42,
    },
    orphaned_catalog_race_ids: ["legacy-race-2026"],
    generated_at: "2026-08-18T12:00:00Z",
  };
}

function traffic() {
  return {
    configured: true,
    provider: "cloudflare" as const,
    hours: 720,
    pageviews: 18,
    visits: 10,
    pages_per_visit: 1.8,
    timeseries: [],
    top_pages: [
      { name: "/races/ga-senate-2026", pageviews: 10 },
      { name: "/races/ga-senate-2026?ref=home", pageviews: 5 },
      { name: "/about", pageviews: 3 },
    ],
    top_referrers: [],
    countries: [],
    devices: [],
    fetched_at: "2026-08-18T12:00:00Z",
    error: null,
  };
}

function api(status: ResearchProgramStatus) {
  return {
    getResearchProgramStatus: vi.fn().mockResolvedValue(status),
    recordResearchCheckpoint: vi.fn().mockResolvedValue({}),
  };
}

async function renderLoaded(
  service: ReturnType<typeof api>,
  status: ResearchProgramStatus,
) {
  service.getResearchProgramStatus.mockResolvedValue(status);
  const result = render(ResearchProgramTab, {
    props: { apiService: service as unknown as PipelineApiService },
  });
  await waitFor(() =>
    expect(result.container.textContent).not.toContain(
      "Loading research status",
    ),
  );
  return result;
}

beforeEach(() => {
  getTraffic.mockReset();
  getTraffic.mockResolvedValue(traffic());
});

afterEach(cleanup);

describe("ResearchProgramTab", () => {
  it("renders canonical coverage, demand, provenance, and orphan warnings", async () => {
    const primaryMissing = row("ar-supreme-court-2026", {
      manifest: {
        race_id: "ar-supreme-court-2026",
        state: "Arkansas",
        office: "state_supreme_court",
        event_type: "general_election",
        primary_date: null,
        runoff_date: null,
        general_election_date: "2026-03-03",
        schedule_source_url: "https://example.gov/court",
      },
      checkpoint: null,
      latest: { source: "draft", exists: false, contest_stage: "unknown" },
      latest_source: "draft",
      discovery_state: "waiting_event",
      issue_state: "blocked_roster",
      cost: { run_count: 0, total_usd: 0, by_workflow: {} },
    });
    const status = programStatus([row("ga-senate-2026"), primaryMissing]);
    const service = api(status);
    const { container, getByLabelText } = await renderLoaded(service, status);

    expect(service.getResearchProgramStatus).toHaveBeenCalledOnce();
    expect(getTraffic).toHaveBeenCalledWith(24 * 30);
    expect(container.textContent).toContain("506");
    expect(container.textContent).toContain("legacy-race-2026");
    expect(container.textContent).toContain("15");
    expect(container.textContent).toContain("manifest only");
    expect(container.textContent).toContain("Alex One, Blair Two");

    await fireEvent.input(getByLabelText("Search research races"), {
      target: { value: "Arkansas" },
    });
    expect(container.textContent).toContain("ar-supreme-court-2026");
    expect(container.textContent).not.toContain("ga-senate-2026");
  });

  it("saves a stable checkpoint for the explicitly selected event", async () => {
    const status = programStatus([row("ga-senate-2026")]);
    const service = api(status);
    const { container, getByLabelText, getByRole } = await renderLoaded(
      service,
      status,
    );

    await fireEvent.click(getByRole("button", { name: "Checkpoint" }));
    expect(container.textContent).toContain(
      "Result checkpoint · ga-senate-2026",
    );
    expect((getByLabelText("Verified event") as HTMLSelectElement).value).toBe(
      "runoff|2026-06-16",
    );

    await fireEvent.change(getByLabelText("Verified event"), {
      target: { value: "general|2026-11-03" },
    });
    await fireEvent.click(
      getByLabelText(
        "Discovery artifact reviewed against this exact result fingerprint",
      ),
    );
    await fireEvent.submit(getByRole("button", { name: "Save checkpoint" }));

    await waitFor(() =>
      expect(service.recordResearchCheckpoint).toHaveBeenCalledOnce(),
    );
    expect(service.recordResearchCheckpoint).toHaveBeenCalledWith(
      "ga-senate-2026",
      expect.objectContaining({
        result_state: "stable",
        event_type: "general_election",
        event_date: "2026-11-03",
        advancing_names: ["Alex One", "Blair Two"],
      }),
    );
    expect(service.getResearchProgramStatus).toHaveBeenCalledTimes(2);
  });

  it("keeps status usable when traffic fails and supports non-stable notes", async () => {
    getTraffic.mockRejectedValue(new Error("analytics unavailable"));
    const status = programStatus([row("ga-senate-2026")]);
    const service = api(status);
    const { container, getAllByLabelText, getByLabelText, getByRole } =
      await renderLoaded(service, status);

    expect(container.textContent).toContain("ga-senate-2026");
    await fireEvent.click(getByRole("button", { name: "Checkpoint" }));
    const stateSelects = getAllByLabelText("State", { selector: "select" });
    const checkpointState = stateSelects.find(
      (select) => (select as HTMLSelectElement).value === "stable",
    );
    expect(checkpointState).toBeDefined();
    await fireEvent.change(checkpointState!, {
      target: { value: "manual_review" },
    });
    await fireEvent.input(getByLabelText("Blocker / note"), {
      target: { value: "Awaiting certification" },
    });
    await fireEvent.submit(getByRole("button", { name: "Save checkpoint" }));

    await waitFor(() =>
      expect(service.recordResearchCheckpoint).toHaveBeenCalledWith(
        "ga-senate-2026",
        {
          result_state: "manual_review",
          operator: "operator@example.com",
          blocker: "Awaiting certification",
        },
      ),
    );
  });

  it("shows load and save failures without hiding the rest of the admin", async () => {
    const status = programStatus([row("ga-senate-2026")]);
    const service = api(status);
    service.getResearchProgramStatus.mockRejectedValueOnce(new Error("down"));
    const first = render(ResearchProgramTab, {
      props: { apiService: service as unknown as PipelineApiService },
    });
    await waitFor(() =>
      expect(first.container.textContent).toContain("Research status failed"),
    );
    cleanup();

    service.getResearchProgramStatus.mockResolvedValue(status);
    service.recordResearchCheckpoint.mockRejectedValueOnce(
      new Error("checkpoint rejected"),
    );
    const second = await renderLoaded(service, status);
    await fireEvent.click(second.getByRole("button", { name: "Checkpoint" }));
    await fireEvent.submit(
      second.getByRole("button", { name: "Save checkpoint" }),
    );
    await waitFor(() =>
      expect(second.container.textContent).toContain("checkpoint rejected"),
    );
    await fireEvent.click(second.getByRole("button", { name: "Close" }));
    expect(second.container.textContent).not.toContain("Result checkpoint ·");
  });
});
