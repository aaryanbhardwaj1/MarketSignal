import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

/** Section title (15px semibold), optional one-line description and a right-aligned action. */
export function SectionHeader({
  title,
  description,
  action,
  as: Tag = "h2",
  id,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  as?: "h2" | "h3" | "h4";
  /** Id of the heading element, for `aria-labelledby` on the enclosing section. */
  id?: string;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-wrap items-end justify-between gap-x-4 gap-y-2", className)}>
      <div className="min-w-0">
        <Tag id={id} className={cx("font-semibold text-primary", Tag === "h2" ? "text-md" : "text-base")}>
          {title}
        </Tag>
        {description && <p className="mt-0.5 max-w-reading text-sm text-muted">{description}</p>}
      </div>
      {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
    </div>
  );
}
