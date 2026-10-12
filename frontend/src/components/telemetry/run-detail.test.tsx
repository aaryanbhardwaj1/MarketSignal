import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { TelemetryRunDetail } from "@/lib/api/contracts";
import research from "@/lib/api/__fixtures__/telemetry-run-6f18725e.json";
import standard from "@/lib/api/__fixtures__/telemetry-run-fbffdd6b.json";
import unavailable from "@/lib/api/__fixtures__/telemetry-run-288b6e18.json";
import { REASONING_NOTE, RunDetailView } from "./run-detail";

vi.mock("next/navigation", () => ({
  usePathname: () => "/w/NORTHSTAR/dev/telemetry/runs/x",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const render = (detail: unknown): string =>
  renderToStaticMarkup(<RunDetailView ws="NORTHSTAR" detail={detail as TelemetryRunDetail} />);

function hasKey(value: unknown, key: string): boolean {
  if (Array.isArray(value)) return value.some((v) => hasKey(v, key));
  if (value && typeof value === "object") {
    return Object.entries(value).some(([k, v]) => k === key || hasKey(v, key));
  }
  return false;
}

describe("RunDetailView", () => {
  it("always states that model reasoning is not recorded", () => {
    for (const fixture of [research, standard, unavailable]) {
      expect(render(fixture)).toContain(REASONING_NOTE);
    }
    expect(REASONING_NOTE).toBe("Model reasoning is not recorded; only observable actions, timings and outcomes are.");
  });

  it("never receives or renders answer content", () => {
    for (const fixture of [research, standard, unavailable]) {
      expect(hasKey(fixture, "content")).toBe(false);
      expect(hasKey(fixture, "answer_md")).toBe(false);
    }
    const html = render(research);
    expect(html).toContain("27 chunks streamed");
  });

  it("builds the observable timeline, tool calls and verification for a research run", () => {
    const html = render(research);
    expect(html).toContain("Run started");
    expect(html).toContain("Mode selected");
    expect(html).toContain("Research step 1: search_evidence called");
    expect(html).toContain("Analytics executed (step 2)");
    expect(html).toContain("Evidence pack created");
    expect(html).toContain("Final answer persisted");
    expect(html).toContain("Run completed");
    expect(html).toContain("describe_dataset");
    expect(html).toContain("Gaps &amp; unknowns");
    expect(html).toContain("Open result");
    expect(html).toContain("No retrieval trace");
  });

  it("shows a Redacted badge instead of arguments for redacted tool calls", () => {
    const detail = structuredClone(research) as unknown as TelemetryRunDetail;
    detail.tools = detail.tools.map((t, i) => (i === 1 ? { ...t, args: { redacted: true }, redacted: true } : t));
    const html = render(detail);
    expect(html).toContain(">Redacted<");
    expect(html.match(/Sanitized arguments/g)?.length).toBe(detail.tools.length - 1);
  });

  it("renders retrieval lanes and handles for a standard run", () => {
    const html = render(standard);
    expect(html).toContain("Retrieval performed");
    expect(html).toContain("NORTHSTAR/PERSO-PILOT@v1:S1.B8");
    expect(html).toContain("Embedding cache");
  });

  it("marks route, research and verification as not recorded for older runs", () => {
    const old = structuredClone(standard) as unknown as TelemetryRunDetail;
    old.run = { ...old.run, route: {}, route_reason: null, verification_disposition: null };
    old.verification = [];
    old.retrieval = null;
    old.timeline = [];
    old.run.mode = "research";
    old.agent = null;
    const html = render(old);
    expect(html).toContain("Not recorded for this run. Route decisions");
    expect(html).toContain("Not recorded for this run: no verification attempts");
    expect(html).toContain("No observable events were recorded");
    expect(html).not.toContain("Mode selected");
  });
});
