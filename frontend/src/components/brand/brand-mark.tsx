import { cx } from "@/lib/cx";

/** Waveform drawn inside the 24px tile: flat, a dip, then a decisive rise to a node. */
export const MARK_PATH = "M5 15 H8.5 L10.75 11 L13.25 16.5 L18 8";

/**
 * MarketSignal mark: a signal-blue tile with a white waveform rising to a node. Geometric and
 * crisp at 20-28px. Decorative by default; pass `title` when it stands alone.
 */
export function BrandMark({ size = 24, title, className }: { size?: number; title?: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      className={cx("shrink-0", className)}
    >
      <rect width="24" height="24" rx="6" fill="var(--color-accent)" />
      <path d={MARK_PATH} fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="18" cy="8" r="2.1" fill="#fff" />
    </svg>
  );
}

/** "MarketSignal" in Geist with tight tracking; "Signal" carries the accent, quietly. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cx("text-md tracking-tight whitespace-nowrap", className)}>
      <span className="font-medium text-primary">Market</span>
      <span className="font-semibold text-accent-text">Signal</span>
    </span>
  );
}

/** Mark + wordmark lockup. */
export function BrandLockup({ size = 22, className, hideWordmark = false }: { size?: number; className?: string; hideWordmark?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <BrandMark size={size} />
      {hideWordmark ? <span className="sr-only">MarketSignal</span> : <Wordmark />}
    </span>
  );
}

/**
 * Barely-visible signal/grid motif for the top bar behind the brand. Decorative; sits under
 * content (`pointer-events-none`). This is the one documented brand motif.
 */
export function BrandMotif({ className }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 240 52" preserveAspectRatio="none" className={cx("pointer-events-none absolute inset-y-0 left-0 h-full w-60", className)}>
      <defs>
        <linearGradient id="ms-motif-fade" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="var(--color-accent)" stopOpacity="0.09" />
          <stop offset="1" stopColor="var(--color-accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[13, 26, 39].map((y) => (
        <line key={y} x1="0" x2="240" y1={y} y2={y} stroke="url(#ms-motif-fade)" strokeWidth="1" />
      ))}
      <path d="M0 34 H40 L52 28 L64 36 L80 18 L104 30 L124 24 L240 24" fill="none" stroke="url(#ms-motif-fade)" strokeWidth="1.25" />
    </svg>
  );
}
