import { Card, CardHeader } from "@/components/ui/card";
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

/** Titled sub-panel inside a `Section`: the design-system `Card` + `CardHeader` with a padded body. */
export function Panel({
  title,
  meta,
  children,
  className,
}: {
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card padding="none" className={cx("min-w-0", className)}>
      <CardHeader title={title} meta={meta} />
      <div className="px-5 py-4">{children}</div>
    </Card>
  );
}

/** Muted inline marker for data that a run (or window) did not record. */
export function NotRecorded({ children = "Not recorded for this run" }: { children?: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}
