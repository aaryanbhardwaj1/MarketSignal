import { describe, expect, it } from "vitest";
import type { AgentTraceStep, RunRecord } from "./api/contracts";
import { liveStages, replaySchedule, replayStages, savedStages } from "./research-stages";
import { initialRunStreamState, type RunStreamState, type ToolStep } from "./run-stream";

const baseRun = (over: Partial<RunRecord> = {}): RunRecord => ({
  run_id: "r1",
  conversation_id: "c1",
  mode: "standard" as RunRecord["mode"],
  status: "completed",
  termination_state: "completed",
  degradation_flags: [],
  original_query: "q",
  pack_handles: Array.from({ length: 12 }, (_, i) => `H${i}`),
  cited_handles: [],
  usage: {},
  timings: { pack_ms: 2, attempts: 1, total_ms: 9379.9, verify_ms_1: 18.5, retrieval_ms: 158.3, synthesis_ms_1: 9071 },
  models: {},
  route: { decided: "standard" },
  agent: null,
  tool_calls: null,
  created_at: "2026-10-06T00:00:00Z",
  finished_at: "2026-10-06T00:00:09Z",
  ...over,
});

const step = (n: number, idx: number, tool: string, handles: number, ms: number, status = "ok"): AgentTraceStep => ({
  step: n,
  call_index: idx,
  tool,
  args: {},
  status,
  error_code: null,
  handles: Array.from({ length: handles }, (_, i) => `${tool}-${n}-${idx}-${i}`),
  duration_ms: ms,
});

const researchRun = (trace: AgentTraceStep[], over: Partial<RunRecord> = {}) =>
  baseRun({
    mode: "research" as RunRecord["mode"],
    timings: { pack_ms: 8.3, agent_ms: 9315, attempts: 1, total_ms: 17761.4, verify_ms_1: 26.4, synthesis_ms_1: 8236.6 },
    agent: {
      stop_reason: "finish_research",
      steps: 4,
      tool_calls: trace.length,
      tool_errors: 0,
      pool_size: 22,
      sufficient: true,
      gap_count: 0,
      duration_ms: 9315,
      flags: [],
      usage: {},
      trace,
    },
    ...over,
  });

const ids = (stages: { id: string }[]) => stages.map((s) => s.id);

describe("savedStages", () => {
  it("maps a standard run to search, compare, prepare and verify with recorded timings", () => {
    const out = savedStages(baseRun());
    expect(ids(out.stages)).toEqual(["understand", "search", "compare", "prepare", "verify"]);
    expect(out.stages.every((s) => s.state === "done")).toBe(true);
    expect(out.stages[1].durationMs).toBe(158.3);
    expect(out.stages[1].detail).toBe("12 passages");
    expect(out.stages[2].detail).toBe("12 passages selected");
    expect(out.summary).toBe("5 stages · 9.38 s");
    expect(out.outcome).toBe("completed");
  });

  it("adds Running analysis only when a calculation ran, splitting agent time", () => {
    const out = savedStages(
      researchRun([
        step(1, 0, "describe_dataset", 0, 24),
        step(1, 1, "search_evidence", 10, 94),
        step(2, 0, "aggregate", 1, 39),
        step(2, 1, "search_evidence", 12, 62),
        step(3, 0, "get_evidence", 4, 32),
      ]),
    );
    expect(ids(out.stages)).toEqual(["understand", "search", "analyze", "compare", "prepare", "verify"]);
    const analyze = out.stages[2];
    expect(analyze.durationMs).toBe(63);
    expect(analyze.detail).toBe("1 calculation");
    expect(out.stages[1].durationMs).toBe(9315 - 63);
    expect(out.stages[1].detail).toBe("3 searches · 26 passages");
    expect(out.summary).toBe("4 steps · 5 tool calls · 17.8 s");
  });

  it("omits Running analysis for a research run that only searched (dataset description alone is not analysis)", () => {
    const out = savedStages(researchRun([step(1, 0, "list_sources", 0, 5), step(1, 1, "describe_dataset", 0, 10), step(2, 0, "search_evidence", 8, 50)]));
    expect(ids(out.stages)).not.toContain("analyze");
    expect(out.stages[1].durationMs).toBe(9315);
  });

  it("evidence-only fallback (model unavailable) has no Preparing answer stage", () => {
    const out = savedStages(
      baseRun({ termination_state: "generation_unavailable", degradation_flags: ["generation_unavailable"], timings: { retrieval_ms: 120, pack_ms: 3, total_ms: 200 } }),
    );
    expect(ids(out.stages)).toEqual(["understand", "search", "compare"]);
  });

  it("citation-check fallback notes it on the verify stage", () => {
    const out = savedStages(baseRun({ degradation_flags: ["CITATION_VERIFICATION_FAILED"] }));
    const verify = out.stages.find((s) => s.id === "verify");
    expect(verify?.detail).toMatch(/evidence shown instead/);
  });

  it("marks the last recorded stage failed for a failed run", () => {
    const out = savedStages(baseRun({ status: "failed", termination_state: "error", timings: { retrieval_ms: 100, total_ms: 500 } }));
    expect(out.outcome).toBe("failed");
    expect(out.stages[out.stages.length - 1].state).toBe("failed");
    expect(out.summary).toContain("Did not complete");
  });

  it("lists only stages that ran for a cancelled run", () => {
    const out = savedStages(baseRun({ status: "cancelled", termination_state: "cancelled", timings: { retrieval_ms: 100 } }));
    expect(out.outcome).toBe("cancelled");
    expect(ids(out.stages)).toEqual(["understand", "search"]);
    expect(out.summary).toBe("2 stages · Cancelled");
  });

  it("sums timings across attempts and notes a rewrite", () => {
    const out = savedStages(baseRun({ timings: { pack_ms: 1, attempts: 2, synthesis_ms_1: 100, synthesis_ms_2: 50, verify_ms_1: 5, verify_ms_2: 5 } }));
    const prepare = out.stages.find((s) => s.id === "prepare");
    expect(prepare?.durationMs).toBe(150);
    expect(prepare?.detail).toBe("Rewritten after citation checks");
    expect(out.stages.find((s) => s.id === "verify")?.durationMs).toBe(10);
  });
});

