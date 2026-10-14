"use client";

import Link from "next/link";
import type { Opportunity } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { formatCount } from "@/lib/format";
import { evidenceBalance, type AnalysisIndex } from "@/lib/insights-view";
import { ClaimTag } from "@/components/ui/claim-tag";
import { StatusPill } from "@/components/ui/status-pill";
import { gapLabel, leadSignal, sourceMix } from "@/lib/views/opportunities";
import { OpportunityStatusBadge } from "./brief-parts";
import { opportunityHref } from "@/lib/routes";
import { EvidenceTally, FieldLabel, GapCount, IntegrityNotice, LeadSignalView, SourceMix } from "./opportunity-parts";

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
      <span className={b.contradicting > 0 ? "text-contradicting" : undefined}>
        <span className="font-semibold tabular-nums">{b.contradicting}</span> contradicting
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

/**
 * One opportunity on the list page, as a row: title, status and thesis on the left; the lead
 * signal, the evidence balance with open gaps, and the source mix to the right. Scannable in a
 * glance; the detail page carries the evidence itself.
 */
export function OpportunityCard({
  ws,
  opportunity,
  analyses,
}: {
  ws: string;
  opportunity: Opportunity;
  analyses: AnalysisIndex;
}) {
  const href = opportunityHref(ws, opportunity.id);
  const lead = leadSignal(opportunity, analyses);
  const balance = evidenceBalance(opportunity);
  return (
    <article
      aria-labelledby={`opp-${opportunity.id}`}
      className="grid gap-x-8 gap-y-4 py-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,0.9fr)]"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h2 id={`opp-${opportunity.id}`} className="text-md font-semibold text-primary">
            <Link href={href} className="rounded-sm hover:text-accent-text hover:underline">
              {opportunity.title}
            </Link>
          </h2>
          <StatusPill status={opportunity.status} />
        </div>
        <p className="mt-2 max-w-reading text-base text-secondary">
          {opportunity.thesis}
          {opportunity.thesis_claim_type && (
            <ClaimTag type={opportunity.thesis_claim_type} size="sm" className="ml-2" />
          )}
        </p>
        <div className="mt-2">
          <IntegrityNotice integrity={opportunity.integrity} />
        </div>
        <Link
          href={href}
          aria-label={`Review the evidence for ${opportunity.title}`}
          className="mt-3 inline-block rounded-sm text-sm font-medium text-accent-text hover:underline"
        >
          Review the evidence
        </Link>
      </div>
      <div className="min-w-0">
        <FieldLabel>Lead signal</FieldLabel>
        <div className="mt-1.5">
          <LeadSignalView lead={lead} />
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        <div>
          <FieldLabel>Evidence</FieldLabel>
          <div className="mt-1.5 flex flex-col gap-1">
            <EvidenceTally supporting={balance.supporting} contradicting={balance.contradicting} />
            <GapCount count={balance.gaps} label={gapLabel(balance.gaps)} />
          </div>
        </div>
        <div>
          <FieldLabel>Sources</FieldLabel>
          <div className="mt-1.5">
            <SourceMix mix={sourceMix(opportunity)} />
          </div>
        </div>
      </div>
    </article>
  );
}
