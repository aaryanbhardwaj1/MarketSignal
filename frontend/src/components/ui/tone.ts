/**
 * Status tones for the design system (plan §2.1 status semantics):
 * success = verified, ready, completed, Supported
 * warn    = degraded, stale, Mixed Evidence, repaired with fallback
 * danger  = failed, withdrawn
 * info    = running, processing, Emerging
 * neutral = cancelled, superseded, Needs Research
 */
export type StatusTone = "success" | "warn" | "danger" | "info" | "neutral";

/** Tone names used by `lib/status.ts` and older components. */
export type LegacyTone = "warning" | "progress" | "muted";

const LEGACY: Record<LegacyTone, StatusTone> = {
  warning: "warn",
  progress: "info",
  muted: "neutral",
};

export function normalizeTone(tone: StatusTone | LegacyTone | undefined): StatusTone {
  if (!tone) return "neutral";
  return tone in LEGACY ? LEGACY[tone as LegacyTone] : (tone as StatusTone);
}

/** Subtle background plus border colour per tone. */
export const TONE_SURFACE: Record<StatusTone, string> = {
  success: "bg-success-subtle border-success/25",
  warn: "bg-warn-subtle border-warn/25",
  danger: "bg-danger-subtle border-danger/25",
  info: "bg-info-subtle border-info/25",
  neutral: "bg-surface-muted border-border",
};

/** Solid dot colour per tone. */
export const TONE_DOT: Record<StatusTone, string> = {
  success: "bg-success",
  warn: "bg-warn",
  danger: "bg-danger",
  info: "bg-info",
  neutral: "bg-text-muted",
};
