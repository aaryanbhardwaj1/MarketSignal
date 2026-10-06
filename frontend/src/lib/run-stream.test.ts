import { describe, expect, it } from "vitest";
import {
  foldRunEvents,
  initialRunStreamState,
  parseRunEvent,
  reduceRunEvent,
  terminationLabel,
  type RunEvent,
} from "./run-stream";

const CARD = {
  handle: "NORTHSTAR/SURVEY-2026@v1:R185",
  source_code: "SURVEY-2026",
  source_title: "Consumer survey",
  source_class: "customer",
  source_type: "csv",
  locator_label: "Row 185",
  anchor_child_id: "0d4c7f8e-2b5a-4c1e-9a77-1f2e3d4c5b6a",
  char_start: 0,
  char_end: 10,
  parent_content_hash: "abc",
};

function ev(seq: number, type: string, data: Record<string, unknown> = {}): RunEvent {
  return { type, seq, data: { run_id: "r1", seq, ts: "2026-10-05T00:00:00Z", ...data } };
}

const citation = (seq: number, alias: string, attempt = 1) =>
  ev(seq, "citation", {
    attempt,
    alias,
    handle: CARD.handle,
    source_title: CARD.source_title,
    source_class: CARD.source_class,
    locator_label: CARD.locator_label,
  });

