import { afterEach, describe, expect, it, vi } from "vitest";
import type { ServerLogResponse, TelemetrySeries } from "../contracts";
import {
  getServerLogs,
  getTelemetrySeries,
  serverLogKeys,
  serverLogQuery,
  seriesQuery,
  telemetryKeys,
} from "./telemetry";

const series: TelemetrySeries = {
  window: { since: null, until: null },
  points: [],
  n: 0,
  truncated: false,
  test_runs_excluded: 2,
};

const logs: ServerLogResponse = {
  entries: [],
  capacity: 2000,
  size: 0,
  dropped: 0,
  capture_errors: 0,
  oldest_seq: null,
  latest_seq: null,
  process_started_at: "2026-10-14T00:00:00+00:00",
  scope: "api_process",
  routes: [],
  levels: { DEBUG: 0, INFO: 0, WARNING: 0, ERROR: 0, CRITICAL: 0 },
};

function stubFetch(body: unknown): ReturnType<typeof vi.fn> {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const calledUrl = (fetch: ReturnType<typeof vi.fn>): URL =>
  new URL(String(fetch.mock.calls[0]?.[0]));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("server log params and keys", () => {
  it("omits unset params, trims q and stringifies include_noise", () => {
    expect(serverLogQuery({})).toEqual({
      level: undefined,
      kind: undefined,
      method: undefined,
      status_class: undefined,
      route: undefined,
      q: undefined,
      include_noise: undefined,
      after_seq: undefined,
      limit: undefined,
    });
    const q = serverLogQuery({ q: "  run-42 ", include_noise: false, after_seq: 7, level: "ERROR" });
    expect(q.q).toBe("run-42");
    expect(q.include_noise).toBe("false");
    expect(q.after_seq).toBe(7);
    expect(q.level).toBe("ERROR");
    expect(serverLogQuery({ q: "   " }).q).toBeUndefined();
  });

  it("keys differ by params and share a stable prefix", () => {
    const a = serverLogKeys.list({ kind: "http" });
    const b = serverLogKeys.list({ kind: "run" });
    expect(a.slice(0, 2)).toEqual(serverLogKeys.all);
    expect(a).not.toEqual(b);
    expect(serverLogKeys.list({ kind: "http" })).toEqual(a);
  });

  it("sends the filters to /api/dev/logs", async () => {
    const fetch = stubFetch(logs);
    await expect(
      getServerLogs({ status_class: "5xx", route: "/api/workspaces/{ws}/runs", limit: 50 }),
    ).resolves.toEqual(logs);
    const url = calledUrl(fetch);
    expect(url.pathname).toBe("/api/dev/logs");
    expect(url.searchParams.get("status_class")).toBe("5xx");
    expect(url.searchParams.get("route")).toBe("/api/workspaces/{ws}/runs");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.has("include_noise")).toBe(false);
  });
});

describe("telemetry series", () => {
  it("builds the series query and key from the summary window plus limit", () => {
    const filters = { mode: "research" as const, include_test_runs: true, limit: 300 };
    expect(seriesQuery(filters)).toEqual({
      since: undefined,
      until: undefined,
      mode: "research",
      include_test_runs: "true",
      limit: 300,
    });
    expect(telemetryKeys.series("NORTHSTAR", filters)).toEqual([
      "workspace",
      "NORTHSTAR",
      "telemetry",
      "series",
      seriesQuery(filters),
    ]);
  });

  it("calls the workspace series endpoint", async () => {
    const fetch = stubFetch(series);
    await expect(getTelemetrySeries("NORTH STAR", { limit: 10 })).resolves.toEqual(series);
    const url = calledUrl(fetch);
    expect(url.pathname).toBe("/api/workspaces/NORTH%20STAR/telemetry/series");
    expect(url.searchParams.get("limit")).toBe("10");
  });
});
