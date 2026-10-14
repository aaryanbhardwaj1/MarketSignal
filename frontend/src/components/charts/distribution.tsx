"use client";

import type { ReactNode } from "react";
import { ChartEmpty, ChartFrame, CHART_TEXT } from "./chart-frame";
import { defaultFormat, histogram, linearScale, niceDomain, quantile, ticks } from "./scale";
import { useChartWidth } from "./use-chart-width";

const PAD_X = 8;

/**
 * Distribution of one measure: a histogram (default) or a dot strip for small samples, with
 * p50 and p95 markers labelled in place.
 */
export function Distribution({
  values,
  ariaLabel,
  title,
  caption,
  variant = "histogram",
  bins = 16,
  format = defaultFormat,
  height = 120,
  markers = true,
  className,
}: {
  values: readonly number[];
  ariaLabel: string;
  title?: ReactNode;
  caption?: ReactNode;
  variant?: "histogram" | "strip";
  bins?: number;
  format?: (value: number) => string;
  height?: number;
  /** Show p50 / p95 markers. */
  markers?: boolean;
  className?: string;
}) {
  const [ref, width] = useChartWidth();
  const finite = values.filter(Number.isFinite);
  if (finite.length === 0) return <ChartEmpty />;

  const domain = niceDomain(finite, { includeZero: true });
  const sx = linearScale(domain, [PAD_X, width - PAD_X]);
  const base = height - 22;
  const p50 = quantile(finite, 0.5);
  const p95 = quantile(finite, 0.95);
  const histo = histogram(finite, bins);
  const maxCount = Math.max(1, ...histo.map((b) => b.count));
  const sy = linearScale([0, maxCount], [base, 18]);

  const table =
    variant === "histogram"
      ? { columns: ["Range", "Count"], rows: histo.map((b) => [`${format(b.x0)} to ${format(b.x1)}`, b.count]) }
      : { columns: ["#", "Value"], rows: finite.map((v, i) => [i + 1, format(v)]) };
  const summary = { columns: ["Statistic", "Value"], rows: [["Median (p50)", format(p50)], ["p95", format(p95)], ["Count", finite.length]] };

  return (
    <ChartFrame title={title} caption={caption} ariaLabel={ariaLabel} table={{ columns: table.columns, rows: [...table.rows, ...summary.rows] }} className={className}>
      <div ref={ref}>
        <svg aria-hidden width={width} height={height} className="block overflow-visible">
          <line x1={PAD_X} x2={width - PAD_X} y1={base} y2={base} stroke="var(--color-chart-axis)" />
          {variant === "histogram"
            ? histo.map((b, i) => {
                const x0 = sx(b.x0) + 1;
                const w = Math.max(1, sx(b.x1) - sx(b.x0) - 2);
                return b.count > 0 ? <rect key={i} x={x0} y={sy(b.count)} width={w} height={base - sy(b.count)} rx={1.5} fill="var(--color-chart-bar)" /> : null;
              })
            : finite.map((v, i) => <circle key={i} cx={sx(v)} cy={base - 14 - (i % 3) * 7} r={3} fill="var(--color-chart-bar)" fillOpacity={0.75} />)}
          {markers &&
            [
              { label: "p50", value: p50, color: "var(--color-chart-1)" },
              { label: "p95", value: p95, color: "var(--color-chart-4)" },
            ].map((m) => (
              <g key={m.label}>
                <line x1={sx(m.value)} x2={sx(m.value)} y1={12} y2={base} stroke={m.color} strokeWidth={1.5} strokeDasharray={m.label === "p95" ? "3 2" : undefined} />
                <text x={sx(m.value)} y={8} textAnchor="middle" {...CHART_TEXT} fill="var(--color-text)" fontWeight={500}>
                  {`${m.label} ${format(m.value)}`}
                </text>
              </g>
            ))}
          {ticks(domain, 5).map((t) => (
            <text key={t} x={sx(t)} y={height - 4} textAnchor="middle" {...CHART_TEXT}>
              {format(t)}
            </text>
          ))}
        </svg>
      </div>
    </ChartFrame>
  );
}