describe("reduceRunEvent", () => {
  it("folds a normal run in order", () => {
    const state = foldRunEvents([
      ev(1, "run_started", { conversation_id: "c1", persona: "generalist", mode: "standard" }),
      ev(2, "status", { phase: "searching", message: "Searching workspace evidence" }),
      ev(3, "tool_started", { step: 1, tool: "search_evidence", kind: "search", summary: "hybrid" }),
      ev(4, "tool_completed", { step: 1, tool: "search_evidence", status: "ok", result_count: 5 }),
      ev(5, "evidence", { item_count: 5, classes: ["customer"], truncated: false }),
      ev(6, "status", { phase: "synthesizing", message: "Writing the answer" }),
      citation(7, "E1"),
      ev(8, "token", { attempt: 1, text: "Growth is up [E1]" }),
      ev(9, "token", { attempt: 1, text: "." }),
    ]);
    expect(state.conversationId).toBe("c1");
    expect(state.phase).toBe("synthesizing");
    expect(state.statusMessage).toBe("Writing the answer");
    expect(state.evidence).toEqual({ itemCount: 5, classes: ["customer"], truncated: false });
    expect(state.draft).toBe("Growth is up [E1].");
    expect(Object.keys(state.citationsByAlias)).toEqual(["E1"]);
    expect(state.lastSeq).toBe(9);
    expect(state.done).toBeNull();
  });

  it("clears the draft and alias bindings on draft_reset and ignores the old attempt", () => {
    const state = foldRunEvents([
      citation(1, "E1"),
      ev(2, "token", { attempt: 1, text: "First try [E1]" }),
      ev(3, "draft_reset", { attempt: 2, reason: "verification_failed" }),
      ev(4, "token", { attempt: 1, text: " stale" }),
      citation(5, "E2", 2),
      ev(6, "token", { attempt: 2, text: "Second [E2]" }),
    ]);
    expect(state.draft).toBe("Second [E2]");
    expect(Object.keys(state.citationsByAlias)).toEqual(["E2"]);
    expect(state.attempt).toBe(2);
    expect(state.draftResetReason).toBe("verification_failed");
  });

  it("treats an evidence-only reset (attempt 0) as discarding the current attempt", () => {
    const state = foldRunEvents([
      ev(1, "token", { attempt: 1, text: "Draft" }),
      ev(2, "draft_reset", { attempt: 0, reason: "evidence_only" }),
      ev(3, "token", { attempt: 1, text: "late" }),
    ]);
    expect(state.draft).toBe("");
    expect(state.citationsByAlias).toEqual({});
    expect(state.draftResetReason).toBe("evidence_only");
  });

  it("final replaces the draft entirely", () => {
    const state = foldRunEvents([
      citation(1, "E1"),
      ev(2, "token", { attempt: 1, text: "Draft text [E1]" }),
      ev(3, "final", {
        message_id: "m1",
        content: `Final [[${CARD.handle}]]`,
        citations: [CARD, { not: "a card" }],
        sections: { answer: ["Final"], findings: [] },
        verification: { passed: true },
      }),
    ]);
    expect(state.draft).toBe("");
    expect(state.citationsByAlias).toEqual({});
    expect(state.final?.content).toBe(`Final [[${CARD.handle}]]`);
    expect(state.final?.citations).toEqual([CARD]);
    expect(state.final?.message_id).toBe("m1");
  });

  it("done is terminal and ignores everything after it", () => {
    const done = foldRunEvents([
      ev(1, "status", { phase: "searching", message: "Searching" }),
      ev(2, "done", {
        termination_state: "cancelled",
        flags: ["RUN_CANCELLED"],
        cache_status: "disabled",
        timings: { total_ms: 12.5, bad: "x" },
      }),
    ]);
    expect(done.done).toEqual({
      terminationState: "cancelled",
      flags: ["RUN_CANCELLED"],
      cacheStatus: "disabled",
      timings: { total_ms: 12.5 },
    });
    expect(done.terminationState).toBe("cancelled");
    expect(done.phase).toBeNull();
    const after = foldRunEvents(
      [ev(3, "token", { attempt: 1, text: "x" }), ev(4, "warning", { code: "W", message: "m" })],
      done,
    );
    expect(after).toBe(done);
  });

  it("ignores duplicate and replayed seqs", () => {
    const events = [
      ev(1, "token", { attempt: 1, text: "a" }),
      ev(2, "token", { attempt: 1, text: "b" }),
      ev(3, "warning", { code: "UNKNOWN_ALIAS", message: "dropped E9" }),
    ];
    const once = foldRunEvents(events);
    // A reconnect replays from Last-Event-ID; an overlapping replay must change nothing.
    const replayed = foldRunEvents([...events, ...events]);
    expect(replayed).toEqual(once);
    expect(replayed.draft).toBe("ab");
    expect(replayed.warnings).toHaveLength(1);
    expect(reduceRunEvent(once, ev(2, "token", { attempt: 1, text: "dup" }))).toBe(once);
  });

  it("ignores unknown event types but still advances seq", () => {
    const state = foldRunEvents([ev(1, "telemetry", { anything: true }), ev(2, "token", { attempt: 1, text: "ok" })]);
    expect(state.draft).toBe("ok");
    expect(state.lastSeq).toBe(2);
  });

  it("accumulates warnings in order", () => {
    const state = foldRunEvents([
      ev(1, "warning", { code: "UNKNOWN_ALIAS", message: "one" }),
      ev(2, "warning", { code: "RETRIEVAL_DEGRADED", message: "two" }),
    ]);
    expect(state.warnings).toEqual([
      { code: "UNKNOWN_ALIAS", message: "one" },
      { code: "RETRIEVAL_DEGRADED", message: "two" },
    ]);
  });

  it("shows each warning code once, however often the run repeats it", () => {
    const state = foldRunEvents([
      ev(1, "warning", { code: "SOURCE_DELETED_DURING_RUN", message: "withheld" }),
      ev(2, "warning", { code: "UNKNOWN_ALIAS", message: "one" }),
      ev(3, "warning", { code: "SOURCE_DELETED_DURING_RUN", message: "withheld" }),
      ev(4, "warning", { code: "SOURCE_DELETED_DURING_RUN", message: "deleted" }),
    ]);
    expect(state.warnings).toEqual([
      { code: "SOURCE_DELETED_DURING_RUN", message: "withheld" },
      { code: "UNKNOWN_ALIAS", message: "one" },
    ]);
    expect(state.lastSeq).toBe(4);
  });

  it("records run errors", () => {
    const state = foldRunEvents([ev(1, "error", { code: "TIMEOUT", message: "Too slow", retryable: true })]);
    expect(state.error).toEqual({ code: "TIMEOUT", message: "Too slow", retryable: true });
  });

  it("does not mutate the previous state", () => {
    const before = initialRunStreamState;
    const after = reduceRunEvent(before, ev(1, "warning", { code: "W", message: "m" }));
    expect(before.warnings).toHaveLength(0);
    expect(after.warnings).toHaveLength(1);
  });
});

describe("parseRunEvent", () => {
  it("decodes JSON with a seq", () => {
    expect(parseRunEvent("token", '{"seq": 4, "text": "x"}')).toEqual({
      type: "token",
      seq: 4,
      data: { seq: 4, text: "x" },
    });
  });

  it("falls back to the SSE id when seq is missing", () => {
    expect(parseRunEvent("status", '{"phase": "searching"}', "7")?.seq).toBe(7);
  });

  it("rejects undecodable or seq-less payloads", () => {
    expect(parseRunEvent("token", "not json")).toBeNull();
    expect(parseRunEvent("token", "[1,2]")).toBeNull();
    expect(parseRunEvent("token", '{"text": "x"}')).toBeNull();
    expect(parseRunEvent("token", '{"seq": 0}')).toBeNull();
  });
});

describe("terminationLabel", () => {
  it("labels known states and humanizes unknown ones", () => {
    expect(terminationLabel("no_relevant_evidence")).toBe("No relevant evidence");
    expect(terminationLabel("brand_new_state")).toBe("brand new state");
  });
});
