import { describe, expect, it } from "vitest";
import type { TimelineEntry } from "@/lib/api/contracts";
import {
  DEFAULT_VIEW,
  buildTimeline,
  formatRate,
  formatOffset,
  formatShare,
  isRedacted,
  parseViewState,
  runFilters,
  serializeViewState,
  stageSegments,
  windowSince,
} from "./telemetry-view";

const params = (qs: string) => new URLSearchParams(qs);

describe("stageSegments", () => {
  it("sums to at most the recorded total and adds the unattributed remainder", () => {
    const segs = stageSegments("standard", {
      total_ms: 6371.2,
      retrieval_ms: 188.1,
      pack_ms: 3.3,
      synthesis_ms_1: 5986.6,
      verify_ms_1: 23.09,
      first_token_ms: 2378.6,
      attempts: 1,
    });
    expect(segs.map((s) => s.label)).toEqual(["Retrieval", "Evidence pack", "Synthesis", "Verification", "Other (unattributed)"]);
    const total = segs.reduce((a, s) => a + s.ms, 0);
    expect(total).toBeCloseTo(6371.2, 5);
    expect(segs.reduce((a, s) => a + s.pct, 0)).toBeLessThanOrEqual(100.0001);
  });

  it("omits stages that were not recorded instead of zero-filling them", () => {
    const segs = stageSegments("research", { total_ms: 647.7, agent_ms: 196.3, retrieval_ms: 116.2, pack_ms: 2.4 });
    expect(segs.map((s) => s.key)).toEqual(["agent_ms", "retrieval_ms", "pack_ms", "other"]);
    expect(segs.some((s) => s.key.startsWith("synthesis") || s.key.startsWith("verify"))).toBe(false);
  });

  it("never exceeds 100% when stages sum past the total", () => {
    const segs = stageSegments("standard", { total_ms: 100, retrieval_ms: 80, pack_ms: 40 });
    expect(segs.find((s) => s.key === "other")).toBeUndefined();
    expect(segs.reduce((a, s) => a + s.pct, 0)).toBeCloseTo(100, 5);
  });

  it("labels regeneration attempts separately", () => {
    const segs = stageSegments("standard", { total_ms: 10, synthesis_ms_1: 3, verify_ms_1: 1, synthesis_ms_2: 4, verify_ms_2: 1 });
    expect(segs.map((s) => s.label)).toContain("Synthesis (attempt 2)");
  });

  it("returns nothing when no timings were recorded", () => {
    expect(stageSegments("standard", {})).toEqual([]);
  });
});

describe("view state", () => {
  it("round-trips through the URL and drops defaults", () => {
    const state = { ...DEFAULT_VIEW, window: "7d" as const, includeTestRuns: true, mode: "research" as const, outcome: "term:completed" };
    const qs = serializeViewState(state);
    expect(parseViewState(params(qs))).toEqual(state);
    expect(serializeViewState(DEFAULT_VIEW)).toBe("");
  });

  it("ignores unknown values", () => {
    expect(parseViewState(params("window=90d&mode=x&outcome=drop table&disposition=nope"))).toEqual(DEFAULT_VIEW);
  });

  it("excludes test-harness runs by default and maps the outcome filter", () => {
    const f = runFilters({ ...DEFAULT_VIEW, outcome: "status:failed", degraded: "no" }, undefined);
    expect(f.include_test_runs).toBe(false);
    expect(f.status).toBe("failed");
    expect(f.termination_state).toBeUndefined();
    expect(f.degraded).toBe(false);
  });

  it("floors the window start to the minute so query keys are stable", () => {
    const now = new Date("2026-10-12T10:15:42.123Z");
    expect(windowSince("7d", now)).toBe("2026-10-05T10:15:00.000Z");
    expect(windowSince("all", now)).toBeUndefined();
  });
});

describe("formatRate", () => {
  it("always states the denominator", () => {
    expect(formatRate(0.0688, 407)).toBe("6.9% of 407 runs");
    expect(formatRate(0, 0)).toBe("No runs in window");
  });
});

