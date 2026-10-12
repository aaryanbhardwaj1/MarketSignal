import Link from "next/link";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { TONE_DOT, type StatusTone } from "./tone";

/** A single business figure: label, value (+unit), context line and provenance line. */
export function MetricCard({
  label,
  value,
  unit,
  context,
  provenance,
  tone,
  href,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  context?: ReactNode;
  provenance?: ReactNode;
  tone?: StatusTone;
  href?: string;
}) {
  const body = (
    <>
      <p className="flex items-center gap-1.5 text-sm text-secondary">
        {tone && <span aria-hidden className={cx("h-2 w-2 rounded-full", TONE_DOT[tone])} />}
        {label}
      </p>
      <p className="mt-1.5 flex items-baseline gap-1 text-xl font-semibold tabular-nums text-primary">
        {value}
        {unit && <span className="text-sm font-medium text-muted">{unit}</span>}
      </p>
      {context && <div className="mt-1 text-sm text-secondary">{context}</div>}
      {provenance && <div className="mt-3 border-t border-border pt-2 text-xs text-muted">{provenance}</div>}
    </>
  );
  const surface = "block rounded-lg border border-border bg-surface p-4";
  if (href) {
    return (
      <Link href={href} className={cx(surface, "transition-colors hover:border-border-strong hover:bg-surface-muted/40")}>
        {body}
      </Link>
    );
  }
  return <div className={surface}>{body}</div>;
}
