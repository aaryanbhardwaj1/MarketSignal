"use client";

import { FileText } from "lucide-react";
import Link from "next/link";
import { ClaimTag } from "@/components/ui/claim-tag";
import type { ItemIntegrity } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { formatCount } from "@/lib/format";
import type { MetricView } from "@/lib/insights-view";
import type { RelatedLink, SourceChip } from "@/lib/views/insights";

/** Small uppercase-free label that introduces a line ("So what", "Forecast"). */
export function LineLabel({ children }: { children: string }) {
  return <span className="mr-1.5 text-xs font-medium text-muted">{children}</span>;
}

/** The one supporting figure: value, its base, and the Derived tag. */
export function SupportingFigure({ metric }: { metric: MetricView }) {
  return (
    <div className="min-w-0">
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-semibold tabular-nums text-primary">{metric.display}</span>
        <ClaimTag type="derived" size="sm" />
      </div>
      <p className="mt-0.5 text-xs text-secondary">{metric.label}</p>
      {metric.base && (
        <p className="text-xs text-muted">
          {metric.baseLabel} <span className="tabular-nums">{metric.base}</span>
        </p>
      )}
    </div>
  );
}

/** "3 supporting · 1 contradicting" with a hairline balance bar; contradictions are never hidden. */
export function EvidenceCount({ supporting, contradicting }: { supporting: number; contradicting: number }) {
  const total = supporting + contradicting;
  return (
    <div className="min-w-0">
      <p className="text-xs text-secondary tabular-nums">
        {formatCount(supporting, "supporting", "supporting")}
        <span aria-hidden className="text-muted"> · </span>
        <span className={cx(contradicting > 0 && "font-medium text-status-mixed")}>
          {formatCount(contradicting, "contradicting", "contradicting")}
        </span>
      </p>
      {total > 0 && (
        <div aria-hidden className="mt-1 flex h-1 w-24 gap-px overflow-hidden rounded-full bg-sunken">
          <span className="h-full bg-accent" style={{ width: `${(supporting / total) * 100}%` }} />
          {contradicting > 0 && (
            <span className="h-full bg-chart-negative" style={{ width: `${(contradicting / total) * 100}%` }} />
          )}
        </div>
      )}
    </div>
  );
}

/** The honest state of an item whose evidence changed or could not be re-verified. */
export function IntegrityNote({ integrity }: { integrity: ItemIntegrity }) {
  if (integrity === "verified") return null;
  return (
    <p className="text-xs text-status-mixed">
      {integrity === "unverified"
        ? "Could not be re-verified against current evidence. Figures are withheld."
        : "Some cited passages changed or are no longer available."}
    </p>
  );
}

/** Source titles; each opens its first cited passage in the evidence drawer. */
export function SourceChips({ sources, onOpen }: { sources: SourceChip[]; onOpen?: (chip: SourceChip) => void }) {
  if (sources.length === 0) return null;
  return (
    <ul aria-label="Sources" className="flex flex-wrap gap-1.5">
      {sources.map((s) => (
        <li key={s.code}>
          {s.available && onOpen ? (
            <button
              type="button"
              onClick={() => onOpen(s)}
              className="inline-flex h-6 max-w-64 items-center gap-1.5 rounded-md border border-border bg-surface px-2 text-xs text-secondary transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong hover:text-primary"
            >
              <FileText aria-hidden size={12} strokeWidth={1.75} className="shrink-0 text-muted" />
              <span className="truncate">{s.title}</span>
            </button>
          ) : (
            <span
              className={cx(
                "inline-flex h-6 max-w-64 items-center gap-1.5 rounded-md border px-2 text-xs text-muted",
                s.available ? "border-border" : "border-dashed border-border-strong",
              )}
            >
              <span className="truncate">{s.title}</span>
              {!s.available && <span className="shrink-0">· no longer available</span>}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

const RELATED_KIND: Record<RelatedLink["kind"], string> = {
  opportunity: "Opportunity",
  analysis: "Analysis",
  insight: "Insight",
};

export function RelatedLinks({ links }: { links: RelatedLink[] }) {
  if (links.length === 0) return null;
  return (
    <ul aria-label="Related" className="flex flex-col gap-1">
      {links.map((l) => (
        <li key={`${l.kind}-${l.id}`} className="text-sm">
          <span className="mr-2 inline-block w-20 text-xs text-muted">{RELATED_KIND[l.kind]}</span>
          <Link href={l.href} className="text-accent-text hover:underline">
            {l.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}
