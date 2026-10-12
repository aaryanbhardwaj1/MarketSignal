"use client";

import Link from "next/link";
import type { Opportunity } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { formatCount } from "@/lib/format";
import { evidenceBalance, numbersAllowed, topMetric, type AnalysisIndex } from "@/lib/insights-view";
import { Card } from "@/components/ui/card";
import { ItemIntegrityIndicator, MetricFigure, OpportunityStatusBadge } from "./brief-parts";
import { opportunityHref } from "@/lib/routes";

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
      <span>{formatCount(b.gaps, "evidence gap")}</span>
      {b.notCurrent > 0 && (
        <>
          <span aria-hidden className="text-disabled">
            ·
          </span>
          <span className="text-warn">{formatCount(b.notCurrent, "passage")} not current</span>
        </>
      )}
    </p>
  );
}

/**
 * An opportunity's title with its status badge beside it: the one placement used on Overview,
 * the list and (as the page title) the detail page.
 */
export function OpportunityTitle({
  level,
  href,
  title,
  status,
}: {
  level: 2 | 3;
  href: string;
  title: string;
  status: Opportunity["status"];
}) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
      <Heading className={cx("min-w-0 font-semibold text-primary", level === 2 ? "text-md" : "text-base")}>
        <Link href={href} className="rounded-sm hover:text-accent-text hover:underline">
          {title}
        </Link>
      </Heading>
      <OpportunityStatusBadge status={status} />
    </div>
  );
}

/** One opportunity on the list page: title and status, then the hypothesis and its evidence balance. */
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
    <Card as="article" className="flex flex-col">
      <OpportunityTitle level={2} href={href} title={opportunity.title} status={opportunity.status} />
      <p className="mt-1.5 text-base text-secondary">{opportunity.thesis}</p>
      <p className="mt-2 text-sm text-muted">{opportunity.status_rationale}</p>
      {opportunity.integrity !== "verified" && (
        <div className="mt-2">
          <ItemIntegrityIndicator value={opportunity.integrity} />
        </div>
      )}
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
    </Card>
  );
}
