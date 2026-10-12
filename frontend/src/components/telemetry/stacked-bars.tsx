import type { BarItem } from "@/components/ui/bar-list";

/**
 * Bar list with the label above its bar, for long humanized labels (route reasons, failure
 * categories). Same tokens and list semantics as `BarList`; labels wrap instead of truncating.
 */
export function StackedBarList({ items, ariaLabel }: { items: BarItem[]; ariaLabel: string }) {
  const top = Math.max(0, ...items.map((i) => i.value));
  return (
    <ol aria-label={ariaLabel} className="flex flex-col gap-3">
      {items.map((item) => {
        const pct = top > 0 ? Math.max(0, Math.min(100, (item.value / top) * 100)) : 0;
        return (
          <li key={item.label} className="text-sm">
            <span className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 text-secondary" title={item.label}>
                {item.label}
              </span>
              <span className="shrink-0 tabular-nums text-secondary">{item.display}</span>
            </span>
            <span aria-hidden className="mt-1 block h-2 overflow-hidden rounded-sm bg-chart-track">
              <span className="block h-full rounded-sm bg-chart-bar" style={{ width: `${pct}%` }} />
            </span>
          </li>
        );
      })}
    </ol>
  );
}
