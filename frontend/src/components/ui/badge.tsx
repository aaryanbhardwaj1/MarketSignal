import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { normalizeTone, type LegacyTone, type StatusTone } from "./tone";

export type BadgeTone = StatusTone | LegacyTone | "accent";

const TONE: Record<StatusTone | "accent", string> = {
  success: "bg-success-subtle text-success border-success/15",
  warn: "bg-warn-subtle text-warn border-warn/15",
  danger: "bg-danger-subtle text-danger border-danger/15",
  info: "bg-info-subtle text-info border-info/15",
  neutral: "bg-neutral-subtle text-secondary border-border",
  accent: "bg-accent-subtle text-accent-text border-accent/15",
};

/** Small label. Tone adds meaning only alongside the text, never instead of it. */
export function Badge({
  tone = "neutral",
  size = "sm",
  title,
  children,
}: {
  tone?: BadgeTone;
  size?: "sm" | "md";
  title?: string;
  children: ReactNode;
}) {
  const key = tone === "accent" ? "accent" : normalizeTone(tone);
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-md border font-medium tabular-nums [&_svg]:size-3",
        size === "sm" ? "h-5 px-1.5 text-xs" : "h-6 px-2 text-sm",
        TONE[key],
      )}
    >
      {children}
    </span>
  );
}
