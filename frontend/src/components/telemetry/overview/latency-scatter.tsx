"use client";

import { useState } from "react";
import { ChartEmpty, ChartFrame, SERIES_COLORS, linearScale, niceDomain, ticks, type LegendItem } from "@/components/charts";
import { CHART_TEXT } from "@/components/charts/chart-frame";
import { useChartWidth } from "@/components/charts/use-chart-width";
import { formatDateTime, formatMs } from "@/lib/format";
import { shortId, type LatencyDot } from "@/lib/telemetry-view";

const AXIS_W = 48;
const BOTTOM = 26;
const TOP = 10;
const RIGHT = 56;
const MODES = ["standard", "research"] as const;
const MODE_LABEL: Record<string, string> = { standard: "Standard", research: "Research" };

export interface ModeReference {
  mode: "standard" | "research";
  p50: number | null;
  p95: number | null;
}

const colorOf = (mode: string) => SERIES_COLORS[mode === "research" ? 1 : 0];

/**
 * Total latency of every run as a dot, x = position in the window (order recorded), coloured by
 * mode, with each mode's p50 (solid) and p95 (dashed) as reference lines. Arrow keys step through
 * runs; the tooltip names the run so it can be found in the Runs tab.
 */
export function LatencyScatter({
  dots,
  references,
  total,
  caption,
  height = 240,
}: {
  dots: readonly LatencyDot[];
  references: readonly ModeReference[];
  /** Runs in the window (x-axis extent), including runs without a recorded latency. */
  total: number;
  caption?: string;
  height?: number;
}) {
  const [ref, width] = useChartWidth();
  const [hover, setHover] = useState<number | null>(null);
  if (dots.length === 0) return <ChartEmpty message="No run in this window recorded a total latency." />;

  const refValues = references.flatMap((r) => [r.p50, r.p95]).filter((v): v is number => v != null);
  const domain = niceDomain([...dots.map((d) => d.ms), ...refValues]);
  const sx = linearScale([1, Math.max(2, total)], [AXIS_W, width - RIGHT]);
  const sy = linearScale(domain, [height - BOTTOM, TOP]);
  const present = MODES.filter((m) => dots.some((d) => d.mode === m));
  const legend: LegendItem[] = [
    ...present.map((m) => ({ label: `${MODE_LABEL[m]} run`, color: colorOf(m) })),
    { label: "p50 (solid) and p95 (dashed) per mode", color: "var(--color-chart-reference)", dashed: true },
  ];
  const table = {
    columns: ["Run (order recorded)", "Mode", "Total latency", "Recorded at"],
    rows: dots.map((d) => [`#${d.seq} (${shortId(d.id)})`, MODE_LABEL[d.mode] ?? d.mode, formatMs(d.ms), formatDateTime(d.created_at)]),
  };
  const active = hover == null ? null : dots[hover];
  const nearest = (px: number) => {
    let best = 0;
    dots.forEach((d, i) => {
      if (Math.abs(sx(d.seq) - px) < Math.abs(sx(dots[best].seq) - px)) best = i;
    });
    return best;
  };
  const r = dots.length > 150 ? 2.5 : 3.5;
  const xTicks = [1, Math.round(total / 2), total].filter((v, i, a) => v >= 1 && a.indexOf(v) === i);

  return (
    <ChartFrame
      ariaLabel={`Total latency per run for ${dots.length} runs, in the order recorded`}
      caption={caption}
      table={table}
      legend={legend}
      visualRole="group"
    >
      <div
        ref={ref}
        tabIndex={0}
        role="group"
        aria-label="Runs: use the left and right arrow keys to read each run"
        className="relative rounded-sm focus-visible:outline-offset-4"
        onPointerMove={(e) => setHover(nearest(e.clientX - e.currentTarget.getBoundingClientRect().left))}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") setHover((h) => Math.min(dots.length - 1, (h ?? -1) + 1));
          else if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? dots.length) - 1));
          else if (e.key === "Escape") setHover(null);
          else return;
          e.preventDefault();
        }}
      >
        <svg aria-hidden width={width} height={height} className="block overflow-visible">
          {ticks(domain, 4).map((t) => (
            <g key={t}>
              <line x1={AXIS_W} x2={width - RIGHT} y1={sy(t)} y2={sy(t)} stroke="var(--color-chart-grid)" />
              <text x={AXIS_W - 8} y={sy(t)} textAnchor="end" dominantBaseline="central" {...CHART_TEXT}>
                {formatMs(t)}
              </text>
            </g>
          ))}
          {xTicks.map((v, i) => (
            <text key={v} x={sx(v)} y={height - 6} textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"} {...CHART_TEXT}>
              {`Run ${v}`}
            </text>
          ))}
          {dots.map((d, i) => (
            <circle
              key={d.id}
              cx={sx(d.seq)}
              cy={sy(d.ms)}
              r={i === hover ? r + 2 : r}
              fill={colorOf(d.mode)}
              fillOpacity={hover == null || i === hover ? 0.85 : 0.35}
              stroke="var(--color-surface)"
              strokeWidth={1}
            />
          ))}
          {references.flatMap((rf) =>
            (["p50", "p95"] as const).flatMap((k) => {
              const v = rf[k];
              if (v == null) return [];
              return [
                <g key={`${rf.mode}-${k}`}>
                  <line
                    x1={AXIS_W}
                    x2={width - RIGHT}
                    y1={sy(v)}
                    y2={sy(v)}
                    stroke={colorOf(rf.mode)}
                    strokeWidth={1.25}
                    strokeDasharray={k === "p95" ? "4 3" : undefined}
                  />
                  <text x={width - RIGHT + 4} y={sy(v)} dominantBaseline="central" {...CHART_TEXT}>
                    {`${rf.mode === "research" ? "R" : "S"} ${k}`}
                  </text>
                </g>,
              ];
            }),
          )}
        </svg>
        {active && (
          <div
            aria-live="polite"
            className="pointer-events-none absolute top-0 z-10 min-w-40 -translate-x-1/2 rounded-md border border-border bg-raised px-2.5 py-2 text-xs shadow-overlay"
            style={{ left: Math.min(Math.max(sx(active.seq), 90), width - 90) }}
          >
            <p className="font-medium text-primary">
              Run {active.seq} · <span className="font-mono">{shortId(active.id)}</span>
            </p>
            <p className="text-secondary">
              {MODE_LABEL[active.mode] ?? active.mode} · <span className="font-medium text-primary tabular-nums">{formatMs(active.ms)}</span>
            </p>
            <p className="text-muted">{formatDateTime(active.created_at)}</p>
          </div>
        )}
      </div>
    </ChartFrame>
  );
}
