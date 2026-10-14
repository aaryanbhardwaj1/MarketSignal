"use client";

import { cx } from "@/lib/cx";
import { INSIGHT_CATEGORIES, type InsightCategoryId } from "@/lib/views/insights";

export type CategoryFilterValue = "all" | InsightCategoryId;

/** Quiet category filter with counts; "All" shows every category in order. */
export function CategoryFilter({
  value,
  counts,
  total,
  onChange,
}: {
  value: CategoryFilterValue;
  counts: Record<InsightCategoryId, number>;
  total: number;
  onChange: (value: CategoryFilterValue) => void;
}) {
  const options: { id: CategoryFilterValue; label: string; count: number }[] = [
    { id: "all", label: "All", count: total },
    ...INSIGHT_CATEGORIES.map((c) => ({ id: c.id, label: c.label, count: counts[c.id] })),
  ];
  return (
    <nav aria-label="Insight categories" className="-mx-1 overflow-x-auto">
      <ul className="flex min-w-max items-center gap-0.5 px-1">
        {options.map((o) => {
          const active = o.id === value;
          return (
            <li key={o.id}>
              <button
                type="button"
                aria-pressed={active}
                disabled={o.count === 0 && o.id !== "all"}
                onClick={() => onChange(o.id)}
                className={cx(
                  "inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm transition-colors duration-(--duration-fast) ease-standard disabled:cursor-not-allowed disabled:opacity-50",
                  active ? "bg-sunken font-medium text-primary" : "text-secondary hover:bg-surface-muted hover:text-primary",
                )}
              >
                {o.label}
                <span className={cx("tabular-nums text-xs", active ? "text-secondary" : "text-muted")}>{o.count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
