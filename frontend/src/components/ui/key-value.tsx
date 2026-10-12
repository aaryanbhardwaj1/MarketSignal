import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

/** Label/value pairs as a description list, in one or two columns. */
export function KeyValueList({ items, columns = 1 }: { items: { label: string; value: ReactNode }[]; columns?: 1 | 2 }) {
  return (
    <dl className={cx("grid gap-x-6 gap-y-2.5", columns === 2 ? "sm:grid-cols-2" : "grid-cols-1")}>
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-sm text-muted">{item.label}</dt>
          <dd className="mt-0.5 break-words text-base text-primary">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
