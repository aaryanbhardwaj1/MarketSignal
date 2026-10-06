import { describe, expect, it } from "vitest";
import { RUN_MODE_OPTIONS, describeRoute, toolSummaryText } from "./run-mode";
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

describe("describeRoute", () => {
  it("labels an auto-routed research run with the reason", () => {
    expect(describeRoute(route())).toEqual({
      label: "Research mode · auto-routed: multi source cue",
      tone: "info",
    });
  });

  it("labels an auto-routed standard run", () => {
    expect(describeRoute(route({ decided: "standard", reason: "short_factual" }))?.label).toBe(
      "Standard mode · auto-routed: short factual",
    );
  });

  it("says chosen by you when the user picked the mode", () => {
    expect(describeRoute(route({ requested: "standard", decided: "standard" }))).toEqual({
      label: "Standard mode · chosen by you",
      tone: "neutral",
    });
    expect(describeRoute(route({ requested: "research" }))?.label).toBe("Research mode · chosen by you");
  });

  it("omits an empty reason and returns null without a route", () => {
    expect(describeRoute(route({ reason: "" }))?.label).toBe("Research mode · auto-routed");
    expect(describeRoute(null)).toBeNull();
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
    expect(toolSummaryText(step({ kind: "analytics", tool: "aggregate" }))).toBe("Computing analytics");
  });

  it("falls back to a fixed label per kind", () => {
    expect(toolSummaryText(step({ kind: "keyword" }))).toBe("Checking exact identifiers");
    expect(toolSummaryText(step({ kind: "lookup" }))).toBe("Opening evidence items");
    expect(toolSummaryText(step({ kind: "catalog" }))).toBe("Listing sources");
    expect(toolSummaryText(step({ kind: "search" }))).toBe("Searching evidence");
    expect(toolSummaryText(step({ kind: "other", tool: "x_tool" }))).toBe("x tool");
  });
});
