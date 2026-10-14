import { describe, expect, it } from "vitest";
import type { TelemetryRunDetail } from "@/lib/api/contracts";
import researchJson from "@/lib/api/__fixtures__/telemetry-run-6f18725e.json";
import standardJson from "@/lib/api/__fixtures__/telemetry-run-fbffdd6b.json";
import fallbackJson from "@/lib/api/__fixtures__/telemetry-run-288b6e18.json";
import { degradedInfo, deriveRunFlow, flowGantt, type FlowStage } from "./run-flow";

const research = researchJson as unknown as TelemetryRunDetail;
const standard = standardJson as unknown as TelemetryRunDetail;
const fallback = fallbackJson as unknown as TelemetryRunDetail;

const ids = (stages: FlowStage[]) => stages.map((s) => s.id);
const stage = (stages: FlowStage[], id: FlowStage["id"]) => stages.find((s) => s.id === id)!;
const meta = (s: FlowStage, label: string) => s.meta.find((m) => m.label === label)?.value;

describe("deriveRunFlow", () => {
  it("orders the stages of a research run with analytics, skipping retrieval it did not record", () => {
    const flow = deriveRunFlow(research);
    expect(ids(flow)).toEqual(["request", "routing", "tools", "analytics", "evidence", "generation", "verification", "final", "completed"]);
    const tools = stage(flow, "tools");
    expect(tools.calls).toHaveLength(5);
    expect(tools.calls?.map((c) => c.tool)).toContain("aggregate");
    expect(tools.duration_ms).toBe(9315);
    expect(tools.state).toBe("done");
    const analytics = stage(flow, "analytics");
    expect(analytics.resultIds).toEqual(["d3d38949-dbb4-422b-8963-6591b6cb5182"]);
    expect(meta(analytics, "Analytics calls")).toBe("2");
    expect(analytics.start_ms).toBe(2514.4);
    const routing = stage(flow, "routing");
    expect(routing.summary).toBe("Automatic → Research");
    expect(meta(routing, "Cues")).toBe("numeric, analytics");
    const gen = stage(flow, "generation");
    expect(meta(gen, "Model")).toBe("claude-sonnet-5-5");
    expect(gen.duration_ms).toBeCloseTo(8236.6);
    expect(gen.state).toBe("done");
    const verify = stage(flow, "verification");
    expect(verify.summary).toContain("2 repairs");
    expect(verify.state).toBe("done");
    expect(verify.duration_ms).toBeCloseTo(26.38);
    expect(stage(flow, "final").summary).toBe("Answer finalized with 13 citations");
    expect(stage(flow, "completed").state).toBe("done");
  });

  it("shows the evidence-only fallback honestly", () => {
    const flow = deriveRunFlow(fallback);
    expect(ids(flow)).toEqual(["request", "routing", "tools", "retrieval", "evidence", "generation", "final", "completed"]);
    expect(ids(flow)).not.toContain("verification");
    const retrieval = stage(flow, "retrieval");
    expect(retrieval.duration_ms).toBeCloseTo(116.2);
    expect(retrieval.start_ms).toBe(248.2);
    expect(meta(retrieval, "Trigger")).toContain("Fallback search");
    expect(meta(retrieval, "Kept")).toBe("24");
    const tools = stage(flow, "tools");
    expect(tools.state).toBe("degraded");
    expect(tools.calls).toEqual([]);
    expect(tools.summary).toContain("0 tool calls");
    const gen = stage(flow, "generation");
    expect(gen.state).toBe("failed");
    expect(meta(gen, "Model")).toBe("Not recorded");
    expect(meta(gen, "Failed attempts")).toBe("1");
    expect(stage(flow, "final").meta.find((m) => m.label === "Verification")?.value).toBe("Not verified");
    expect(stage(flow, "completed").state).toBe("degraded");
    expect(stage(flow, "request").start_ms).toBe(0); // clamped from -1.8
  });

  it("covers a standard run and an empty legacy record", () => {
    expect(ids(deriveRunFlow(standard))).toEqual(["request", "routing", "retrieval", "evidence", "generation", "verification", "final", "completed"]);
    const legacy: TelemetryRunDetail = {
      ...standard,
      run: { ...standard.run, route: {}, timings: {}, usage: {}, model: null, termination_state: null, flags: [] },
      agent: null,
      timeline: [],
      tools: [],
      verification: [],
      retrieval: null,
      analytics_result_ids: [],
    };
    expect(ids(deriveRunFlow(legacy))).toEqual(["request"]);
  });

  it("builds gantt rows only from stages with start and duration", () => {
    const rows = flowGantt(deriveRunFlow(research));
    expect(rows.map((r) => r.label)).toEqual(["Tool execution", "Evidence pack", "Generation", "Verification"]);
    expect(rows.every((r) => r.duration > 0 && r.start >= 0)).toBe(true);
  });
});

describe("degradedInfo", () => {
  it("lists termination state and flags with labels", () => {
    const info = degradedInfo(fallback);
    expect(info.degraded).toBe(true);
    expect(info.reasons.map((r) => r.code)).toEqual(["generation_unavailable", "PLANNER_UNAVAILABLE_FALLBACK", "LLM_SYNTHESIS_UNAVAILABLE"]);
    expect(info.reasons[0].label).toBe("Evidence only (live model unavailable)");
    expect(info.reasons[2].description).toContain("only the evidence found is shown");
    expect(degradedInfo(research).degraded).toBe(false);
  });
});
