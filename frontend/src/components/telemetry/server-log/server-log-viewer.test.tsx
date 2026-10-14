import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ServerLogEntry, ServerLogResponse } from "@/lib/api/contracts";
import { LOG_EMPTY_TEXT, ServerLogView, WORKER_NOTE, logFooterText } from "./server-log-viewer";

vi.mock("next/navigation", () => ({
  usePathname: () => "/w/NORTHSTAR/dev/telemetry",
  useParams: () => ({ ws: "NORTHSTAR" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const RUN = "288b6e18-8682-4d67-b35d-2a62edd76bb5";

const http: ServerLogEntry = {
  seq: 41,
  ts: "2026-10-14T09:05:03.042Z",
  level: "INFO",
  logger: "marketsignal.access",
  event: "http.request",
  kind: "http",
  request_id: "a1b2c3d4e5f6",
  run_id: null,
  workspace: "NORTHSTAR",
  http: { method: "POST", route: "/api/workspaces/{ws}/runs", path: "/api/workspaces/NORTHSTAR/runs", status: 503, duration_ms: 12.4 },
  fields: { noise: false },
};

const run: ServerLogEntry = {
  seq: 42,
  ts: "2026-10-14T09:05:04.100Z",
  level: "WARNING",
  logger: "marketsignal.runs",
  event: "run.degraded",
  kind: "run",
  request_id: "a1b2c3d4e5f6",
  run_id: RUN,
  workspace: "NORTHSTAR",
  http: null,
  fields: { termination_state: "generation_unavailable", tool_calls: 0 },
};

const meta: ServerLogResponse = {
  entries: [run, http],
  capacity: 2000,
  size: 812,
  dropped: 3,
  capture_errors: 0,
  oldest_seq: 1,
  latest_seq: 42,
  process_started_at: "2026-10-14T08:00:00Z",
  scope: "api_process",
  routes: ["/api/workspaces/{ws}/runs"],
  levels: { DEBUG: 0, INFO: 40, WARNING: 1, ERROR: 2, CRITICAL: 0 },
};

const render = (entries: ServerLogEntry[], expanded: number[] = []) =>
  renderToStaticMarkup(
    <ServerLogView entries={entries} meta={meta} ws="NORTHSTAR" expanded={new Set(expanded)} onToggle={() => {}} onFilter={() => {}} />,
  );

describe("ServerLogView", () => {
  it("renders HTTP and run rows with tones, ids and the run trace link", () => {
    const html = render([http, run]);
    expect(html).toContain("/api/workspaces/{ws}/runs");
    expect(html).toContain("POST");
    expect(html).toContain("503");
    expect(html).toContain("12 ms");
    expect(html).toContain("text-danger"); // 5xx
    expect(html).toContain(">WARN<");
    expect(html).toContain("run.degraded");
    expect(html).toContain("a1b2c3d4");
    expect(html).toContain("288b6e18");
    expect(html).toContain(`/w/NORTHSTAR/dev/telemetry/runs/${RUN}`);
    expect(html).toContain('aria-expanded="false"');
    // Fields stay collapsed until a row is expanded.
    expect(html).not.toContain("generation_unavailable");
  });

  it("shows sanitized fields of an expanded row", () => {
    const html = render([http, run], [42]);
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain("termination_state");
    expect(html).toContain("generation_unavailable");
  });

  it("states an honest empty state and the footer facts", () => {
    const html = render([]);
    expect(html).toContain(LOG_EMPTY_TEXT);
    expect(html).toContain("812/2,000 entries");
    expect(html).toContain("3 dropped");
    expect(html).toContain(WORKER_NOTE);
    expect(html).toContain("2 errors");
  });

  it("builds the footer only from response fields", () => {
    const text = logFooterText(meta);
    expect(text.startsWith("API process log · since ")).toBe(true);
    expect(text).not.toContain("capture errors");
    expect(logFooterText({ ...meta, capture_errors: 2 })).toContain("2 capture errors");
  });
});
