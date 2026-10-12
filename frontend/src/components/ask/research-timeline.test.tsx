import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ToolStep } from "@/lib/run-stream";
import { ResearchTimeline } from "./research-timeline";
import { RouteBadge } from "./route-badge";

const step = (over: Partial<ToolStep> = {}): ToolStep => ({
  step: 1,
  callIndex: 0,
  tool: "search_evidence",
  kind: "search",
  summary: 'Searching customer evidence for "fit complaints"',
  status: "ok",
  resultCount: 8,
  durationMs: 412,
  errorCode: null,
  ...over,
});

const render = (tools: ToolStep[], running = true, phase: Parameters<typeof ResearchTimeline>[0]["phase"] = null) =>
  renderToStaticMarkup(<ResearchTimeline tools={tools} phase={phase} running={running} />);

describe("ResearchTimeline", () => {
  it("renders nothing without tool calls", () => {
    expect(render([])).toBe("");
  });

  it("renders a compact step line", () => {
    const html = render([step()]);
    expect(html).toContain("Research steps");
    expect(html).toContain("Step 1");
    expect(html).toContain("Searching customer evidence for &quot;fit complaints&quot;");
    expect(html).toContain("8 results");
    expect(html).toContain("412 ms");
    expect(html).toContain("<ol");
  });

  it("labels analytics steps and shows the plain-text summary", () => {
    const html = render([
      step({
        tool: "aggregate",
        kind: "analytics",
        summary: "Computing mean(nps) by region on SURVEY-2026:1 <b>x</b>",
        resultCount: 5,
      }),
    ]);
    expect(html).toContain("Analytics");
    expect(html).toContain("Computing mean(nps) by region on SURVEY-2026:1 &lt;b&gt;x&lt;/b&gt;");
    expect(render([step()])).not.toContain("Analytics");
  });

  it("uses singular result and in-progress marker", () => {
    const html = render([step({ status: "running", resultCount: null, durationMs: null })]);
    expect(html).toContain("In progress");
    expect(html).not.toContain("results");
    expect(render([step({ resultCount: 1 })])).toContain("1 result<");
  });

  it("visibly marks error, denied and timeout calls with the error code", () => {
    const html = render([
      step({ callIndex: 0, status: "error", errorCode: "TOOL_FAILED", resultCount: null }),
      step({ callIndex: 1, status: "denied", errorCode: "POLICY_DENIED", resultCount: null }),
      step({ callIndex: 2, status: "timeout", errorCode: "TOOL_TIMEOUT", resultCount: null }),
    ]);
    expect(html).toContain("Failed");
    expect(html).toContain("Denied");
    expect(html).toContain("Timed out");
    expect(html).toContain("TOOL_FAILED");
    expect(html).toContain("POLICY_DENIED");
    expect(html).toContain("TOOL_TIMEOUT");
  });

  it("renders the summary as plain text, never markdown or HTML", () => {
    const html = render([
      step({ summary: 'Searching for "<script>alert(1)</script> **bold** [x](http://evil)"' }),
    ]);
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<strong>");
    expect(html).not.toContain("<a ");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("**bold**");
  });

  it("shows the current phase while running only", () => {
    expect(render([step()], true, "analyzing")).toContain("Analyzing");
    expect(render([step()], false, "analyzing")).not.toContain("Analyzing");
  });

  it("is open while running and collapsed after the run", () => {
    expect(render([step()], true)).toMatch(/<details[^>]* open/);
    expect(render([step()], false)).not.toMatch(/<details[^>]* open/);
  });
});

describe("RouteBadge", () => {
  const route = {
    requested: "auto",
    personaDefault: "generalist",
    decided: "research" as const,
    reason: "multi_source_cue",
    cues: ["compare"],
  };

  it("shows the auto-routed badge", () => {
    const html = renderToStaticMarkup(<RouteBadge route={route} />);
    expect(html).toContain("Research mode · auto-routed: multi source cue");
    expect(html).toContain("compare");
  });

  it("shows the user choice", () => {
    const html = renderToStaticMarkup(
      <RouteBadge route={{ ...route, requested: "standard", decided: "standard", cues: [] }} />,
    );
    expect(html).toContain("Standard mode · chosen by you");
  });

  it("renders nothing without a route", () => {
    expect(renderToStaticMarkup(<RouteBadge route={null} />)).toBe("");
  });
});
