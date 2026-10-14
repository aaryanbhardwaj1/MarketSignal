"use client";

import { RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ScanLine } from "@/components/motion/scan-line";
import { SignalLoader } from "@/components/motion/signal-loader";
import { StageProgress, type Stage } from "@/components/motion/stage-progress";
import { Button } from "@/components/ui/button";
import { Disclosure } from "@/components/ui/disclosure";
import { formatMs } from "@/lib/format";
import { PHASE_LABELS } from "@/lib/labels";
import { toolSummaryText } from "@/lib/run-mode";
import { liveStages, replaySchedule, replayStages, type ResearchStage, type StagesSummary } from "@/lib/research-stages";
import type { RunPhase, RunStreamState, ToolStatus, ToolStep } from "@/lib/run-stream";

const STATUS_VIEW: Record<ToolStatus, { label: string; className: string } | null> = {
  running: { label: "In progress", className: "text-info" },
  ok: null,
  error: { label: "Failed", className: "font-medium text-danger" },
  denied: { label: "Not allowed", className: "font-medium text-warn" },
  timeout: { label: "Timed out", className: "font-medium text-warn" },
};

function resultText(count: number): string {
  return `${count} result${count === 1 ? "" : "s"}`;
}

function TimelineItem({ tool }: { tool: ToolStep }) {
  const status = STATUS_VIEW[tool.status];
  const failed = tool.status === "error" || tool.status === "denied" || tool.status === "timeout";
  const parts: string[] = [];
  if (tool.resultCount !== null && tool.status !== "running") parts.push(resultText(tool.resultCount));
  if (tool.durationMs !== null) parts.push(formatMs(tool.durationMs));
  return (
    <li
      className={`flex flex-wrap items-baseline gap-x-1.5 rounded-sm px-2 py-1 ${
        failed ? "border border-warn/25 bg-warn-subtle" : ""
      }`}
    >
      <span className="font-medium text-muted">Step {tool.step}</span>
      <span aria-hidden>·</span>
      {/* Plain text only: the summary may quote model-supplied text and is never parsed as markup. */}
      {tool.kind === "analytics" && (
        <span
          title="A calculation over a workspace dataset"
          className="rounded-sm border border-cite-result/20 bg-cite-result-bg px-1.5 text-xs font-medium text-cite-result"
        >
          Calculation
        </span>
      )}
      <span className="text-primary">{toolSummaryText(tool)}</span>
      {parts.map((part) => (
        <span key={part} className="text-muted">
          <span aria-hidden>· </span>
          {part}
        </span>
      ))}
      {status && (
        <span className={status.className}>
          <span aria-hidden>· </span>
          {status.label}
        </span>
      )}
    </li>
  );
}

/** Compact, ordered view of the research agent's tool calls (fields of the SSE contract only). */
export function ResearchTimeline({
  tools,
  phase,
  running,
}: {
  tools: readonly ToolStep[];
  phase: RunPhase | null;
  running: boolean;
}) {
  if (tools.length === 0) return null;
  return (
    <details open={running} className="rounded-md border border-border bg-surface-muted text-sm">
      <summary className="cursor-pointer select-none rounded-md px-3 py-2 font-medium text-secondary">
        Research steps ({tools.length})
        {running && phase && (
          <span className="ml-2 font-normal text-muted">Now: {PHASE_LABELS[phase]}</span>
        )}
      </summary>
      <ol aria-label="Research steps" className="flex flex-col gap-0.5 px-2 pb-2">
        {tools.map((tool) => (
          <TimelineItem key={`${tool.step}:${tool.callIndex}`} tool={tool} />
        ))}
      </ol>
    </details>
  );
}

function stageTiming(stage: ResearchStage): string | undefined {
  if (stage.state === "active") return "running";
  return stage.durationMs !== null ? formatMs(stage.durationMs) : undefined;
}

/** `ResearchStage` → `Stage` for `StageProgress` (plain labels, real timings only). */
export function toProgressStages(stages: readonly ResearchStage[]): Stage[] {
  return stages.map((s) => ({ id: s.id, label: s.label, detail: s.detail ?? undefined, state: s.state, timing: stageTiming(s) }));
}

/**
 * Live research progress: the observable stages of the active run (never model reasoning), with
 * a scanning line while evidence is searched and the signal loader while the answer is prepared.
 */
export function LiveResearchProgress({ state, running }: { state: RunStreamState; running: boolean }) {
  const stages = liveStages(state);
  const active = stages.find((s) => s.state === "active")?.id ?? null;
  return (
    <div className="flex flex-col gap-3">
      <StageProgress stages={toProgressStages(stages)} label="Research progress" />
      {running && (active === "search" || active === "analyze") && <ScanLine label="Searching workspace evidence" />}
      {running && (active === "prepare" || active === "verify") && (
        <SignalLoader size="sm" label={active === "verify" ? "Verifying sources" : "Preparing the answer"} showLabel />
      )}
    </div>
  );
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Replays saved stages at their recorded relative timings; reduced motion shows the end state at once. */
function useReplay(stages: readonly ResearchStage[]) {
  const [index, setIndex] = useState<number | null>(null);
  const timers = useRef<number[]>([]);
  const stop = useCallback(() => {
    for (const t of timers.current) window.clearTimeout(t);
    timers.current = [];
  }, []);
  useEffect(() => stop, [stop]);
  const start = useCallback(() => {
    stop();
    if (prefersReducedMotion()) {
      setIndex(null);
      return;
    }
    const frames = replaySchedule(stages);
    setIndex(0);
    timers.current = frames.map((f) =>
      window.setTimeout(() => setIndex(f.index >= stages.length ? null : f.index), f.atMs),
    );
  }, [stages, stop]);
  return { index, start, replaying: index !== null };
}

/** "Research steps" for a saved run: a collapsed summary with durations, expandable, with Replay. */
export function SavedResearchSteps({ summary, children }: { summary: StagesSummary; children?: ReactNode }) {
  const { index, start, replaying } = useReplay(summary.stages);
  const shown = index === null ? summary.stages : replayStages(summary.stages, index);
  return (
    <Disclosure
      variant="plain"
      summary={
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-medium text-secondary">Research steps</span>
          <span className="tabular-nums text-muted">{summary.summary}</span>
        </span>
      }
    >
      <div className="mt-3 flex flex-col gap-4 border-l border-border pl-4">
        <div className="flex flex-col gap-2">
          <StageProgress stages={toProgressStages(shown)} label={replaying ? "Replay of saved run" : "Research steps"} />
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="ghost" size="sm" onClick={start} disabled={replaying || summary.stages.length === 0}>
              <RotateCcw aria-hidden className="h-3.5 w-3.5" />
              Replay
            </Button>
            <span role="status" className="text-xs text-muted">
              {replaying ? "Replay of saved run" : ""}
            </span>
          </div>
        </div>
        {children}
      </div>
    </Disclosure>
  );
}
