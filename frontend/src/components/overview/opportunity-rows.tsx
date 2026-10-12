"use client";

import Link from "next/link";
import { EvidenceBalanceLine, opportunityHref } from "@/components/opportunities/opportunity-card";
import { OpportunityStatusBadge } from "@/components/opportunities/brief-parts";
import type { Opportunity } from "@/lib/api/contracts";

/** Compact opportunity rows for the Overview: status, title, one-line thesis and evidence balance. */
export function OpportunityRows({ ws, opportunities }: { ws: string; opportunities: Opportunity[] }) {
  return (
    <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
      {opportunities.map((o) => (
        <li key={o.id} className="grid gap-x-6 gap-y-2 px-5 py-4 md:grid-cols-[8rem_minmax(0,1fr)]">
          <div className="pt-0.5">
            <OpportunityStatusBadge status={o.status} />
          </div>
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-primary">
              <Link href={opportunityHref(ws, o.id)} className="rounded-sm hover:text-accent-text hover:underline">
                {o.title}
              </Link>
            </h3>
            <p className="mt-0.5 truncate text-base text-secondary" title={o.thesis}>
              {o.thesis}
            </p>
            <div className="mt-1.5">
              <EvidenceBalanceLine opportunity={o} compact />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
