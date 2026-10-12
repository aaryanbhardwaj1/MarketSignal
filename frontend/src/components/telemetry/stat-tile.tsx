import { cx } from "@/lib/cx";
import type { ReactNode } from "react";

/** Dense console figure: label, value and one context line. Denser than the business `MetricCard`. */
export function StatTile({
  label,
  value,
  context,
  footnote,
  className,
}: {
  className?: string;
  label: ReactNode;
  value: ReactNode;
  context?: ReactNode;
  footnote?: ReactNode;
}) {
  return (
    <div className={cx("flex min-w-0 flex-col rounded-lg border border-border bg-surface px-3.5 py-3", className)}>
      <p className="truncate text-sm text-secondary">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-primary">{value}</p>
      {context && <div className="mt-0.5 text-xs text-muted">{context}</div>}
      {footnote && <div className="mt-auto pt-2 text-xs text-muted">{footnote}</div>}
    </div>
  );
}

/** Bordered sub-panel with a small heading, used inside a `Section`. */
export function Panel({
  title,
  meta,
  children,
}: {
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-4 py-2.5">
        <h3 className="text-base font-semibold text-primary">{title}</h3>
        {meta && <span className="text-xs text-muted">{meta}</span>}
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  );
}

/** Muted inline marker for data that a run (or window) did not record. */
export function NotRecorded({ children = "Not recorded for this run" }: { children?: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}
