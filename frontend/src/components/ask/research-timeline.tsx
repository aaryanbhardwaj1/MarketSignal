import { formatMs } from "@/lib/format";
import { PHASE_LABELS, toolSummaryText } from "@/lib/run-mode";
import type { RunPhase, ToolStatus, ToolStep } from "@/lib/run-stream";

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
