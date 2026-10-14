"use client";

import type { TelemetryRunDetail } from "@/lib/api/contracts";
import { Badge } from "@/components/ui/badge";
import { StageBreakdown } from "@/components/charts/stage-breakdown";
import { cx } from "@/lib/cx";
import { formatMs, formatNumber } from "@/lib/format";
import { formatOffset, toolStatusLabel, toolStatusTone } from "@/lib/telemetry-view";
import { AnalyticsResults } from "../run-sections";
import { NotRecorded } from "../stat-tile";
import { deriveRunFlow, flowGantt, type FlowStage, type FlowState, type FlowToolCall } from "./run-flow";

const NODE: Record<FlowState, string> = {
  done: "border-accent bg-accent",
  degraded: "border-warn bg-warn-subtle",
  failed: "border-danger bg-danger-subtle",
};

const STATE_BADGE: Record<FlowState, { tone: "warn" | "danger"; label: string } | null> = {
  done: null,
  degraded: { tone: "warn", label: "Degraded" },
  failed: { tone: "danger", label: "Failed" },
};

function CallList({ calls }: { calls: FlowToolCall[] }) {
  if (calls.length === 0) return <p className="mt-2 text-xs text-muted">No audited tool calls were made.</p>;
  return (
    <ol aria-label="Tool calls in this stage" className="mt-2 divide-y divide-border rounded-md border border-border bg-surface">
      {calls.map((c) => (
        <li key={c.key} className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto_4.5rem_6rem] items-center gap-x-3 px-2.5 py-1 text-xs">
          <span className="tabular-nums text-muted">Step {c.step}</span>
          <span className="truncate font-mono text-primary">{c.tool}</span>
          <span className="flex items-center gap-1.5">
            <Badge tone={toolStatusTone(c.status)} title={c.status}>
              {toolStatusLabel(c.status)}
            </Badge>
            {c.error_code && <span className="font-mono text-muted">{c.error_code}</span>}
            {c.truncated && <span className="text-warn">Truncated</span>}
            {c.warnings.length > 0 && <span className="text-warn">{c.warnings.length === 1 ? "1 warning" : `${c.warnings.length} warnings`}</span>}
          </span>
          <span className="text-right tabular-nums text-secondary">{formatMs(c.duration_ms)}</span>
          <span className="text-right tabular-nums text-secondary">{c.result_count == null ? "-" : `${formatNumber(c.result_count)} ${c.result_count === 1 ? "result" : "results"}`}</span>
        </li>
      ))}
    </ol>
  );
}

function StageItem({ stage, last }: { stage: FlowStage; last: boolean }) {
  const badge = STATE_BADGE[stage.state];
  return (
    <li className="relative grid grid-cols-[1rem_minmax(0,1fr)] gap-x-3 pb-5 last:pb-0">
      <span aria-hidden className="relative flex justify-center">
        <span className={cx("relative z-10 mt-1 size-2.5 rounded-full border-2", NODE[stage.state])} />
        {!last && <span className="absolute bottom-[-0.25rem] top-4 w-px bg-border" />}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-primary">
            {stage.label}
            {badge && <Badge tone={badge.tone}>{badge.label}</Badge>}
          </h3>
          <span className="font-mono text-xs tabular-nums text-muted">
            {stage.start_ms != null && <span title="Offset from run start">{formatOffset(stage.start_ms)}</span>}
            {stage.duration_ms != null && <span className="ml-2 text-secondary">{formatMs(stage.duration_ms)}</span>}
          </span>
        </div>
        <p className="mt-0.5 text-sm text-secondary">{stage.summary}</p>
        {stage.meta.length > 0 && (
          <dl className="mt-1.5 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
            {stage.meta.map((m) => (
              <div key={m.label} className="contents">
                <dt className="text-muted">{m.label}</dt>
                <dd className="text-secondary">{m.value}</dd>
              </div>
            ))}
          </dl>
        )}
        {stage.calls && <CallList calls={stage.calls} />}
        {stage.resultIds && stage.resultIds.length > 0 && (
          <div className="mt-2">
            <AnalyticsResults ids={stage.resultIds} />
          </div>
        )}
      </div>
    </li>
  );
}

/** Vertical execution flow: only stages the run actually recorded, with timing and sanitized metadata. */
export function ExecutionFlow({ detail }: { detail: TelemetryRunDetail }) {
  const stages = deriveRunFlow(detail);
  return (
    <ol aria-label="Execution flow" className="ms-fade-in">
      {stages.map((s, i) => (
        <StageItem key={s.id} stage={s} last={i === stages.length - 1} />
      ))}
    </ol>
  );
}

/** Mini gantt of the stages with a recorded start and duration; overlaps mean concurrent work. */
export function FlowGantt({ detail }: { detail: TelemetryRunDetail }) {
  const rows = flowGantt(deriveRunFlow(detail));
  if (rows.length === 0) return <NotRecorded>No stage spans were recorded for this run.</NotRecorded>;
  return (
    <StageBreakdown
      stages={rows}
      ariaLabel="Stage spans relative to run start"
      format={formatMs}
      labelWidth="7.5rem"
      caption={`Spans relative to run start; total run time ${formatMs(detail.run.total_ms)}. Stages without a recorded start are omitted.`}
    />
  );
}
