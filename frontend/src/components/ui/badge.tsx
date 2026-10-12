import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { normalizeTone, type LegacyTone, type StatusTone } from "./tone";

export type BadgeTone = StatusTone | LegacyTone | "accent";

const TONE: Record<StatusTone | "accent", string> = {
  success: "bg-success-subtle text-success border-success/20",
  warn: "bg-warn-subtle text-warn border-warn/20",
  danger: "bg-danger-subtle text-danger border-danger/20",
  info: "bg-info-subtle text-info border-info/20",
  neutral: "bg-surface-muted text-secondary border-border",
  accent: "bg-accent-subtle text-accent-text border-accent/20",
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
        "inline-flex items-center gap-1 whitespace-nowrap rounded-sm border font-medium",
        size === "sm" ? "px-1.5 py-px text-xs" : "px-2 py-0.5 text-sm",
        TONE[key],
      )}
    >
      {children}
    </span>
  );
}
