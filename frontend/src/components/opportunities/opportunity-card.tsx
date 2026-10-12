"use client";

import Link from "next/link";
import { workspaceBase } from "@/components/shell/nav";
import type { Opportunity } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { evidenceBalance, numbersAllowed, plural, topMetric, type AnalysisIndex } from "@/lib/insights-view";
import { ItemIntegrityIndicator, MetricFigure, OpportunityStatusBadge } from "./brief-parts";

export function opportunityHref(ws: string, id: string): string {
  return `${workspaceBase(ws)}/opportunities/${encodeURIComponent(id)}`;
}

/** Evidence balance as text, so it never depends on colour: "5 supporting · 2 contradicting · 2 gaps". */
export function EvidenceBalanceLine({ opportunity, compact = false }: { opportunity: Opportunity; compact?: boolean }) {
  const b = evidenceBalance(opportunity);
  return (
    <p className={cx("flex flex-wrap items-center gap-y-1 text-secondary", compact ? "gap-x-2 text-xs" : "gap-x-3 text-sm")}>
      <span>
        <span className="font-semibold tabular-nums text-primary">{b.supporting}</span> supporting
      </span>
      <span aria-hidden className="text-disabled">
        ·
      </span>
      <span>
        <span className="font-semibold tabular-nums text-primary">{b.contradicting}</span> contradicting
      </span>
      <span aria-hidden className="text-disabled">
        ·
      </span>
      <span>{plural(b.gaps, "evidence gap")}</span>
      {b.notCurrent > 0 && (
        <>
          <span aria-hidden className="text-disabled">
            ·
          </span>
          <span className="text-warn">{plural(b.notCurrent, "passage")} not current</span>
        </>
      )}
    </p>
  );
}

/** One opportunity on the list page: status first, then the hypothesis and its evidence balance. */
export function OpportunityCard({
  ws,
  opportunity,
  analyses,
}: {
  ws: string;
  opportunity: Opportunity;
  analyses: AnalysisIndex;
}) {
  const metric = topMetric(opportunity, analyses);
  const href = opportunityHref(ws, opportunity.id);
  return (
    <article className="flex flex-col rounded-lg border border-border bg-surface p-5">
      <h2 className="text-md font-semibold text-primary">
        <Link href={href} className="rounded-sm hover:underline">
          {opportunity.title}
        </Link>
      </h2>
      <p className="mt-1.5 text-base text-secondary">{opportunity.thesis}</p>
      <div className="mt-3 flex flex-col gap-1.5 rounded-md bg-surface-muted px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <OpportunityStatusBadge status={opportunity.status} />
          {opportunity.integrity !== "verified" && <ItemIntegrityIndicator value={opportunity.integrity} />}
        </div>
        <p className="text-sm text-secondary">{opportunity.status_rationale}</p>
      </div>
      <div className="mt-4">
        <EvidenceBalanceLine opportunity={opportunity} />
      </div>
      {metric ? (
        <div className="mt-4">
          <MetricFigure metric={metric} compact />
        </div>
      ) : (
        !numbersAllowed(opportunity.integrity) && (
          <p className="mt-4 text-sm text-muted">Figures hidden: could not be re-verified.</p>
        )
      )}
      <div className="mt-auto pt-4">
        <Link
          href={href}
          className="rounded-sm text-sm font-medium text-accent-text hover:underline"
          aria-label={`Review the evidence for ${opportunity.title}`}
        >
          Review the evidence
        </Link>
      </div>
    </article>
  );
}
