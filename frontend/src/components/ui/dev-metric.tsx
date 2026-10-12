import type { MetricUnit } from "@/lib/api/contracts";
import { formatMs, formatNumber, formatPercent, formatUsd } from "@/lib/format";
import { Tooltip } from "./tooltip";

export function formatMetricValue(value: number | null | undefined, unit: MetricUnit): string {
  switch (unit) {
    case "ratio":
      return formatNumber(value, 3);
    case "percent":
      return formatPercent(value, { ratio: false });
    case "ms":
      return formatMs(value);
    case "s":
      return value == null ? "-" : `${formatNumber(value, 2)} s`;
    case "usd":
      return formatUsd(value);
    case "tokens":
    case "count":
      return formatNumber(value, 0);
  }
}

export interface MetricSourceRef {
  path: string;
  pointer?: string;
  anchor?: string;
}

/**
 * An evaluation figure for Developer Tools. Confidence interval and sample size are always
 * visible; the artifact path sits in a tooltip so the figure stays traceable.
 */
export function DevMetric({
  label,
  value,
  unit,
  ci,
  n,
  k,
  source,
}: {
  label: string;
  value: number | null;
  unit: MetricUnit;
  ci?: [number, number];
  n?: number;
  k?: number;
  source?: MetricSourceRef;
}) {
  const sourceText = source
    ? `${source.path}${source.pointer ? ` ${source.pointer}` : ""}${source.anchor ? ` #${source.anchor}` : ""}`
    : null;
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-sm text-secondary">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-primary">
        {value == null ? <span className="text-muted">Not measured</span> : formatMetricValue(value, unit)}
      </p>
      <dl className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted">
        {ci && (
          <div className="flex gap-1">
            <dt>95% CI</dt>
            <dd className="tabular-nums">
              {formatMetricValue(ci[0], unit)} to {formatMetricValue(ci[1], unit)}
            </dd>
          </div>
        )}
        {n != null && (
          <div className="flex gap-1">
            <dt>n</dt>
            <dd className="tabular-nums">{formatNumber(n)}</dd>
          </div>
        )}
        {k != null && (
          <div className="flex gap-1">
            <dt>k</dt>
            <dd className="tabular-nums">{formatNumber(k)}</dd>
          </div>
        )}
        {sourceText && (
          <div>
            <Tooltip content={<span className="font-mono">{sourceText}</span>}>
              <button type="button" className="rounded-sm text-xs text-accent-text underline decoration-dotted underline-offset-2">
                Source
              </button>
            </Tooltip>
          </div>
        )}
      </dl>
    </div>
  );
}
