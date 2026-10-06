import { formatMs } from "@/lib/format";
import { toolSummaryText } from "@/lib/run-mode";
import type { RunPhase, ToolStatus, ToolStep } from "@/lib/run-stream";

const PHASE_LABELS: Record<RunPhase, string> = {
  routing: "Routing",
  planning: "Planning",
  searching: "Searching",
  analyzing: "Analyzing",
  synthesizing: "Synthesizing",
  verifying: "Verifying",
};

const STATUS_VIEW: Record<ToolStatus, { label: string; className: string } | null> = {
  running: { label: "In progress", className: "text-sky-700" },
  ok: null,
  error: { label: "Failed", className: "font-semibold text-red-700" },
  denied: { label: "Denied", className: "font-semibold text-amber-800" },
  timeout: { label: "Timed out", className: "font-semibold text-amber-800" },
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
      className={`flex flex-wrap items-baseline gap-x-1.5 rounded px-2 py-1 ${
        failed ? "border border-amber-200 bg-amber-50/70" : ""
      }`}
    >
      <span className="font-medium text-slate-500">Step {tool.step}</span>
      <span aria-hidden>·</span>
      {/* Plain text only: the summary may quote model-supplied text and is never parsed as markup. */}
      {tool.kind === "analytics" && (
        <span
          title="Deterministic calculation over a structured table"
          className="rounded bg-teal-50 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-teal-800 ring-1 ring-inset ring-teal-600/20"
        >
          Analytics
        </span>
      )}
      <span className="text-slate-800">{toolSummaryText(tool)}</span>
      {parts.map((part) => (
        <span key={part} className="text-slate-500">
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
      {tool.errorCode && failed && (
        <code className="rounded bg-white px-1 py-0.5 font-mono text-[11px] text-slate-700">{tool.errorCode}</code>
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
    <details open={running} className="rounded-md border border-slate-200 bg-slate-50/60 text-xs">
      <summary className="cursor-pointer select-none px-2.5 py-1.5 font-semibold text-slate-600">
        Research steps ({tools.length})
        {running && phase && (
          <span className="ml-2 font-normal text-slate-500">Phase: {PHASE_LABELS[phase]}</span>
        )}
      </summary>
      <ol aria-label="Research steps" className="flex flex-col gap-0.5 px-1.5 pb-2">
        {tools.map((tool) => (
          <TimelineItem key={`${tool.step}:${tool.callIndex}`} tool={tool} />
        ))}
      </ol>
    </details>
  );
}
