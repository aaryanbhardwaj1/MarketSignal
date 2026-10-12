"use client";

import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import { Badge } from "@/components/ui/badge";
import { LinkButton } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status-indicator";
import type { EvidenceRef, InsightsBrief, ItemIntegrity, OpportunityStatus } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";
import { drawerTarget, type MetricView } from "@/lib/insights-view";
import { integrity as integrityLabel, opportunityStatus } from "@/lib/labels";
import { askHref, evidenceLibraryHref } from "@/lib/routes";

/** Opens a cited passage in the evidence drawer, or null when no drawer is mounted (tests). */
export function useOpenEvidence(): ((ref: EvidenceRef) => void) | null {
  const drawer = useOptionalEvidenceDrawer();
  if (!drawer) return null;
  return (ref) => {
    const target = drawerTarget(ref);
    if (target) drawer.openEvidence(target);
  };
}

export function OpportunityStatusBadge({ status, size = "sm" }: { status: OpportunityStatus; size?: "sm" | "md" }) {
  const entry = opportunityStatus(status);
  return (
    <Badge tone={entry.tone ?? "neutral"} size={size}>
      {entry.label}
    </Badge>
  );
}

/** Integrity of a whole brief item. Verified items show a quiet indicator; others say why. */
export function ItemIntegrityIndicator({ value }: { value: ItemIntegrity }) {
  if (value === "unverified") return <StatusIndicator tone="neutral" label="Could not be re-verified" />;
  const entry = integrityLabel(value);
  return (
    <StatusIndicator
      tone={entry.tone ?? "neutral"}
      label={value === "verified" ? "Verified against current evidence" : entry.label}
      className="text-xs"
    />
  );
}

/**
 * A recomputed figure in compact form (cards and rows). Uses the computed-result rule so it never
 * reads as a quoted passage; a figure that was not recomputed says so instead of showing a number.
 */
export function MetricFigure({ metric, compact = false }: { metric: MetricView; compact?: boolean }) {
  return (
    <div className="min-w-0 border-l-2 border-l-cite-result pl-3">
      {metric.visible ? (
        <p className={cx("font-semibold tabular-nums text-primary", compact ? "text-md" : "text-lg")}>
          {metric.display}
        </p>
      ) : (
        <p className="text-sm font-medium text-muted">Could not be re-verified</p>
      )}
      <p className="text-sm text-secondary">{metric.label}</p>
      {metric.basis && <p className="text-xs text-muted">{metric.basis}</p>}
    </div>
  );
}

/** The brief's provenance line: what it is and when its numbers were last recomputed. */
export function BriefMeta({ brief }: { brief: InsightsBrief }) {
  return (
    <span>
      Curated analyst brief, re-verified against current evidence on {formatDateTime(brief.computed_at)}
    </span>
  );
}

/** Shown when the corpus changed since the brief was written. */
export function DriftCallout({ brief }: { brief: InsightsBrief }) {
  if (brief.corpus_check.status !== "drift") return null;
  return (
    <Callout tone="warn" title="Some brief items could not be re-verified against current evidence">
      Sources have changed since this brief was prepared. Affected items show without figures until an analyst
      reviews them.
    </Callout>
  );
}

/** A workspace without a curated brief (for example a newly onboarded client). */
export function NoBriefState({ ws, subject }: { ws: string; subject: string }) {
  return (
    <EmptyState
      title="No analyst brief for this workspace yet"
      description={`${subject} appear here once an analyst has prepared a brief from this workspace's evidence. You can still browse the evidence or ask a research question.`}
      action={
        <div className="flex flex-wrap justify-center gap-2">
          <LinkButton href={evidenceLibraryHref(ws)}>Open the Evidence Library</LinkButton>
          <LinkButton href={askHref(ws)} variant="ghost">
            Ask MarketSignal
          </LinkButton>
        </div>
      }
    />
  );
}