describe("buildTimeline", () => {
  const entries: TimelineEntry[] = [
    { t_ms: 5.4, kind: "run_started", label: "Run started", detail: { mode: "research", persona: "generalist" } },
    { t_ms: 12.4, kind: "status", label: "Planning the research", detail: { phase: "planning" } },
    { t_ms: 2514.4, kind: "tool_started", label: "Describing datasets", detail: { step: 1, call_index: 0, tool: "describe_dataset" } },
    { t_ms: 2525.4, kind: "tool_started", label: "Searching", detail: { step: 1, call_index: 1, tool: "search_evidence" } },
    { t_ms: 2632.4, kind: "tool_completed", label: "ok", detail: { step: 1, call_index: 0, tool: "describe_dataset", status: "ok", duration_ms: 24, result_count: 9 } },
    { t_ms: 2637.4, kind: "tool_completed", label: "ok", detail: { step: 1, call_index: 1, tool: "search_evidence", status: "ok", result_count: 10 } },
    { t_ms: 5466.4, kind: "tool_started", label: "Computing count", detail: { step: 2, call_index: 0, tool: "aggregate" } },
    { t_ms: 5625.4, kind: "tool_completed", label: "ok", detail: { step: 2, call_index: 0, tool: "aggregate", status: "ok", result_count: 1 } },
    { t_ms: 9397.4, kind: "evidence", label: "Evidence pack: 12 passages", detail: { item_count: 12, result_count: 1 } },
    { t_ms: 13010.4, kind: "tokens", label: "Streamed 27 chunks", detail: { count: 27, citations: 13, attempt: 1, last_t_ms: 17658.4 } },
    { t_ms: 17740.4, kind: "final", label: "Answer finalized", detail: { citations: 13, passed: true } },
    { t_ms: 17767.4, kind: "done", label: "Done: completed", detail: { termination_state: "completed" } },
  ];

  it("merges tool start/complete pairs and orders by time", () => {
    const steps = buildTimeline(entries, "research");
    expect(steps.map((s) => s.title)).toEqual([
      "Run started",
      "Mode selected",
      "Research planning started",
      "Research step 1: describe_dataset called",
      "Research step 1: search_evidence called",
      "Analytics executed (step 2)",
      "Evidence pack created",
      "Answer streamed",
      "Final answer persisted",
      "Run completed",
    ]);
    const search = steps.find((s) => s.tool === "search_evidence");
    expect(search?.end_ms).toBe(2637.4);
    expect(search?.status).toBe("ok");
    expect(steps.find((s) => s.title === "Answer streamed")?.end_ms).toBe(17658.4);
  });

  it("uses the recorded tool duration, not the gap between events", () => {
    const steps = buildTimeline(entries, "research");
    const describe = steps.find((s) => s.tool === "describe_dataset");
    expect(describe?.duration_ms).toBe(24);
    const streamed = steps.find((s) => s.title === "Answer streamed");
    expect(streamed?.duration_ms).toBeCloseTo(17658.4 - 13010.4);
    expect(steps.find((s) => s.title === "Run started")?.duration_ms).toBeNull();
  });

  it("names the standard search step as retrieval and never surfaces content", () => {
    const steps = buildTimeline(
      [
        { t_ms: 44.7, kind: "tool_started", label: "hybrid search", detail: { step: 1, tool: "search_evidence" } },
        { t_ms: 240.7, kind: "tool_completed", label: "ok", detail: { step: 1, tool: "search_evidence", status: "ok", result_count: 156 } },
      ],
      "standard",
    );
    expect(steps).toHaveLength(1);
    expect(steps[0].title).toBe("Retrieval performed");
    expect(steps[0].detail).toBe("hybrid search · 156 results");
  });

  it("omits Mode selected when the run did not record a mode", () => {
    const steps = buildTimeline([{ t_ms: 1, kind: "run_started", label: "Run started", detail: null }], "standard");
    expect(steps.map((s) => s.kind)).toEqual(["start"]);
  });
});

describe("isRedacted", () => {
  it("detects both the API flag and purge-redacted args", () => {
    expect(isRedacted({ args: { redacted: true }, redacted: false })).toBe(true);
    expect(isRedacted({ args: { query: "x" }, redacted: true })).toBe(true);
    expect(isRedacted({ args: { query: "x" }, redacted: false })).toBe(false);
  });
});

describe("formatShare", () => {
  it("never shows a recorded stage as 0.0%", () => {
    expect(formatShare(0.04)).toBe("<0.1%");
    expect(formatShare(0)).toBe("0.0%");
    expect(formatShare(52.44)).toBe("52.4%");
  });
});

describe("fallback retrieval and warnings", () => {
  it("labels an un-planned search in a research run as retrieval and humanizes warnings", () => {
    const steps = buildTimeline(
      [
        { t_ms: -1.6, kind: "run_started", label: "Run started", detail: { mode: "research" } },
        { t_ms: 248, kind: "tool_started", label: "hybrid search", detail: { step: 2, tool: "search_evidence" } },
        { t_ms: 364, kind: "tool_completed", label: "ok", detail: { step: 2, tool: "search_evidence", status: "ok", duration_ms: 116 } },
        { t_ms: 572, kind: "warning", label: "warning", detail: { code: "LLM_SYNTHESIS_UNAVAILABLE" } },
      ],
      "research",
    );
    expect(steps.map((s) => s.title)).toContain("Retrieval performed");
    expect(steps.find((s) => s.kind === "warning")?.detail).toContain("(LLM_SYNTHESIS_UNAVAILABLE)");
    expect(formatOffset(steps[0].t_ms)).toBe("t-2 ms");
    expect(formatOffset(1234.4)).toBe("t+1,234 ms");
  });
});
