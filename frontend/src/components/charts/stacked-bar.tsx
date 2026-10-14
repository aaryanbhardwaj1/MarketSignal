import type { ReactNode } from "react";
import { ChartEmpty, ChartFrame, SERIES_COLORS } from "./chart-frame";
import { defaultFormat, stackShares } from "./scale";

export interface StackSegment {
  label: string;
  value: number;
  /** Optional explicit colour (a token var); defaults to the fixed series order. */
  color?: string;
}

const pct = (share: number) => `${Math.round(share * 100)}%`;

/** 100% composition bar with a legend that carries each label, value and share. */
export function StackedBar({
  segments,
  ariaLabel,
  title,
  caption,
  format = defaultFormat,
  className,
}: {
  segments: readonly StackSegment[];
  ariaLabel: string;
  title?: ReactNode;
  caption?: ReactNode;
  format?: (value: number) => string;
  className?: string;
}) {
  const shares = stackShares(segments.map((s) => s.value));
  if (segments.length === 0 || shares.every((s) => s.share === 0)) return <ChartEmpty />;
  const color = (i: number) => segments[i].color ?? SERIES_COLORS[Math.min(i, SERIES_COLORS.length - 1)];
  const table = { columns: ["Part", "Value", "Share"], rows: segments.map((s, i) => [s.label, format(s.value), pct(shares[i].share)]) };

  return (
    <ChartFrame title={title} caption={caption} ariaLabel={ariaLabel} table={table} className={className}>
      <div aria-hidden className="flex h-3 w-full gap-0.5 overflow-hidden rounded-sm">
        {shares.map((s, i) =>
          s.share > 0 ? (
            <span key={segments[i].label} className="h-full first:rounded-l-sm last:rounded-r-sm" style={{ width: `${s.share * 100}%`, backgroundColor: color(i) }} title={`${segments[i].label}: ${pct(s.share)}`} />
          ) : null,
        )}
      </div>
      <ul aria-hidden className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs">
        {segments.map((s, i) => (
          <li key={s.label} className="inline-flex items-center gap-1.5 text-secondary">
            <span className="h-2 w-2.5 rounded-xs" style={{ backgroundColor: color(i) }} />
            {s.label}
            <span className="font-medium text-primary">{pct(shares[i].share)}</span>
            <span className="text-muted">({format(s.value)})</span>
          </li>
        ))}
      </ul>
    </ChartFrame>
  );
}
