"use client";

import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import type { EvalMetric, EvalSource } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import {
  deltaVerdict,
  formatCi,
  formatCountOf,
  formatSigned,
  gitForPath,
  isKOfN,
  primaryDisplay,
  sha256ForPath,
  shortHash,
  sourceLocator,
  type Direction,
} from "@/lib/eval-view";
import { useCatalogContext } from "./catalog-context";

/**
 * "Source" trigger whose tooltip names the artifact path, JSON pointer (or report anchor),
 * the artifact's sha256 prefix and the git commit of the run that produced it.
 */
export function SourceRef({ path, locator, note }: { path: string; locator?: string; note?: string }) {
  const catalog = useCatalogContext();
  const sha = catalog ? sha256ForPath(catalog, path) : null;
  const git = catalog ? gitForPath(catalog, path) : null;
  return (
    <Tooltip
      content={
        <span className="flex flex-col gap-0.5 font-mono">
          <span className="break-all">{path}</span>
          {locator && <span className="break-all text-secondary">{locator}</span>}
          <span className="text-secondary">sha256 {sha ? shortHash(sha, 12) : "not listed"}</span>
          <span className="text-secondary">git {git ?? "not recorded for this artifact"}</span>
          {note && <span className="font-sans text-muted">{note}</span>}
        </span>
      }
    >
      <button
        type="button"
        aria-label={`Source: ${path}${locator ? ` ${locator}` : ""}`}
        className="rounded-sm text-xs text-accent-text underline decoration-dotted underline-offset-2"
      >
        Source
      </button>
    </Tooltip>
  );
}

export function MetricSource({ source }: { source: EvalSource }) {
  return <SourceRef path={source.path} locator={sourceLocator(source)} />;
}

/** Secondary line under a value: CI, k / n and the source trigger. */
function MetricMeta({ metric, signed = false, extra }: { metric: EvalMetric; signed?: boolean; extra?: ReactNode }) {
  const ci = formatCi(metric, { signed });
  const count = isKOfN(metric) ? null : formatCountOf(metric);
  return (
    <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
      {ci && <span className="tabular-nums">{ci}</span>}
      {count && <span className="tabular-nums">{count}</span>}
      {extra}
      <MetricSource source={metric.source} />
    </span>
  );
}

/** A metric inside a table cell: value, then CI / n / source on a quiet second line. */
export function MetricCell({ metric, align = "right" }: { metric: EvalMetric | undefined; align?: "left" | "right" }) {
  if (!metric) return <span className="text-muted">Not reported</span>;
  return (
    <span className={cx("inline-flex flex-col", align === "right" ? "items-end" : "items-start")}>
      <span className="tabular-nums text-primary">
        {metric.value == null ? <span className="text-muted">Not measured</span> : primaryDisplay(metric)}
      </span>
      <MetricMeta metric={metric} />
    </span>
  );
}

/** A paired delta with its CI and a plain verdict ("Not distinguishable" when the CI crosses 0). */
export function DeltaCell({
  metric,
  direction = "higher",
  resource = false,
}: {
  metric: EvalMetric | null | undefined;
  direction?: Direction;
  resource?: boolean;
}) {
  if (!metric) return <span className="text-xs text-muted">No paired delta recorded</span>;
  const verdict = deltaVerdict(metric, direction, { resource });
  return (
    <span className="inline-flex flex-col items-end">
      <span className="flex items-center gap-2">
        <span className="font-medium tabular-nums text-primary">{formatSigned(metric.value, metric.unit)}</span>
        <Badge tone={verdict.tone}>{verdict.label}</Badge>
      </span>
      <MetricMeta metric={metric} signed />
    </span>
  );
}

/** Summary figure card for headline metrics. CI and n are always visible when recorded. */
export function EvalStat({ metric, note }: { metric: EvalMetric; note?: ReactNode }) {
  return (
    <div className="flex flex-col rounded-lg border border-border bg-surface p-4">
      <p className="text-sm text-secondary">{metric.label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-primary">
        {metric.value == null ? <span className="text-muted">Not measured</span> : primaryDisplay(metric)}
      </p>
      <MetricMeta metric={metric} />
      {note && <p className="mt-2 text-xs text-muted">{note}</p>}
    </div>
  );
}

/** Dense grid of small stat tiles for groups of related measures. */
export function MetricGrid({ metrics, label }: { metrics: EvalMetric[]; label: string }) {
  return (
    <ul aria-label={label} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map((m) => (
        <li key={m.id} className="flex flex-col rounded-lg border border-border bg-surface px-4 py-3">
          <span className="text-sm text-secondary">{m.label}</span>
          <span className="mt-1 text-md font-semibold tabular-nums text-primary">
            {m.value == null ? <span className="text-muted">Not measured</span> : primaryDisplay(m)}
          </span>
          <MetricMeta metric={m} />
        </li>
      ))}
    </ul>
  );
}

/** Two-option (or more) toggle rendered as pressed buttons in a labelled group. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted">{label}</span>
      <div role="group" aria-label={label} className="inline-flex rounded-md border border-border bg-surface-muted p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            aria-pressed={o.value === value}
            onClick={() => onChange(o.value)}
            className={cx(
              "rounded-sm px-2.5 py-1 text-sm font-medium transition-colors",
              o.value === value ? "bg-surface text-primary shadow-sm" : "text-muted hover:text-primary",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
