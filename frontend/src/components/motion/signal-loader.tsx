import { cx } from "@/lib/cx";

export type SignalLoaderSize = "sm" | "md" | "lg";

const SIZE: Record<SignalLoaderSize, string> = {
  sm: "h-3 w-6",
  md: "h-5 w-10",
  lg: "h-8 w-16",
};

/** The brand waveform: flat, a rising signal, then settling. Normalised to pathLength 120. */
export const SIGNAL_PATH = "M2 20 H12 L17 15 L22 22 L28 8 L34 25 L40 12 L46 18 L51 16 H62";

/**
 * Brand-tied loading indicator: a highlight travels along the signal waveform. Announced as a
 * polite status with `label`; `showLabel` also prints it beside the mark.
 */
export function SignalLoader({
  size = "md",
  label = "Loading",
  showLabel = false,
  className,
}: {
  size?: SignalLoaderSize;
  label?: string;
  showLabel?: boolean;
  className?: string;
}) {
  return (
    <span role="status" className={cx("inline-flex items-center gap-2 text-sm text-muted", className)}>
      <svg aria-hidden viewBox="0 0 64 32" className={cx("shrink-0 overflow-visible", SIZE[size])} fill="none">
        <path d={SIGNAL_PATH} pathLength={120} stroke="var(--color-border-strong)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        <path
          d={SIGNAL_PATH}
          pathLength={120}
          className="ms-signal-travel"
          stroke="var(--color-accent)"
          strokeWidth={2.25}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {showLabel ? <span>{label}</span> : <span className="sr-only">{label}</span>}
    </span>
  );
}
