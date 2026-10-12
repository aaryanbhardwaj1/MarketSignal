import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { foldRunEvents, initialRunStreamState, type RunEvent } from "@/lib/run-stream";
import { RunPanel } from "./run-panel";

const ev = (seq: number, type: string, data: Record<string, unknown> = {}): RunEvent => ({ type, seq, data });
const render = (state = initialRunStreamState) =>
  renderToStaticMarkup(
    <RunPanel ws="NORTHSTAR" state={state} connection="open" onCancel={() => {}} cancelling={false} />,
  );

describe("RunPanel", () => {
  it("is unchanged for a standard run without route or tools", () => {
    const html = render(
      foldRunEvents([
        ev(1, "run_started", { conversation_id: "c1", persona: "generalist", mode: "standard" }),
        ev(2, "status", { phase: "searching", message: "Searching workspace evidence" }),
      ]),
    );
    expect(html).toContain("Searching workspace evidence");
    expect(html).not.toContain("Research steps");
    expect(html).not.toContain("mode ·");
  });

  it("shows the route badge and research timeline", () => {
    const html = render(
      foldRunEvents([
        ev(1, "run_started", {
          conversation_id: "c1",
          mode: "research",
          route: { requested: "auto", decided: "research", reason: "multi_source_cue", cues: [] },
        }),
        ev(2, "status", { phase: "planning", message: "Planning the research" }),
        ev(3, "tool_started", { step: 1, call_index: 0, tool: "search_evidence", kind: "search", summary: 'Searching for "fit"' }),
        ev(4, "tool_completed", { step: 1, call_index: 0, tool: "search_evidence", status: "ok", result_count: 3, duration_ms: 90 }),
      ]),
    );
    expect(html).toContain("Research mode · auto-routed: multi source cue");
    expect(html).toContain("Planning the research");
    expect(html).toContain("Research steps");
    expect(html).toContain("3 results");
  });
});
