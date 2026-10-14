import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { CitationCard } from "@/lib/api/types";
import { initialRunStreamState, reduceRunEvent, type RunEvent } from "@/lib/run-stream";
import type { StagesSummary } from "@/lib/research-stages";
import type { SavedRunView } from "@/lib/saved-run";
import { SourcesList } from "./answer-evidence";
import { RunMeta } from "./assistant-turn";
import { RunPanel } from "./run-panel";
import { SavedResearchSteps } from "./research-timeline";

const ev = (seq: number, type: string, data: Record<string, unknown> = {}): RunEvent => ({ type, seq, data });
const fold = (events: readonly RunEvent[]) => events.reduce(reduceRunEvent, initialRunStreamState);
const panel = (state = initialRunStreamState, connection: "open" | "closed" = "open") =>
  renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <RunPanel ws="NORTHSTAR" state={state} connection={connection} onCancel={() => {}} cancelling={false} />
    </QueryClientProvider>,
  );

describe("Live research progress", () => {
  it("shows observable stages with the current one marked, plus cancel", () => {
    const html = panel(fold([ev(1, "run_started", { conversation_id: "c1", mode: "standard" }), ev(2, "status", { phase: "searching", message: "Searching workspace evidence" })]));
    expect(html).toContain('aria-label="Research progress"');
    expect(html).toContain("Understanding question");
    expect(html).toContain("Searching evidence");
    expect(html).toMatch(/aria-current="step"[^>]*>[\s\S]*Searching evidence/);
    expect(html).toContain("Cancel");
    expect(html).not.toContain("Running analysis");
  });

  it("labels the streamed draft as not yet verified", () => {
    const html = panel(fold([ev(1, "run_started", { conversation_id: "c1" }), ev(2, "status", { phase: "synthesizing", message: "Writing" }), ev(3, "token", { text: "Draft words" })]));
    expect(html).toContain("Draft — not yet verified");
    expect(html).toContain("Draft words");
  });

  it("tells the reader when the live connection is lost", () => {
    const html = panel(fold([ev(1, "run_started", { conversation_id: "c1" })]), "closed");
    expect(html).toContain("Lost the live connection");
    expect(html).not.toContain("Cancel");
  });
});

const summary: StagesSummary = {
  outcome: "completed",
  totalMs: 17761,
  summary: "4 steps · 5 lookups · 17.8 s",
  stages: [
    { id: "understand", label: "Understanding question", state: "done", durationMs: null, detail: null },
    { id: "search", label: "Searching evidence", state: "done", durationMs: 9252, detail: "3 searches · 26 passages" },
    { id: "analyze", label: "Running analysis", state: "done", durationMs: 63, detail: "1 calculation" },
  ],
};

describe("SavedResearchSteps", () => {
  it("summarises the saved run collapsed by default, with a replay control", () => {
    const html = renderToStaticMarkup(<SavedResearchSteps summary={summary} />);
    expect(html).toContain("Research steps");
    expect(html).toContain("4 steps · 5 lookups · 17.8 s");
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("Replay");
    expect(html).toContain("9.25 s");
  });
});

describe("RunMeta", () => {
  it("states mode, verified status, duration and sources in plain words", () => {
    const view = { mode: "Research", verifiedText: "Citations verified", durationMs: 17761 } as SavedRunView;
    const html = renderToStaticMarkup(<RunMeta view={view} sources={4} />);
    for (const text of ["Research", "Citations verified", "17.8 s", "4 sources"]) expect(html).toContain(text);
  });
});

describe("SourcesList", () => {
  it("lists numbered sources with a plain type and locator, no handles", () => {
    const card: CitationCard = {
      handle: "NORTHSTAR/SURVEY-2026@v1:R185",
      source_code: "SURVEY-2026",
      source_title: "Northstar Customer Survey 2026",
      source_class: "customer",
      source_type: "csv",
      locator_label: "Row 185",
      anchor_child_id: null,
      char_start: null,
      char_end: null,
      parent_content_hash: null,
    };
    const html = renderToStaticMarkup(<SourcesList ws="NORTHSTAR" cards={[card]} />);
    expect(html).toContain("1.");
    expect(html).toContain("Northstar Customer Survey 2026");
    expect(html).toContain("Survey · Row 185");
    expect(html.replace(/href="[^"]*"/g, "")).not.toContain("SURVEY-2026@v1");
  });
});
