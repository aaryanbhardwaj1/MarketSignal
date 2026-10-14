import { cx } from "@/lib/cx";

export interface BarItem {
  label: string;
  value: number;
  display: string;
  emphasis?: boolean;
}

export type BarListLayout = "inline" | "stacked";

function barPercent(value: number, top: number): number {
  return top > 0 ? Math.max(0, Math.min(100, (value / top) * 100)) : 0;
}

function Bar({ pct, emphasis, className }: { pct: number; emphasis?: boolean; className?: string }) {
  return (
    <span aria-hidden className={cx("h-1.5 overflow-hidden rounded-full bg-chart-track", className)}>
      <span
        className={cx(
          "block h-full rounded-full transition-[width] duration-(--duration-slow) ease-standard motion-reduce:transition-none",
          emphasis ? "bg-chart-bar-emphasis" : "bg-chart-bar",
        )}
        style={{ width: `${pct}%` }}
      />
    </span>
  );
}

/**
 * Horizontal CSS bars with printed values. Rendered as an ordered list so screen readers
 * hear "label: value" for each row; the bars themselves are decorative.
 *
 * `layout="inline"` (default) puts label, bar and value on one row and truncates long labels.
 * `layout="stacked"` puts the label and value above the bar and lets long humanized labels
 * (route reasons, failure categories) wrap instead of truncating.
 */
export function BarList({
  items,
  max,
  ariaLabel,
  layout = "inline",
}: {
  items: BarItem[];
  max?: number;
  ariaLabel: string;
  layout?: BarListLayout;
}) {
  const top = max ?? Math.max(0, ...items.map((i) => i.value));
  const stacked = layout === "stacked";
  return (
    <ol aria-label={ariaLabel} className={cx("flex flex-col", stacked ? "gap-3" : "gap-2.5")}>
      {items.map((item) => {
        const pct = barPercent(item.value, top);
        const tone = item.emphasis ? "font-medium text-primary" : "text-secondary";
        if (stacked) {
          return (
            <li key={item.label} className="text-sm">
              <span className="flex items-baseline justify-between gap-3">
                <span className={cx("min-w-0", tone)} title={item.label}>
                  {item.label}
                </span>
                <span className={cx("shrink-0 tabular-nums", tone)}>{item.display}</span>
              </span>
              <Bar pct={pct} emphasis={item.emphasis} className="mt-1 block" />
            </li>
          );
        }
        return (
          <li key={item.label} className="grid grid-cols-[minmax(0,12rem)_1fr_auto] items-center gap-3 text-sm">
            <span className={cx("truncate", tone)} title={item.label}>
              {item.label}
            </span>
            <Bar pct={pct} emphasis={item.emphasis} />
            <span className={cx("tabular-nums", tone)}>{item.display}</span>
          </li>
        );
      })}
    </ol>
  );
}
