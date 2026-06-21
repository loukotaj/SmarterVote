/**
 * Analytics and alert API service for the admin dashboard.
 * All requests route through the races-api backend (Auth0-protected)
 * so the ADMIN_API_KEY never reaches the browser.
 */

import { fetchWithAuth } from "$lib/stores/apiStore";
import { racesApiBase } from "$lib/config/api";
import type {
  Alert,
  AnalyticsOverview,
  PipelineMetricsSummary,
  PipelineRunRecord,
  RaceAnalytics,
  TrafficAnalytics,
} from "$lib/types";

const API_BASE = racesApiBase();

async function fetchAdmin<T>(
  path: string,
  params?: Record<string, string | number>
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) =>
      url.searchParams.set(k, String(v))
    );
  }
  const resp = await fetchWithAuth(url.toString(), {
    headers: { "Content-Type": "application/json" },
  });
  if (!resp.ok) {
    throw new Error(`Analytics API error ${resp.status}: ${await resp.text()}`);
  }
  return resp.json() as Promise<T>;
}

export const analyticsService = {
  async getOverview(hours = 24): Promise<AnalyticsOverview> {
    return fetchAdmin<AnalyticsOverview>("/analytics/overview", { hours });
  },

  async getTraffic(hours = 24): Promise<TrafficAnalytics> {
    return fetchAdmin<TrafficAnalytics>("/analytics/traffic", { hours });
  },

  async getRaces(
    hours = 24
  ): Promise<{ races: RaceAnalytics[]; hours: number }> {
    return fetchAdmin<{ races: RaceAnalytics[]; hours: number }>(
      "/analytics/races",
      { hours }
    );
  },

  async getTimeseries(
    hours = 24,
    bucket = 60
  ): Promise<{ timeseries: { time: string; requests: number }[] }> {
    return fetchAdmin("/analytics/timeseries", { hours, bucket });
  },

  async getAlerts(): Promise<{
    alerts: Alert[];
    total: number;
    unacknowledged: number;
  }> {
    return fetchAdmin("/alerts");
  },

  async acknowledgeAlert(alertId: string): Promise<void> {
    const resp = await fetchWithAuth(
      `${API_BASE}/alerts/${encodeURIComponent(alertId)}/acknowledge`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }
    );
    if (!resp.ok) throw new Error(`Acknowledge failed ${resp.status}`);
  },

  async acknowledgeAllAlerts(): Promise<{ acknowledged_count: number }> {
    const resp = await fetchWithAuth(`${API_BASE}/alerts/acknowledge-all`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!resp.ok) throw new Error(`Ack-all failed ${resp.status}`);
    return resp.json();
  },

  async getPipelineMetrics(
    limit = 50
  ): Promise<{ records: PipelineRunRecord[]; count: number }> {
    return fetchAdmin<{ records: PipelineRunRecord[]; count: number }>(
      "/pipeline/metrics",
      { limit }
    );
  },

  async getPipelineMetricsSummary(
    hours?: number
  ): Promise<PipelineMetricsSummary> {
    return fetchAdmin<PipelineMetricsSummary>(
      "/pipeline/metrics/summary",
      hours ? { hours } : undefined
    );
  },
};