const tool = (over: Partial<ToolStep>): ToolStep => ({
  step: 1,
  callIndex: 0,
  tool: "search_evidence",
  kind: "search",
  summary: "Searched",
  status: "ok",
  resultCount: 3,
  durationMs: 40,
  errorCode: null,
  ...over,
});

const live = (over: Partial<RunStreamState>): RunStreamState => ({ ...initialRunStreamState, ...over });
const stateOf = (stages: ReturnType<typeof liveStages>) => Object.fromEntries(stages.map((s) => [s.id, s.state]));

describe("liveStages", () => {
  it("starts with Understanding question active", () => {
    const stages = liveStages(live({}));
    expect(stateOf(stages)).toEqual({ understand: "active", search: "pending", compare: "pending", prepare: "pending", verify: "pending" });
  });

  it("moves to searching once routed and shows search tool time", () => {
    const stages = liveStages(
      live({ route: { requested: "auto", personaDefault: "auto", decided: "research", reason: "x", cues: [] }, phase: "searching", tools: [tool({})] }),
    );
    expect(stateOf(stages).understand).toBe("done");
    expect(stateOf(stages).search).toBe("active");
    expect(stages.find((s) => s.id === "search")?.detail).toBe("1 search");
  });

  it("adds Running analysis when a calculation runs and makes it active", () => {
    const stages = liveStages(live({ phase: "searching", tools: [tool({}), tool({ step: 2, kind: "analytics", tool: "aggregate", status: "running", durationMs: null })] }));
    expect(ids(stages)).toEqual(["understand", "search", "analyze", "compare", "prepare", "verify"]);
    expect(stateOf(stages).analyze).toBe("active");
    expect(stages.find((s) => s.id === "search")?.durationMs).toBe(40);
  });

  it("maps the evidence-selection phase to Comparing findings and synthesis to Preparing answer", () => {
    expect(stateOf(liveStages(live({ phase: "analyzing" }))).compare).toBe("active");
    const writing = liveStages(live({ phase: "synthesizing", evidence: { itemCount: 9, classes: [], truncated: false } }));
    expect(stateOf(writing).compare).toBe("done");
    expect(stateOf(writing).prepare).toBe("active");
    expect(writing.find((s) => s.id === "compare")?.detail).toBe("9 passages selected");
    expect(stateOf(liveStages(live({ phase: "verifying" }))).verify).toBe("active");
  });

  it("completes every stage with done-event timings on final", () => {
    const stages = liveStages(
      live({
        phase: "verifying",
        final: { content: "x", citations: [], sections: {}, verification: null } as unknown as RunStreamState["final"],
        done: { terminationState: "completed", flags: [], cacheStatus: null, timings: { retrieval_ms: 150, pack_ms: 2, synthesis_ms_1: 900, verify_ms_1: 20 } } as RunStreamState["done"],
      }),
    );
    expect(stages.every((s) => s.state === "done")).toBe(true);
    expect(stages.find((s) => s.id === "prepare")?.durationMs).toBe(900);
    expect(stages.find((s) => s.id === "search")?.durationMs).toBe(150);
  });

  it("marks the current stage failed on error and skipped on cancel", () => {
    const failed = liveStages(live({ phase: "synthesizing", error: { code: "X", message: "m", retryable: false } }));
    expect(stateOf(failed).prepare).toBe("failed");
    const cancelled = liveStages(live({ phase: "searching", done: { terminationState: "cancelled", flags: [], cacheStatus: null, timings: {} } as RunStreamState["done"] }));
    expect(stateOf(cancelled).search).toBe("skipped");
    expect(stateOf(cancelled).prepare).toBe("pending");
  });
});

describe("replay", () => {
  it("schedules each stage in order, compressed to a few seconds", () => {
    const { stages } = savedStages(baseRun());
    const frames = replaySchedule(stages);
    expect(frames.map((f) => f.index)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(frames[0].atMs).toBe(0);
    for (let i = 1; i < frames.length; i++) expect(frames[i].atMs).toBeGreaterThan(frames[i - 1].atMs);
    expect(frames[frames.length - 1].atMs).toBeLessThanOrEqual(6000);
    // The long synthesis stage takes the largest share of the replay.
    const gaps = frames.slice(1).map((f, i) => f.atMs - frames[i].atMs);
    expect(Math.max(...gaps)).toBe(gaps[3]);
  });

  it("derives stage states for a replay position", () => {
    const { stages } = savedStages(baseRun());
    const at2 = replayStages(stages, 2);
    expect(at2.map((s) => s.state)).toEqual(["done", "done", "active", "pending", "pending"]);
    expect(replayStages(stages, stages.length).every((s) => s.state === "done")).toBe(true);
  });
});
