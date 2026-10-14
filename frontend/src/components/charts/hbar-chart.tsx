"use client";

import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { ChartEmpty, ChartFrame, CHART_TEXT } from "./chart-frame";
import { defaultFormat, linearScale, niceDomain } from "./scale";
import { useChartWidth } from "./use-chart-width";

export interface HBarDatum {
  label: string;
  value: number;
  /** Optional interval (e.g. a confidence interval reported by the analytics engine). */
  low?: number;
  high?: number;
  /** Draw this bar in the accent; everything else stays neutral. */
  emphasis?: boolean;
}

const ROW = 28;
const BAR = 12;
const VALUE_GUTTER = 64;

/**
 * Horizontal bars for ranked magnitudes. Labels sit in an HTML column (they wrap and truncate
 * cleanly); bars, whiskers and value labels in one SVG so a reference line spans every row.
 */
export function HBarChart({
  data,
  ariaLabel,
  title,
  caption,
  format = defaultFormat,
  valueLabel = "Value",
  reference,
  labelWidth = "10rem",
  domain,
  className,
}: {
  data: readonly HBarDatum[];
  ariaLabel: string;
  title?: ReactNode;
  caption?: ReactNode;
  format?: (value: number) => string;
  /** Column header for the hidden data table. */
  valueLabel?: string;
  reference?: { value: number; label: string };
  labelWidth?: string;
  domain?: readonly [number, number];
  className?: string;
}) {
  const [ref, width] = useChartWidth();
  if (data.length === 0) return <ChartEmpty />;

  const hasInterval = data.some((d) => d.low !== undefined && d.high !== undefined);
  const extent = data.flatMap((d) => [d.value, d.low ?? d.value, d.high ?? d.value]);
  if (reference) extent.push(reference.value);
  const [d0, d1] = domain ?? niceDomain(extent);
  const plot = Math.max(40, width - VALUE_GUTTER);
  const x = linearScale([d0, d1], [0, plot]);
  const height = data.length * ROW;
  const zero = x(Math.max(d0, Math.min(0, d1)));

  const table = {
    columns: ["Item", valueLabel, ...(hasInterval ? ["Low", "High"] : [])],
    rows: data.map((d) => [d.label, format(d.value), ...(hasInterval ? [d.low === undefined ? "" : format(d.low), d.high === undefined ? "" : format(d.high)] : [])]),
  };

  return (
    <ChartFrame title={title} caption={caption} ariaLabel={ariaLabel} table={table} className={className}>
      <div className="grid items-start gap-x-3" style={{ gridTemplateColumns: `${labelWidth} minmax(0, 1fr)` }}>
        <ul aria-hidden className="flex flex-col">
          {data.map((d) => (
            <li key={d.label} className={cx("flex items-center truncate text-sm", d.emphasis ? "font-medium text-primary" : "text-secondary")} style={{ height: ROW }} title={d.label}>
              <span className="truncate">{d.label}</span>
            </li>
          ))}
        </ul>
        <div ref={ref} className="min-w-0">
          <svg aria-hidden width={width} height={height + (reference ? 16 : 0)} className="block overflow-visible">
            <line x1={zero} x2={zero} y1={0} y2={height} stroke="var(--color-chart-axis)" />
            {data.map((d, i) => {
              const y = i * ROW + (ROW - BAR) / 2;
              const x0 = Math.min(x(d.value), zero);
              const w = Math.max(1, Math.abs(x(d.value) - zero));
              const end = Math.max(x(d.value), x(d.high ?? d.value), zero);
              return (
                <g key={d.label}>
                  <rect x={x0} y={y} width={w} height={BAR} rx={2} fill={d.emphasis ? "var(--color-chart-bar-emphasis)" : "var(--color-chart-bar)"}>
                    <title>{`${d.label}: ${format(d.value)}`}</title>
                  </rect>
                  {d.low !== undefined && d.high !== undefined && (
                    <g stroke="var(--color-chart-4)" strokeWidth={1.25}>
                      <line x1={x(d.low)} x2={x(d.high)} y1={y + BAR / 2} y2={y + BAR / 2} />
                      <line x1={x(d.low)} x2={x(d.low)} y1={y + 2} y2={y + BAR - 2} />
                      <line x1={x(d.high)} x2={x(d.high)} y1={y + 2} y2={y + BAR - 2} />
                    </g>
                  )}
                  <text x={end + 6} y={y + BAR / 2} dominantBaseline="central" {...CHART_TEXT} fill={d.emphasis ? "var(--color-text)" : CHART_TEXT.fill} fontWeight={d.emphasis ? 600 : 400}>
                    {format(d.value)}
                  </text>
                </g>
              );
            })}
            {reference && (
              <g>
                <line x1={x(reference.value)} x2={x(reference.value)} y1={-2} y2={height + 2} stroke="var(--color-chart-reference)" strokeDasharray="3 3" />
                <text x={x(reference.value)} y={height + 12} textAnchor="middle" {...CHART_TEXT}>
                  {`${reference.label} ${format(reference.value)}`}
                </text>
              </g>
            )}
          </svg>
        </div>
      </div>
    </ChartFrame>
  );
}
