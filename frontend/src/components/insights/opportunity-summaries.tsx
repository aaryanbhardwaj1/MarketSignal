"use client";

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { ClaimTag } from "@/components/ui/claim-tag";
import { StatusPill } from "@/components/ui/status-pill";
import type { Opportunity } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { opportunityHref } from "@/lib/routes";
import { EvidenceCount } from "./insight-parts";

/**
 * Strategic Opportunities as compact summaries: title, status, thesis and evidence balance.
 * The full case (risks, gaps, next investigation) lives in Growth Opportunities.
 */
export function OpportunitySummaries({
  ws,
  opportunities,
  isSelected,
  onToggle,
}: {
  ws: string;
  opportunities: Opportunity[];
  isSelected: (id: string) => boolean;
  onToggle: (id: string) => void;
}) {
  return (
    <ul className="grid gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-2">
      {opportunities.map((o) => {
        const selected = isSelected(o.id);
        return (
          <li
            key={o.id}
            className={cx("flex gap-3 bg-surface px-4 py-4", selected && "bg-accent-subtle/40")}
          >
            <input
              type="checkbox"
              checked={selected}
              onChange={() => onToggle(o.id)}
              aria-label={`Select "${o.title}" for a presentation`}
              className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded-sm accent-accent"
            />
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <Link
                  href={opportunityHref(ws, o.id)}
                  className="group inline-flex items-start gap-1 text-md font-semibold text-primary hover:text-accent-text"
                >
                  {o.title}
                  <ArrowUpRight aria-hidden size={14} className="mt-1 shrink-0 text-muted group-hover:text-accent-text" />
                </Link>
                <StatusPill status={o.status} />
              </div>
              {/* The tag leads the thesis so clamping can never hide it. */}
              <p className="line-clamp-2 text-sm text-secondary">
                {o.thesis_claim_type && (
                  <>
                    <ClaimTag type={o.thesis_claim_type} size="sm" />{" "}
                  </>
                )}
                {o.thesis}
              </p>
              <EvidenceCount supporting={o.support_count} contradicting={o.contradiction_count} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
