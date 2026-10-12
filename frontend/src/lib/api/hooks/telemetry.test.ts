import { afterEach, describe, expect, it, vi } from "vitest";
import type { TelemetryRunDetail, TelemetryRunRow, TelemetrySummary, Page } from "../contracts";
import runDetail from "../__fixtures__/telemetry-run-41eb18bd.json";
import standardDetail from "../__fixtures__/telemetry-run-fbffdd6b.json";
import runs from "../__fixtures__/telemetry-runs.json";
import summary from "../__fixtures__/telemetry-summary.json";
import { getTelemetryRun, getTelemetryRuns, getTelemetrySummary } from "./telemetry";

// JSON imports widen literal unions, so the captured payloads are cast to the contract types;
// the assertions below check the essentials the pages rely on.
const typedSummary: TelemetrySummary = summary as TelemetrySummary;
const typedRuns: Page<TelemetryRunRow> = runs as Page<TelemetryRunRow>;
const typedDetail: TelemetryRunDetail = runDetail as TelemetryRunDetail;

function stubFetch(body: unknown): ReturnType<typeof vi.fn> {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

function calledUrl(fetch: ReturnType<typeof vi.fn>): URL {
  return new URL(String(fetch.mock.calls[0]?.[0]));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("telemetry getters", () => {
  it("sends the summary window and the test-run toggle as query parameters", async () => {
    const fetch = stubFetch(typedSummary);
    await expect(
      getTelemetrySummary("NORTHSTAR", { since: "2026-10-01T00:00:00Z", include_test_runs: false }),
    ).resolves.toEqual(summary);
    const url = calledUrl(fetch);
    expect(url.pathname).toBe("/api/workspaces/NORTHSTAR/telemetry/summary");
    expect(url.searchParams.get("since")).toBe("2026-10-01T00:00:00Z");
    expect(url.searchParams.get("include_test_runs")).toBe("false");
    expect(url.searchParams.has("mode")).toBe(false);
  });

  it("passes run filters and the opaque cursor through", async () => {
    const fetch = stubFetch(typedRuns);
    await getTelemetryRuns("NORTHSTAR", { degraded: true, disposition: "fallback", limit: 5 }, "abc");
    const params = calledUrl(fetch).searchParams;
    expect(params.get("degraded")).toBe("true");
    expect(params.get("disposition")).toBe("fallback");
    expect(params.get("limit")).toBe("5");
    expect(params.get("cursor")).toBe("abc");
  });

  it("encodes the run id in the detail path", async () => {
    const fetch = stubFetch(typedDetail);
    await getTelemetryRun("NORTHSTAR", typedDetail.run.id);
    expect(calledUrl(fetch).pathname).toBe(
      `/api/workspaces/NORTHSTAR/telemetry/runs/${typedDetail.run.id}`,
    );
  });
});

describe("captured telemetry fixtures", () => {
  it("summary reports n with every percentile and an estimated cost basis", () => {
    for (const stage of Object.values(typedSummary.latency_ms.stages)) {
      expect(typeof stage.n).toBe("number");
    }
    expect(typedSummary.cost.basis).toBe("list_prices_from_persisted_usage");
    expect(typedSummary.test_runs_excluded).toBeGreaterThanOrEqual(0);
  });

  it("run detail carries no answer text, token text or reasoning", () => {
    for (const detail of [typedDetail, standardDetail as TelemetryRunDetail]) {
      const raw = JSON.stringify(detail);
      expect(raw).not.toMatch(/"(content|text|span|thinking|reasoning|trace)"\s*:/);
      expect(detail.timeline.some((e) => e.kind === "tokens")).toBe(true);
    }
  });
});
