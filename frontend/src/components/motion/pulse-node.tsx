import { cx } from "@/lib/cx";

export type PulseTone = "accent" | "success" | "warn" | "danger" | "neutral";

const DOT: Record<PulseTone, string> = {
  accent: "bg-accent",
  success: "bg-success",
  warn: "bg-warn",
  danger: "bg-danger",
  neutral: "bg-text-muted",
};

/** A node that softly pulses while `active` (a live run, a step in progress). Decorative. */
export function PulseNode({
  tone = "accent",
  active = true,
  size = "md",
  className,
}: {
  tone?: PulseTone;
  active?: boolean;
  size?: "sm" | "md";
  className?: string;
}) {
  const dim = size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";
  return (
    <span aria-hidden className={cx("relative inline-flex shrink-0", dim, className)}>
      {active && <span className={cx("ms-pulse-ring absolute inset-0 rounded-full", DOT[tone])} />}
      <span className={cx("relative inline-flex rounded-full", dim, DOT[tone])} />
    </span>
  );
}
