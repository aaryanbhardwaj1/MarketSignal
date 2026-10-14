import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { TelemetryRunRow, TelemetrySeries, TelemetrySummaryWithOutcomes } from "@/lib/api/contracts";
import summaryFixture from "@/lib/api/__fixtures__/telemetry-summary.json";
import runsFixture from "@/lib/api/__fixtures__/telemetry-runs.json";
import seriesFixture from "@/lib/api/__fixtures__/telemetry-series.json";
import { RunsTable } from "../runs-table";
import { TelemetryOverview, type SeriesState } from "./telemetry-overview";

vi.mock("next/navigation", () => ({
  usePathname: () => "/w/NORTHSTAR/dev/telemetry",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const summary = summaryFixture as unknown as TelemetrySummaryWithOutcomes;
const series = seriesFixture as unknown as TelemetrySeries;
const loaded: SeriesState = { data: series, pending: false, error: null, retry: () => {} };
const render = (s: TelemetrySummaryWithOutcomes = summary, state: SeriesState = loaded) =>
  renderToStaticMarkup(<TelemetryOverview summary={s} series={state} />);

describe("TelemetryOverview", () => {
  it("shows the six headline figures from persisted telemetry", () => {
    const html = render();
    for (const label of ["Total runs", "Success rate", "Standard p50 latency", "Total tokens", "Estimated cost", "Verification fallback"]) {
      expect(html).toContain(label);
    }
    expect(html).toContain("407");
    expect(html).toContain("215 Standard · 192 Research");
    expect(html).toContain("5.41 s");
    expect(html).toContain("$8.93");
    expect(html).toContain("per run · estimate");
    expect(html).toContain("Regeneration 6.9%");
  });

  it("answers four questions with charts and labels the run-order axis honestly", () => {
    const html = render();
    for (const q of ["How long does a run take?", "Where does the time go?", "How did runs end?", "Which research tools run?", "How many model calls per run?"]) {
      expect(html).toContain(q);
    }
    expect(html).toContain("in the order recorded (Oct 6, 2026, 16:30–23:06 UTC)");
    expect(html).toContain("The x-axis is run order, not elapsed time");
    expect(html).toContain("Live model unavailable");
    expect(html).toContain("None in this window:");
    expect(html).toContain("get_evidence: 13 truncated");
  });

  it("shows secondary metrics, the cost basis and the glossary", () => {
    const html = render();
    expect(html).toContain("Evidence pack size p50 / p95");
    expect(html).toContain("Planner fallback");
    expect(html).toContain("It is not a billed amount");
    expect(html).toContain("Metric glossary");
  });

  it("keeps headline figures when the per-run series fails, without sparklines", () => {
    const html = render(summary, { data: undefined, pending: false, error: new Error("boom"), retry: () => {} });
    expect(html).toContain("Per-run telemetry could not be loaded");
    expect(html).toContain("Total runs");
    expect(html).not.toContain("equal groups of runs");
  });

  it("says when charts cover only the most recent runs", () => {
    const html = render(summary, { ...loaded, data: { ...series, truncated: true } });
    expect(html).toContain(`Charts show the ${series.n} most recent runs`);
  });

  it("renders honest empty states rather than zero-filled charts", () => {
    const empty = { ...series, points: [], n: 0 };
    const noTools = { ...summary, tool_calls: { ...summary.tool_calls, total: 0, by_tool: [] } };
    const html = render(noTools, { ...loaded, data: empty });
    expect(html).toContain("No run in this window recorded a total latency.");
    expect(html).toContain("No stage timings were recorded in this window.");
    expect(html).toContain("No research tool calls in this window.");
  });
});

describe("RunsTable", () => {
  const rows = (runsFixture as unknown as { items: TelemetryRunRow[] }).items;
  it("renders dense rows with short mono ids linking to run detail", () => {
    const html = renderToStaticMarkup(<RunsTable rows={rows} runHref={(r) => `/w/NORTHSTAR/dev/telemetry/runs/${r.id}`} onOpen={() => {}} />);
    expect(html).toContain('href="/w/NORTHSTAR/dev/telemetry/runs/288b6e18-8682-4d67-b35d-2a62edd76bb5"');
    expect(html).toContain(">288b6e18<");
    expect(html).toContain("Live model unavailable");
    expect(html).toContain("Ended as: Evidence only (live model unavailable)");
    expect(html).toContain("Cost (est.)");
    expect(html).toContain('tabindex="0"');
  });
});
