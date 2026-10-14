import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { TONE_DOT, type StatusTone } from "./tone";

export type StatSize = "sm" | "md" | "lg";

/** Direction of a change and whether it is good news; the text of `delta.label` always says it in words. */
export interface StatDelta {
  label: ReactNode;
  direction?: "up" | "down" | "flat";
  /** Colour the delta only when the direction is meaningfully good or bad. Defaults to neutral. */
  sentiment?: "positive" | "negative" | "neutral";
}

const VALUE_SIZE: Record<StatSize, string> = {
  sm: "text-lg",
  md: "text-xl",
  lg: "text-display",
};

const SENTIMENT: Record<NonNullable<StatDelta["sentiment"]>, string> = {
  positive: "text-success",
  negative: "text-danger",
  neutral: "text-muted",
};

const ARROW: Record<NonNullable<StatDelta["direction"]>, string> = { up: "↑", down: "↓", flat: "→" };

/**
 * A single figure without chrome: label, tabular value, optional sub line, delta and a trend slot
 * (pass a `<Sparkline>`). Use in a row separated by whitespace or dividers rather than boxed cards.
 * `tone` adds a small status dot beside the label (never colour alone: the label carries meaning).
 */
export function Stat({
  label,
  value,
  sub,
  delta,
  trend,
  tone,
  size = "md",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  delta?: StatDelta;
  trend?: ReactNode;
  tone?: StatusTone;
  size?: StatSize;
  className?: string;
}) {
  return (
    <div className={cx("flex min-w-0 flex-col", className)}>
      <p className={cx("flex items-center gap-1.5 text-secondary", size === "sm" ? "text-xs" : "text-sm")}>
        {tone && <span aria-hidden className={cx("h-1.5 w-1.5 shrink-0 rounded-full", TONE_DOT[tone])} />}
        {label}
      </p>
      <div className="mt-1 flex items-end gap-3">
        <span className={cx("font-semibold tabular-nums text-primary", VALUE_SIZE[size])}>{value}</span>
        {trend && <div className="mb-1 min-w-0 shrink">{trend}</div>}
      </div>
      {(delta || sub) && (
        <p className="mt-1 flex flex-wrap items-baseline gap-x-2 text-sm">
          {delta && (
            <span className={cx("tabular-nums font-medium", SENTIMENT[delta.sentiment ?? "neutral"])}>
              {delta.direction && <span aria-hidden>{ARROW[delta.direction]} </span>}
              {delta.label}
            </span>
          )}
          {sub && <span className="text-muted">{sub}</span>}
        </p>
      )}
    </div>
  );
}

/** A row of `Stat`s divided by hairlines rather than boxes. */
export function StatRow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cx(
        "grid grid-cols-2 gap-x-6 gap-y-5 sm:flex sm:flex-wrap sm:gap-0 sm:divide-x sm:divide-border",
        "sm:[&>*]:px-6 sm:[&>*:first-child]:pl-0",
        className,
      )}
    >
      {children}
    </div>
  );
}
