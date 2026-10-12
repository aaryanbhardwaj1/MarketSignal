import { cx } from "@/lib/cx";

export interface BarItem {
  label: string;
  value: number;
  display: string;
  emphasis?: boolean;
}

/**
 * Horizontal CSS bars with printed values. Rendered as an ordered list so screen readers
 * hear "label: value" for each row; the bars themselves are decorative.
 */
export function BarList({ items, max, ariaLabel }: { items: BarItem[]; max?: number; ariaLabel: string }) {
  const top = max ?? Math.max(0, ...items.map((i) => i.value));
  return (
    <ol aria-label={ariaLabel} className="flex flex-col gap-2.5">
      {items.map((item) => {
        const pct = top > 0 ? Math.max(0, Math.min(100, (item.value / top) * 100)) : 0;
        return (
          <li key={item.label} className="grid grid-cols-[minmax(0,12rem)_1fr_auto] items-center gap-3 text-sm">
            <span className={cx("truncate", item.emphasis ? "font-medium text-primary" : "text-secondary")} title={item.label}>
              {item.label}
            </span>
            <span aria-hidden className="h-2 overflow-hidden rounded-sm bg-chart-track">
              <span
                className={cx("block h-full rounded-sm", item.emphasis ? "bg-chart-bar-emphasis" : "bg-chart-bar")}
                style={{ width: `${pct}%` }}
              />
            </span>
            <span className={cx("tabular-nums", item.emphasis ? "font-medium text-primary" : "text-secondary")}>
              {item.display}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
