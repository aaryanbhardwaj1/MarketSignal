import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

export interface LegendItem {
  label: string;
  color: string;
  /** Dashed swatch, e.g. for an interval or a reference series. */
  dashed?: boolean;
}

export interface ChartTable {
  columns: readonly string[];
  rows: ReadonlyArray<ReadonlyArray<string | number>>;
}

/** Inline legend: swatch + label, identity never by colour alone. */
export function ChartLegend({ items, className }: { items: readonly LegendItem[]; className?: string }) {
  if (items.length === 0) return null;
  return (
    <ul className={cx("flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-secondary", className)}>
      {items.map((item) => (
        <li key={item.label} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className={cx("h-2 w-2.5 rounded-xs", item.dashed && "border border-dashed bg-transparent")}
            style={item.dashed ? { borderColor: item.color } : { backgroundColor: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/**
 * Shared chart wrapper: `<figure>` with an optional title, the visual (role="img" + aria-label),
 * a legend, a `<figcaption>`, and a visually hidden data table carrying the same numbers.
 */
export function ChartFrame({
  title,
  caption,
  ariaLabel,
  table,
  legend,
  children,
  visualRole = "img",
  className,
}: {
  /** "group" for charts with focusable, interactive content (an img role hides its children). */
  visualRole?: "img" | "group";
  title?: ReactNode;
  caption?: ReactNode;
  ariaLabel: string;
  table: ChartTable;
  legend?: readonly LegendItem[];
  children: ReactNode;
  className?: string;
}) {
  return (
    <figure className={cx("flex min-w-0 flex-col gap-3", className)}>
      {title && <div className="text-sm font-medium text-primary">{title}</div>}
      {legend && legend.length > 1 && <ChartLegend items={legend} />}
      <div role={visualRole} aria-label={ariaLabel} className="relative min-w-0 tabular-nums">
        {children}
      </div>
      {caption && <figcaption className="text-xs text-muted">{caption}</figcaption>}
      <table className="sr-only">
        <thead>
          <tr>
            {table.columns.map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (j === 0 ? <th key={j} scope="row">{cell}</th> : <td key={j}>{cell}</td>))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** Honest empty state for a chart with no data: never draw a fake chart. */
export function ChartEmpty({ message = "No data to chart yet." }: { message?: string }) {
  return <p className="rounded-md border border-dashed border-border-strong px-4 py-6 text-center text-sm text-muted">{message}</p>;
}

/** Series colours in fixed order (never cycled past four). */
export const SERIES_COLORS = ["var(--color-chart-1)", "var(--color-chart-2)", "var(--color-chart-3)", "var(--color-chart-4)"] as const;

export const CHART_TEXT = { fill: "var(--color-chart-label)", fontSize: 11 } as const;
