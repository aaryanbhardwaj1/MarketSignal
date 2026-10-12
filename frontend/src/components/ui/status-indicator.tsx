import { cx } from "@/lib/cx";
import { TONE_DOT, normalizeTone, type LegacyTone, type StatusTone } from "./tone";

/** A coloured dot plus a text label: status is never conveyed by colour alone. */
export function StatusIndicator({
  tone,
  label,
  detail,
  className,
}: {
  tone: StatusTone | LegacyTone;
  label: string;
  detail?: string;
  className?: string;
}) {
  const t = normalizeTone(tone);
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-sm text-primary", className)}>
      <span aria-hidden className={cx("h-2 w-2 shrink-0 rounded-full", TONE_DOT[t])} />
      <span className="font-medium">{label}</span>
      {detail && <span className="text-muted">{detail}</span>}
    </span>
  );
}
