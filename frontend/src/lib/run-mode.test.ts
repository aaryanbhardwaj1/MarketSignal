import { describe, expect, it } from "vitest";
import { runMode } from "./labels";
import { RUN_MODE_OPTIONS, describeRoute, modeLabel, toolSummaryText } from "./run-mode";
import type { RunRoute, ToolStep } from "./run-stream";

const route = (over: Partial<RunRoute> = {}): RunRoute => ({
  requested: "auto",
  personaDefault: "generalist",
  decided: "research",
  reason: "multi_source_cue",
  cues: [],
  ...over,
});

describe("RUN_MODE_OPTIONS", () => {
  it("lists auto first with help text for every mode", () => {
    expect(RUN_MODE_OPTIONS.map((o) => o.value)).toEqual(["auto", "standard", "research"]);
    for (const option of RUN_MODE_OPTIONS) expect(option.help.length).toBeGreaterThan(10);
  });
});

const label = (mode: string) => runMode(mode).label;

describe("describeRoute", () => {
  it("explains an auto-routed run with the plain-language reason, never the code or cues", () => {
    const d = describeRoute(route({ reason: "analytics_task", cues: ["numeric", "multi_class"] }));
    expect(d).toEqual({
      mode: label("research"),
      reason: `${label("auto")} mode chose ${label("research")}: the question needed computed figures.`,
      tone: "info",
    });
    expect(JSON.stringify(d)).not.toMatch(/analytics_task|multi_class|numeric/);
  });

  it("omits an unknown reason code", () => {
    expect(describeRoute(route({ decided: "standard", reason: "short_factual" }))?.reason).toBe(
      `${label("auto")} mode chose ${label("standard")}.`,
    );
  });

  it("says the user chose the mode", () => {
    expect(describeRoute(route({ requested: "standard", decided: "standard" }))).toEqual({
      mode: label("standard"),
      reason: `You chose ${label("standard")}.`,
      tone: "neutral",
    });
  });

  it("returns null without a route", () => {
    expect(describeRoute(null)).toBeNull();
  });
});

describe("mode vocabulary", () => {
  it("uses the labels.ts names everywhere", () => {
    expect(RUN_MODE_OPTIONS.map((o) => o.label)).toEqual([label("auto"), label("standard"), label("research")]);
    expect(modeLabel("research")).toBe(label("research"));
    expect(modeLabel("something_else")).toBe(label("standard"));
  });
});

describe("toolSummaryText", () => {
  const step = (over: Partial<ToolStep>): ToolStep => ({
    step: 1,
    callIndex: 0,
    tool: "search_evidence",
    kind: "search",
    summary: "",
    status: "running",
    resultCount: null,
    durationMs: null,
    errorCode: null,
    ...over,
  });

  it("prefers the server summary", () => {
    expect(toolSummaryText(step({ summary: 'Searching for "fit"' }))).toBe('Searching for "fit"');
  });

  it("falls back to the plain step label, then a label per kind, never the tool code", () => {
    expect(toolSummaryText(step({ kind: "analytics", tool: "aggregate" }))).toBe("Computed a figure");
    expect(toolSummaryText(step({ kind: "keyword", tool: "search_evidence_keyword" }))).toBe("Searched for exact terms");
    expect(toolSummaryText(step({ kind: "lookup", tool: "new_lookup" }))).toBe("Reading evidence passages");
    expect(toolSummaryText(step({ kind: "other", tool: "x_tool" }))).toBe("Research step");
  });
});
