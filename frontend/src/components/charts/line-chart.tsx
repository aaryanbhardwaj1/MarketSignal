"use client";

import { useState, type ReactNode } from "react";
import { ChartEmpty, ChartFrame, CHART_TEXT, SERIES_COLORS } from "./chart-frame";
import { bandPath, defaultFormat, linePath, linearScale, nearestIndex, niceDomain, ticks, type Point } from "./scale";
import { useChartWidth } from "./use-chart-width";

export type XValue = number | string | Date;

export interface LineSeries {
  name: string;
  values: ReadonlyArray<number | null>;
}

const AXIS_W = 44;
const BOTTOM = 24;
const TOP = 10;
const RIGHT = 12;

function xNumber(x: XValue, i: number): number {
  if (x instanceof Date) return x.getTime();
  return typeof x === "number" ? x : i;
}

function defaultFormatX(x: XValue): string {
  if (x instanceof Date) return x.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return String(x);
}

/**
 * Lines over time or index: 1-3 series, point markers, an optional interval band around the
 * first series, and a crosshair tooltip on hover or keyboard focus (arrow keys move it).
 */
export function LineChart({
  x,
  series,
  band,
  ariaLabel,
  title,
  caption,
  format = defaultFormat,
  formatX = defaultFormatX,
  height = 220,
  includeZero = true,
  className,
}: {
  x: readonly XValue[];
  series: readonly LineSeries[];
  band?: { low: readonly number[]; high: readonly number[]; label: string };
  ariaLabel: string;
  title?: ReactNode;
  caption?: ReactNode;
  format?: (value: number) => string;
  formatX?: (x: XValue) => string;
  height?: number;
  includeZero?: boolean;
  className?: string;
}) {
  const [ref, width] = useChartWidth();
  const [hover, setHover] = useState<number | null>(null);
  const shown = series.slice(0, 3);
  if (x.length === 0 || shown.length === 0) return <ChartEmpty />;

  const xs = x.map(xNumber);
  const values = [...shown.flatMap((s) => s.values.filter((v): v is number => v !== null)), ...(band ? [...band.low, ...band.high] : [])];
  const domain = niceDomain(values, { includeZero });
  const sx = linearScale([Math.min(...xs), Math.max(...xs)], [AXIS_W, width - RIGHT]);
  const sy = linearScale(domain, [height - BOTTOM, TOP]);
  const px = xs.map(sx);
  const tickIdx = x.length <= 6 ? x.map((_, i) => i) : [0, Math.floor((x.length - 1) / 2), x.length - 1];

  const pointsOf = (s: LineSeries): Point[] =>
    s.values.flatMap((v, i) => (v === null || !Number.isFinite(v) ? [] : [[px[i], sy(v)] as Point]));

  const table = {
    columns: ["X", ...shown.map((s) => s.name), ...(band ? [`${band.label} low`, `${band.label} high`] : [])],
    rows: x.map((xv, i) => [
      formatX(xv),
      ...shown.map((s) => (s.values[i] === null ? "" : format(s.values[i] as number))),
      ...(band ? [format(band.low[i]), format(band.high[i])] : []),
    ]),
  };
  const legend = [
    ...shown.map((s, i) => ({ label: s.name, color: SERIES_COLORS[i] })),
    ...(band ? [{ label: band.label, color: "var(--color-chart-1)", dashed: true }] : []),
  ];

  const onMove = (clientX: number, rect: DOMRect) => setHover(nearestIndex(px, clientX - rect.left));
  const tipLeft = hover === null ? 0 : Math.min(Math.max(px[hover], 80), width - 80);

  return (
    <ChartFrame title={title} caption={caption} ariaLabel={ariaLabel} table={table} legend={band || shown.length > 1 ? legend : undefined} visualRole="group" className={className}>
      <div
        ref={ref}
        tabIndex={0}
        role="group"
        aria-label="Chart values: use the left and right arrow keys to read each point"

        className="relative rounded-sm focus-visible:outline-offset-4"
        onPointerMove={(e) => onMove(e.clientX, e.currentTarget.getBoundingClientRect())}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") setHover((h) => Math.min(x.length - 1, (h ?? -1) + 1));
          else if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? x.length) - 1));
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
                {format(t)}
              </text>
            </g>
          ))}
          {tickIdx.map((i) => (
            <text key={i} x={px[i]} y={height - 6} textAnchor={i === 0 ? "start" : i === x.length - 1 ? "end" : "middle"} {...CHART_TEXT}>
              {formatX(x[i])}
            </text>
          ))}
          {band && (
            <path
              d={bandPath(band.high.map((v, i) => [px[i], sy(v)] as Point), band.low.map((v, i) => [px[i], sy(v)] as Point))}
              fill="var(--color-chart-band)"
            />
          )}
          {hover !== null && <line x1={px[hover]} x2={px[hover]} y1={TOP} y2={height - BOTTOM} stroke="var(--color-chart-axis)" />}
          {shown.map((s, si) => (
            <g key={s.name}>
              <path d={linePath(pointsOf(s))} fill="none" stroke={SERIES_COLORS[si]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {pointsOf(s).map(([cx, cy], i) => (
                <circle key={i} cx={cx} cy={cy} r={x.length > 24 ? 0 : 3} fill={SERIES_COLORS[si]} stroke="var(--color-surface)" strokeWidth={1.5} />
              ))}
              {hover !== null && s.values[hover] !== null && (
                <circle cx={px[hover]} cy={sy(s.values[hover] as number)} r={4.5} fill={SERIES_COLORS[si]} stroke="var(--color-surface)" strokeWidth={2} />
              )}
            </g>
          ))}
        </svg>
        {hover !== null && (
          <div
            aria-live="polite"
            className="pointer-events-none absolute top-0 z-10 min-w-36 -translate-x-1/2 rounded-md border border-border bg-raised px-2.5 py-2 text-xs shadow-overlay"
            style={{ left: tipLeft }}
          >
            <p className="mb-1 font-medium text-primary">{formatX(x[hover])}</p>
            {shown.map((s, si) => (
              <p key={s.name} className="flex items-center justify-between gap-3 text-secondary">
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden className="h-0.5 w-2.5 rounded-full" style={{ backgroundColor: SERIES_COLORS[si] }} />
                  {s.name}
                </span>
                <span className="font-medium text-primary tabular-nums">{s.values[hover] === null ? "–" : format(s.values[hover] as number)}</span>
              </p>
            ))}
            {band && (
              <p className="mt-0.5 text-muted tabular-nums">
                {band.label}: {format(band.low[hover])} to {format(band.high[hover])}
              </p>
            )}
          </div>
        )}
      </div>
    </ChartFrame>
  );
}
