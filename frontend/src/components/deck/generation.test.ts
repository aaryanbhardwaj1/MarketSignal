import { describe, expect, it } from "vitest";
import {
  COMPOSE_STAGES,
  downloadReducer,
  FAST_TICK_MS,
  generationPhase,
  generationReducer,
  generationStages,
  IDLE_GENERATION,
  nextTickMs,
  SLOW_TICK_MS,
  type GenerationEvent,
  type GenerationState,
} from "./generation";

const run = (events: GenerationEvent[], from: GenerationState = IDLE_GENERATION): GenerationState =>
  events.reduce(generationReducer, from);
const states = (s: GenerationState) => generationStages(s).map((x) => x.state);
const ticks = (n: number): GenerationEvent[] => Array.from({ length: n }, () => ({ type: "tick" }));

describe("generationReducer", () => {
  it("starts with the first stage active and nothing else", () => {
    const s = run([{ type: "start" }]);
    expect(states(s)).toEqual(["active", "pending", "pending", "pending", "pending"]);
    expect(generationPhase(s)).toBe("running");
    expect(nextTickMs(s)).toBe(SLOW_TICK_MS);
  });

  it("never completes 'Building slides' before the server answers", () => {
    const s = run([{ type: "start" }, ...ticks(10)]);
    expect(s.shown).toBe(COMPOSE_STAGES - 1);
    expect(states(s)).toEqual(["done", "done", "done", "active", "pending"]);
    expect(nextTickMs(s)).toBeNull();
  });

  it("catches up quickly once the preview answers, then waits on the real file request", () => {
    let s = run([{ type: "start" }, { type: "tick" }, { type: "preview_ok" }, { type: "file_start" }]);
    expect(nextTickMs(s)).toBe(FAST_TICK_MS);
    s = run(ticks(3), s);
    expect(states(s)).toEqual(["done", "done", "done", "done", "active"]);
    expect(generationPhase(s)).toBe("running");
    s = run([{ type: "file_ok" }], s);
    expect(states(s).every((x) => x === "done")).toBe(true);
    expect(generationPhase(s)).toBe("done");
  });

  it("reports done only after the display catches up, even if the file finished first", () => {
    const s = run([{ type: "start" }, { type: "preview_ok" }, { type: "file_start" }, { type: "file_ok" }]);
    expect(generationPhase(s)).toBe("running");
    expect(generationPhase(run([{ type: "settle" }], s))).toBe("done");
  });

  it("settle completes the composition stages at once (reduced motion) but only after the server answered", () => {
    expect(run([{ type: "start" }, { type: "settle" }]).shown).toBe(0);
    expect(run([{ type: "start" }, { type: "preview_ok" }, { type: "settle" }]).shown).toBe(COMPOSE_STAGES);
  });

  it("marks the active stage failed when the preview fails", () => {
    const s = run([{ type: "start" }, { type: "tick" }, { type: "preview_failed" }]);
    expect(states(s)).toEqual(["done", "failed", "pending", "pending", "pending"]);
    expect(generationPhase(s)).toBe("failed");
    expect(nextTickMs(s)).toBeNull();
  });

  it("marks the last stage failed when the file request fails", () => {
    const s = run([{ type: "start" }, { type: "preview_ok" }, { type: "file_start" }, { type: "settle" }, { type: "file_failed" }]);
    expect(states(s)).toEqual(["done", "done", "done", "done", "failed"]);
    expect(generationPhase(s)).toBe("failed");
  });

  it("ignores out-of-order events and resets", () => {
    expect(run([{ type: "file_start" }])).toEqual(IDLE_GENERATION);
    expect(run([{ type: "preview_ok" }])).toEqual(IDLE_GENERATION);
    expect(generationPhase(IDLE_GENERATION)).toBe("idle");
    expect(run([{ type: "start" }, { type: "reset" }])).toEqual(IDLE_GENERATION);
  });
});

describe("downloadReducer", () => {
  it("is saved only after a save that began", () => {
    expect(downloadReducer({ status: "idle" }, { type: "saved", filename: "x.pptx" })).toEqual({ status: "idle" });
    const saving = downloadReducer({ status: "idle" }, { type: "begin" });
    expect(saving).toEqual({ status: "saving" });
    expect(downloadReducer(saving, { type: "saved", filename: "x.pptx" })).toEqual({ status: "saved", filename: "x.pptx" });
  });

  it("records failures and cancellations", () => {
    const saving = { status: "saving" } as const;
    expect(downloadReducer(saving, { type: "failed", message: "No" })).toEqual({ status: "failed", message: "No" });
    expect(downloadReducer(saving, { type: "cancel" })).toEqual({ status: "idle" });
    expect(downloadReducer({ status: "failed", message: "No" }, { type: "begin" })).toEqual({ status: "saving" });
  });
});
