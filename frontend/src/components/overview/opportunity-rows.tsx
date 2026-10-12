"use client";

import { EvidenceBalanceLine, OpportunityTitle } from "@/components/opportunities/opportunity-card";
import { Card } from "@/components/ui/card";
import type { Opportunity } from "@/lib/api/contracts";
import { opportunityHref } from "@/lib/routes";

/** Compact opportunity rows for the Overview: title with status, one-line thesis and evidence balance. */
export function OpportunityRows({ ws, opportunities }: { ws: string; opportunities: Opportunity[] }) {
  return (
    <Card padding="none">
      <ul className="divide-y divide-border">
      {opportunities.map((o) => (
        <li key={o.id} className="px-5 py-4">
          <div className="min-w-0">
            <OpportunityTitle level={3} href={opportunityHref(ws, o.id)} title={o.title} status={o.status} />
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
    </Card>
  );
}
