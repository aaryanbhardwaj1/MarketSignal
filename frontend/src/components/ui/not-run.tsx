import { CircleDashed } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

/**
 * Honest placeholder for something that has not been measured yet ("Evaluation not yet run").
 * Neutral and dashed so it never reads as an error or as a zero; it shows no number at all.
 */
export function NotRun({
  title = "Not yet run",
  reason,
  detail,
  className,
}: {
  title?: string;
  reason: ReactNode;
  detail?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="note"
      data-state="not-run"
      className={cx("flex gap-2.5 rounded-lg border border-dashed border-border-strong bg-canvas px-4 py-3", className)}
    >
      <CircleDashed aria-hidden size={16} strokeWidth={1.75} className="mt-0.5 shrink-0 text-muted" />
      <div className="min-w-0">
        <p className="text-sm font-medium text-primary">{title}</p>
        <p className="mt-0.5 text-sm text-secondary">{reason}</p>
        {detail && <div className="mt-1.5 text-xs text-muted">{detail}</div>}
      </div>
    </div>
  );
}
