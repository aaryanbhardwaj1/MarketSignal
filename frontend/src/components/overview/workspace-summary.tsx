"use client";

import { MetricCard } from "@/components/ui/metric-card";
import type { WorkspaceOverview } from "@/lib/api/contracts";
import { formatNumber } from "@/lib/format";
import { classBreakdown, researchRunBreakdown, sourceTotal } from "@/lib/insights-view";
import { analyticsHref, askHref, evidenceLibraryHref } from "@/lib/routes";

/**
 * Five headline counts about what the workspace holds. Every figure comes from the workspace
 * endpoint. Five tiles sit on one row from xl; below that they split 3 + 2 on a six-column grid
 * (and 2 + 2 + 1 full-width on small screens), so no row leaves an empty slot.
 */
const FIRST_ROW = "lg:col-span-2 xl:col-span-1";
const SECOND_ROW = "lg:col-span-3 xl:col-span-1";
export function WorkspaceSummary({ ws, overview }: { ws: string; overview: WorkspaceOverview }) {
  const total = sourceTotal(overview);
  const breakdown = classBreakdown(overview);
  const customer = overview.sources_by_class.customer ?? 0;
  const runs = researchRunBreakdown(overview);
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6 xl:grid-cols-5">
      <MetricCard
        label="Evidence sources"
        className={FIRST_ROW}
        value={formatNumber(total)}
        href={evidenceLibraryHref(ws)}
        context={
          <span className="text-xs text-muted">
            {breakdown.map((c) => `${c.count} ${c.label.toLowerCase()}`).join(" · ")}
          </span>
        }
      />
      <MetricCard
        label="Structured datasets"
        className={FIRST_ROW}
        value={formatNumber(overview.dataset_count)}
        href={analyticsHref(ws, "datasets")}
        context={<span className="text-xs text-muted">Tables that figures are computed from</span>}
      />
      <MetricCard
        label="Customer evidence"
        className={FIRST_ROW}
        value={formatNumber(customer)}
        unit={`of ${formatNumber(total)} sources`}
        context={<span className="text-xs text-muted">Sources classed as customer research</span>}
      />
      <MetricCard
        label="Research runs"
        className={SECOND_ROW}
        value={formatNumber(runs.total)}
        href={askHref(ws)}
        context={<span className="text-xs text-muted">{runs.detail ?? "Questions researched in this workspace"}</span>}
      />
      <MetricCard
        label="Saved results"
        className={`sm:col-span-2 ${SECOND_ROW}`}
        value={formatNumber(overview.analytics_result_count)}
        href={analyticsHref(ws, "saved-results")}
        context={<span className="text-xs text-muted">Figures computed while answering research questions</span>}
      />
    </div>
  );
}
