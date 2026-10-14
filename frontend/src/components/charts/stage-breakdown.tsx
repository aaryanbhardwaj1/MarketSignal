import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { ChartEmpty, ChartFrame } from "./chart-frame";
import { defaultFormat } from "./scale";

export interface StageTiming {
  label: string;
  /** Duration in the caller's unit (typically milliseconds). */
  duration: number;
  /** Start offset; when omitted, stages run back to back. */
  start?: number;
  emphasis?: boolean;
}

/** Positions each stage on a shared 0-1 timeline. Pure; exported for tests. */
export function stageLayout(stages: readonly StageTiming[]) {
  let cursor = 0;
  const placed = stages.map((s) => {
    const start = s.start ?? cursor;
    const duration = Math.max(0, s.duration);
    cursor = start + duration;
    return { ...s, start, duration };
  });
  const total = Math.max(0, ...placed.map((s) => s.start + s.duration));
  return {
    total,
    rows: placed.map((s) => ({ ...s, offset: total ? s.start / total : 0, share: total ? s.duration / total : 0 })),
  };
}

/** Stage timings as a mini gantt: one row per stage on a shared timeline, durations labelled. */
export function StageBreakdown({
  stages,
  ariaLabel,
  title,
  caption,
  format = (ms: number) => `${defaultFormat(ms)} ms`,
  labelWidth = "9rem",
  className,
}: {
  stages: readonly StageTiming[];
  ariaLabel: string;
  title?: ReactNode;
  caption?: ReactNode;
  format?: (value: number) => string;
  labelWidth?: string;
  className?: string;
}) {
  if (stages.length === 0) return <ChartEmpty />;
  const { total, rows } = stageLayout(stages);
  const table = { columns: ["Stage", "Start", "Duration"], rows: rows.map((r) => [r.label, format(r.start), format(r.duration)]) };

  return (
    <ChartFrame title={title} caption={caption ?? `Total ${format(total)}`} ariaLabel={ariaLabel} table={table} className={className}>
      <ul aria-hidden className="flex flex-col gap-1.5">
        {rows.map((r) => (
          <li key={r.label} className="grid items-center gap-3 text-sm" style={{ gridTemplateColumns: `${labelWidth} minmax(0,1fr) 4.5rem` }}>
            <span className={cx("truncate", r.emphasis ? "font-medium text-primary" : "text-secondary")}>{r.label}</span>
            <span className="relative h-2.5 rounded-xs bg-sunken">
              <span
                className="absolute inset-y-0 rounded-xs"
                style={{
                  left: `${r.offset * 100}%`,
                  width: `max(2px, ${r.share * 100}%)`,
                  backgroundColor: r.emphasis ? "var(--color-chart-bar-emphasis)" : "var(--color-chart-bar)",
                }}
              />
            </span>
            <span className="text-right text-xs text-muted tabular-nums">{format(r.duration)}</span>
          </li>
        ))}
      </ul>
    </ChartFrame>
  );
}
