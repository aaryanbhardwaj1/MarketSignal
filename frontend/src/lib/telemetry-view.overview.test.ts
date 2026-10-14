import { describe, expect, it } from "vitest";
import type { TelemetrySeries } from "@/lib/api/contracts";
import seriesFixture from "@/lib/api/__fixtures__/telemetry-series.json";
import {
  binRate,
  binSeries,
  countByValue,
  formatCompact,
  latencyDots,
  mean,
  median,
  modeStageMedians,
  outcomeBuckets,
  outcomeOf,
  parseTab,
  seriesSpan,
  toolProblems,
} from "./telemetry-view";

const series = seriesFixture as unknown as TelemetrySeries;
const point = series.points[0];

describe("parseTab", () => {
  it("reads known tabs and falls back to the overview", () => {
    expect(parseTab(new URLSearchParams("tab=runs"))).toBe("runs");
    expect(parseTab(new URLSearchParams("tab=logs"))).toBe("logs");
    expect(parseTab(new URLSearchParams("tab=nope"))).toBe("overview");
    expect(parseTab(new URLSearchParams(""))).toBe("overview");
  });
});

describe("median and mean", () => {
  it("ignores values that were not recorded and never invents zero", () => {
    expect(median([3, null, 1, undefined, 2])).toBe(2);
    expect(median([4, 1, 3, 2])).toBe(2.5);
    expect(median([null, undefined])).toBeNull();
    expect(mean([])).toBeNull();
    expect(mean([1, 2, 3])).toBe(2);
  });
});

describe("latencyDots", () => {
  it("keeps the recorded sequence position and skips runs without a total", () => {
    const pts = [
      { ...point, id: "a", total_ms: 100 },
      { ...point, id: "b", total_ms: null },
      { ...point, id: "c", total_ms: 300 },
    ];
    expect(latencyDots(pts).map((d) => [d.seq, d.id, d.ms])).toEqual([
      [1, "a", 100],
      [3, "c", 300],
    ]);
  });

  it("covers every fixture run with a recorded total", () => {
    expect(latencyDots(series.points)).toHaveLength(series.points.filter((p) => p.total_ms != null).length);
  });
});

describe("seriesSpan", () => {
  it("describes a single-day window by time of day, in UTC", () => {
    expect(seriesSpan(series.points)).toBe("Oct 6, 2026, 16:30–23:06 UTC");
  });
  it("uses a date range across days and null when empty", () => {
    expect(seriesSpan([{ created_at: "2026-10-01T10:00:00Z" }, { created_at: "2026-10-06T10:00:00Z" }])).toBe("Oct 1, 2026 – Oct 6, 2026");
    expect(seriesSpan([])).toBeNull();
  });
});

describe("binSeries / binRate", () => {
  it("reduces equal-count groups and skips groups with nothing recorded", () => {
    expect(binSeries([1, 3, null, null, 5, 7], (g) => mean(g), 3)).toEqual([2, 6]);
    expect(binSeries([], (g) => mean(g))).toEqual([]);
    expect(binSeries([1, 2], (g) => mean(g), 10)).toEqual([1, 2]);
  });
  it("computes per-bin rates", () => {
    expect(binRate([true, false, true, true], (b) => b, 2)).toEqual([0.5, 1]);
  });
});

describe("modeStageMedians", () => {
  it("orders research stages with research steps first and omits unrecorded stages", () => {
    const research = modeStageMedians(series.points, "research");
    expect(research[0].label).toBe("Research steps");
    expect(research.every((s) => s.ms >= 0 && s.n > 0)).toBe(true);
    const standard = modeStageMedians(series.points, "standard");
    expect(standard.map((s) => s.key)).not.toContain("agent");
    expect(standard[0].label).toBe("Retrieval");
  });
  it("returns nothing for a mode with no runs", () => {
    expect(modeStageMedians(series.points.filter((p) => p.mode === "standard"), "research")).toEqual([]);
  });
});

describe("outcomeOf", () => {
  const base = { status: "completed", termination_state: "completed", disposition: null } as const;
  it("lets the run status win over termination and verification", () => {
    expect(outcomeOf({ ...base, status: "failed" })).toBe("failed");
    expect(outcomeOf({ ...base, status: "cancelled" })).toBe("cancelled");
    expect(outcomeOf({ ...base, status: "interrupted" })).toBe("cancelled");
  });
  it("maps termination states and verification fallback", () => {
    expect(outcomeOf({ ...base, termination_state: "generation_unavailable", disposition: "fallback" })).toBe("generation_unavailable");
    expect(outcomeOf({ ...base, termination_state: "no_relevant_evidence" })).toBe("no_relevant_evidence");
    expect(outcomeOf({ ...base, termination_state: "tool_failure" })).toBe("tool_failure");
    expect(outcomeOf({ ...base, termination_state: "timeout" })).toBe("failed");
    expect(outcomeOf({ ...base, termination_state: "retrieval_degraded" })).toBe("limited");
    expect(outcomeOf({ ...base, disposition: "fallback" })).toBe("verification_fallback");
    expect(outcomeOf({ ...base, disposition: "repaired" })).toBe("completed");
    expect(outcomeOf({ ...base, termination_state: null })).toBe("completed");
  });
});

describe("outcomeBuckets", () => {
  it("counts every run once and lists empty outcomes separately", () => {
    const { present, absent } = outcomeBuckets(series.points);
    expect(present.reduce((a, b) => a + b.n, 0)).toBe(series.points.length);
    expect(present.map((b) => b.key)).toContain("generation_unavailable");
    expect(absent).toContain("Cancelled");
    expect(absent).not.toContain("Running");
  });
  it("counts fallback answers filed under another outcome", () => {
    const pts = [
      { ...point, status: "completed", termination_state: "generation_unavailable", disposition: "fallback" as const },
      { ...point, status: "completed", termination_state: "completed", disposition: "fallback" as const },
    ];
    const { present, fallbackElsewhere } = outcomeBuckets(pts);
    expect(fallbackElsewhere).toBe(1);
    expect(present.map((b) => b.key)).toEqual(["verification_fallback", "generation_unavailable"]);
  });
});

describe("countByValue", () => {
  it("counts recorded values in ascending order", () => {
    expect(countByValue([2, 1, null, 2, 5])).toEqual([
      { value: 1, n: 1 },
      { value: 2, n: 2 },
      { value: 5, n: 1 },
    ]);
  });
});

describe("toolProblems / formatCompact", () => {
  it("describes non-ok tool calls in words", () => {
    expect(toolProblems({ truncated: 13, error: 1, denied: 2, timeout: 0 })).toBe("1 error · 2 denied · 13 truncated");
    expect(toolProblems({ truncated: 0, error: 0, denied: 0, timeout: 0 })).toBeNull();
  });
  it("formats compact counts and keeps missing values as a dash", () => {
    expect(formatCompact(2_619_649)).toBe("2.6M");
    expect(formatCompact(940)).toBe("940");
    expect(formatCompact(null)).toBe("-");
  });
});
