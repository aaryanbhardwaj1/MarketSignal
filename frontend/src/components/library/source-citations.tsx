"use client";

import Link from "next/link";
import { useOpenEvidence } from "@/components/opportunities/brief-parts";
import { Card } from "@/components/ui/card";
import { EmptyState, LoadingRegion } from "@/components/ui/states";
import type { EvidenceRef, InsightsBrief } from "@/lib/api/contracts";
import { useInsights } from "@/lib/api/hooks/insights";
import { businessLocator, formatCount } from "@/lib/format";
import { evidenceView } from "@/lib/insights-view";
import { opportunityHref, overviewHref } from "@/lib/routes";

export interface SourceCitation {
  key: string;
  /** What cites the passage: a key signal or a growth opportunity. */
  kind: "Key signal" | "Growth opportunity";
  itemTitle: string;
  href: string;
  ref: EvidenceRef;
}

/** Every passage of this source that the curated brief cites, in brief order. */
export function citationsOf(brief: InsightsBrief, sourceCode: string, ws: string): SourceCitation[] {
  const out: SourceCitation[] = [];
  const overview = overviewHref(ws);
  for (const s of brief.signals) {
    s.evidence.forEach((ref, i) => {
      if (ref.source.code === sourceCode) out.push({ key: `s-${s.id}-${i}`, kind: "Key signal", itemTitle: s.title, href: overview, ref });
    });
  }
  for (const o of brief.opportunities) {
    [...o.supporting, ...o.contradicting].forEach((ref, i) => {
      if (ref.source.code === sourceCode) {
        out.push({ key: `o-${o.id}-${i}`, kind: "Growth opportunity", itemTitle: o.title, href: opportunityHref(ws, o.id), ref });
      }
    });
  }
  return out;
}

function CitationRow({ citation, onOpen }: { citation: SourceCitation; onOpen: ((ref: EvidenceRef) => void) | null }) {
  const view = evidenceView(citation.ref);
  return (
    <li className="px-5 py-4">
      <p className="text-xs text-muted">
        {citation.kind} ·{" "}
        <Link href={citation.href} className="rounded-sm text-secondary hover:text-accent-text hover:underline">
          {citation.itemTitle}
        </Link>
      </p>
      <p className="mt-1 text-sm font-medium text-primary">{businessLocator(view.locator)}</p>
      {view.quote ? (
        <blockquote className="mt-1 line-clamp-3 border-l-2 border-l-cite-evidence pl-3 text-base text-secondary">
          {view.quote}
        </blockquote>
      ) : (
        <p className="mt-1 text-sm text-muted">
          {view.kind === "withdrawn" ? "This passage is no longer available." : "This passage changed since the brief was prepared."}
        </p>
      )}
      {onOpen && view.openable && (
        <button
          type="button"
          onClick={() => onOpen(citation.ref)}
          aria-label={`Open passage: ${businessLocator(view.locator)}`}
          className="mt-2 rounded-sm text-sm font-medium text-accent-text hover:underline"
        >
          Open passage
        </button>
      )}
    </li>
  );
}

/** Passages of this source cited in the curated brief, each opening the evidence drawer. */
export function SourceCitations({ ws, sourceCode }: { ws: string; sourceCode: string }) {
  const brief = useInsights(ws);
  const onOpen = useOpenEvidence();
  if (brief.isPending) return <LoadingRegion label="Loading citations" lines={3} />;
  if (brief.isError || !brief.data.fixture_version) {
    return <p className="text-sm text-muted">The analyst brief is not available, so citations cannot be listed.</p>;
  }
  const citations = citationsOf(brief.data, sourceCode, ws);
  if (citations.length === 0) {
    return (
      <EmptyState
        title="Not cited in the analyst brief"
        description="Research answers can still cite this source. Search the Evidence Library to find its passages."
      />
    );
  }
  return (
    <Card padding="none">
      <p className="border-b border-border px-5 py-2.5 text-sm text-muted">{formatCount(citations.length, "cited passage")}</p>
      <ul className="divide-y divide-border">
        {citations.map((c) => (
          <CitationRow key={c.key} citation={c} onOpen={onOpen} />
        ))}
      </ul>
    </Card>
  );
}
