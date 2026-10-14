import { cx } from "@/lib/cx";
import { linePath, linearScale, niceDomain, type Point } from "./scale";

/**
 * Word-sized trend line (fixed size, no axes). Always pass `ariaLabel` describing the trend in
 * words; the last point is marked so the current value reads at a glance.
 */
export function Sparkline({
  values,
  ariaLabel,
  width = 80,
  height = 24,
  emphasis = false,
  className,
}: {
  values: readonly number[];
  ariaLabel: string;
  width?: number;
  height?: number;
  /** Accent colour instead of the neutral grey. */
  emphasis?: boolean;
  className?: string;
}) {
  const finite = values.filter(Number.isFinite);
  if (finite.length < 2) return null;
  const sx = linearScale([0, finite.length - 1], [2, width - 3]);
  const sy = linearScale(niceDomain(finite, { includeZero: false, count: 2 }), [height - 3, 3]);
  const pts: Point[] = finite.map((v, i) => [sx(i), sy(v)]);
  const [lx, ly] = pts[pts.length - 1];
  const stroke = emphasis ? "var(--color-chart-1)" : "var(--color-chart-2)";
  return (
    <svg role="img" aria-label={ariaLabel} width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={cx("shrink-0 overflow-visible", className)}>
      <path d={linePath(pts)} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx} cy={ly} r={2.25} fill={stroke} />
    </svg>
  );
}
