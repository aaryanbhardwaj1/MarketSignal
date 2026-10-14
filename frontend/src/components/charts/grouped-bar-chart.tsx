"use client";

import type { ReactNode } from "react";
import { ChartEmpty, ChartFrame, CHART_TEXT, SERIES_COLORS } from "./chart-frame";
import { visibleLabels, wrapLabel } from "./label-layout";
import { bandLayout, defaultFormat, linearScale, niceDomain, ticks } from "./scale";
import { useChartWidth } from "./use-chart-width";

export interface BarSeries {
  name: string;
  values: readonly number[];
}

const AXIS_W = 40;
const TOP = 16;
/** Space under the plot: gap + one 13px line per category-label line. */
const LABEL_GAP = 10;
const LINE_H = 13;

/** Vertical grouped bars: 2-4 series per category, fixed series colour order, legend always shown. */
export function GroupedBarChart({
  categories,
  series,
  ariaLabel,
  title,
  caption,
  format = defaultFormat,
  height = 220,
  showValues,
  className,
}: {
  categories: readonly string[];
  series: readonly BarSeries[];
  ariaLabel: string;
  title?: ReactNode;
  caption?: ReactNode;
  format?: (value: number) => string;
  height?: number;
  /** Value labels above bars; defaults to on when there are at most 12 bars. */
  showValues?: boolean;
  className?: string;
}) {
  const [ref, width] = useChartWidth();
  const shown = series.slice(0, 4);
  if (categories.length === 0 || shown.length === 0) return <ChartEmpty />;

  const domain = niceDomain(shown.flatMap((s) => s.values));
  const plotW = Math.max(60, width - AXIS_W);
  const outer = bandLayout(categories.length, plotW, 0.28);
  const inner = bandLayout(shown.length, outer.bandwidth, 0.12);
  // Category labels wrap to two lines within their band; anything longer is truncated with a <title>.
  const categoryLabels = categories.map((c) => wrapLabel(c, Math.max(24, outer.step - 6)));
  const labelLines = Math.max(1, ...categoryLabels.map((l) => l.lines.length));
  const bottom = LABEL_GAP + labelLines * LINE_H;
  const plotH = height - bottom - TOP;
  const y = linearScale(domain, [TOP + plotH, TOP]);
  const labels = showValues ?? categories.length * shown.length <= 12;
  // Value labels that would collide with a neighbour (narrow bars) are skipped; the data table keeps every value.
  const valueLabels = categories.flatMap((_, ci) =>
    shown.map((s, si) => {
      const v = s.values[ci];
      const top = Math.min(y(v), y(0));
      return { x: AXIS_W + outer.start(ci) + inner.start(si) + inner.bandwidth / 2, y: top - 4, text: Number.isFinite(v) ? format(v) : "" };
    }),
  );
  const valueVisible = labels ? visibleLabels(valueLabels) : [];

  const table = {
    columns: ["Category", ...shown.map((s) => s.name)],
    rows: categories.map((c, i) => [c, ...shown.map((s) => format(s.values[i] ?? Number.NaN))]),
  };
  const legend = shown.map((s, i) => ({ label: s.name, color: SERIES_COLORS[i] }));

  return (
    <ChartFrame title={title} caption={caption} ariaLabel={ariaLabel} table={table} legend={legend} className={className}>
      <div ref={ref}>
        <svg aria-hidden width={width} height={height} className="block overflow-visible">
          {ticks(domain, 4).map((t) => (
            <g key={t}>
              <line x1={AXIS_W} x2={width} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--color-chart-axis)" : "var(--color-chart-grid)"} />
              <text x={AXIS_W - 8} y={y(t)} textAnchor="end" dominantBaseline="central" {...CHART_TEXT}>
                {format(t)}
              </text>
            </g>
          ))}
          {categories.map((c, ci) => {
            const gx = AXIS_W + outer.start(ci);
            return (
              <g key={c}>
                {shown.map((s, si) => {
                  const v = s.values[ci];
                  if (!Number.isFinite(v)) return null;
                  const bx = gx + inner.start(si);
                  const top = Math.min(y(v), y(0));
                  const h = Math.max(1, Math.abs(y(v) - y(0)));
                  return (
                    <g key={s.name}>
                      <rect x={bx} y={top} width={inner.bandwidth} height={h} rx={2} fill={SERIES_COLORS[si]}>
                        <title>{`${c}, ${s.name}: ${format(v)}`}</title>
                      </rect>
                      {labels && valueVisible[ci * shown.length + si] && (
                        <text x={bx + inner.bandwidth / 2} y={top - 4} textAnchor="middle" {...CHART_TEXT}>
                          {format(v)}
                        </text>
                      )}
                    </g>
                  );
                })}
                <text x={gx + outer.bandwidth / 2} y={TOP + plotH + LABEL_GAP + 9} textAnchor="middle" {...CHART_TEXT} fill="var(--color-text-secondary)">
                  {categoryLabels[ci].truncated && <title>{c}</title>}
                  {categoryLabels[ci].lines.map((line, li) => (
                    <tspan key={li} x={gx + outer.bandwidth / 2} dy={li === 0 ? 0 : LINE_H}>
                      {line}
                    </tspan>
                  ))}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </ChartFrame>
  );
}
