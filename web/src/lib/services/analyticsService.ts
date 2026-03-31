/**
 * Analytics and alert API service for the admin dashboard.
 * All requests route through the pipeline-client backend (Auth0-protected)
 * so the ADMIN_API_KEY never reaches the browser.
 */

import { apiStore } from "$lib/stores/apiStore";
import type { Alert, AnalyticsOverview, PipelineMetricsSummary, PipelineRunRecord, RaceAnalytics } from "$lib/types";
import { get } from "svelte/store";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

async function fetchAdmin<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const store = get(apiStore);
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (store.token) headers["Authorization"] = `Bearer ${store.token}`;

  const resp = await fetch(url.toString(), { headers });
  if (!resp.ok) {
    throw new Error(`Analytics API error ${resp.status}: ${await resp.text()}`);
  }
  return resp.json() as Promise<T>;
}

export const analyticsService = {
  async getOverview(hours = 24): Promise<AnalyticsOverview> {
    return fetchAdmin<AnalyticsOverview>("/analytics/overview", { hours });
  },

  async getRaces(hours = 24): Promise<{ races: RaceAnalytics[]; hours: number }> {
    return fetchAdmin<{ races: RaceAnalytics[]; hours: number }>("/analytics/races", { hours });
  },

  async getTimeseries(hours = 24, bucket = 60): Promise<{ timeseries: { time: string; requests: number }[] }> {
    return fetchAdmin("/analytics/timeseries", { hours, bucket });
  },

  async getAlerts(): Promise<{ alerts: Alert[]; total: number; unacknowledged: number }> {
    return fetchAdmin("/alerts");
  },

  async acknowledgeAlert(alertId: string): Promise<void> {
    const store = get(apiStore);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (store.token) headers["Authorization"] = `Bearer ${store.token}`;
    await fetch(`${API_BASE}/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
      method: "POST",
      headers,
    });
  },

  async getPipelineMetrics(limit = 50): Promise<{ records: PipelineRunRecord[]; count: number }> {
    return fetchAdmin<{ records: PipelineRunRecord[]; count: number }>("/pipeline/metrics", { limit });
  },

  async getPipelineMetricsSummary(): Promise<PipelineMetricsSummary> {
    return fetchAdmin<PipelineMetricsSummary>("/pipeline/metrics/summary");
  },
};
