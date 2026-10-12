"use client";

import { workspaceBase } from "@/components/shell/nav";
import { MetricCard } from "@/components/ui/metric-card";
import type { WorkspaceOverview } from "@/lib/api/contracts";
import { formatNumber } from "@/lib/format";
import { classBreakdown, researchRunBreakdown, sourceTotal } from "@/lib/insights-view";

/**
 * Five headline counts about what the workspace holds. Every figure comes from the workspace
 * endpoint. Five tiles fit one row only on wide screens; below that the row wraps 3 + 2 so labels
 * and the source breakdown stay on one line.
 */
export function WorkspaceSummary({ ws, overview }: { ws: string; overview: WorkspaceOverview }) {
  const total = sourceTotal(overview);
  const breakdown = classBreakdown(overview);
  const customer = overview.sources_by_class.customer ?? 0;
  const runs = researchRunBreakdown(overview);
  const base = workspaceBase(ws);
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 min-[1440px]:grid-cols-5">
      <MetricCard
        label="Evidence sources"
        value={formatNumber(total)}
        href={`${base}/evidence`}
        context={
          <span className="text-xs text-muted">
            {breakdown.map((c) => `${c.count} ${c.label.toLowerCase()}`).join(" · ")}
          </span>
        }
      />
      <MetricCard
        label="Structured datasets"
        value={formatNumber(overview.dataset_count)}
        href={`${base}/analytics#datasets`}
        context={<span className="text-xs text-muted">Tables that figures are computed from</span>}
      />
      <MetricCard
        label="Customer evidence"
        value={formatNumber(customer)}
        unit={`of ${formatNumber(total)} sources`}
        context={<span className="text-xs text-muted">Sources classed as customer research</span>}
      />
      <MetricCard
        label="Research runs"
        value={formatNumber(runs.total)}
        href={`${base}/ask`}
        context={<span className="text-xs text-muted">{runs.detail ?? "Questions researched in this workspace"}</span>}
      />
      <MetricCard
        label="Saved results"
        value={formatNumber(overview.analytics_result_count)}
        href={`${base}/analytics#saved-results`}
        context={
<span className="text-xs text-muted">Figures computed while answering research questions</span>
        }
      />
    </div>
  );
}
