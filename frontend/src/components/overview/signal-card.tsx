"use client";

import { ItemIntegrityIndicator, MetricFigure } from "@/components/opportunities/brief-parts";
import { CiteChip, type CiteState } from "@/components/ui/cite-chip";
import type { EvidenceRef, Signal } from "@/lib/api/contracts";
import { metricViews, numbersAllowed, type AnalysisIndex } from "@/lib/insights-view";

const CITE_STATE: Record<EvidenceRef["integrity"], CiteState> = {
  verified: "verified",
  stale: "stale",
  withdrawn: "unverified",
};

/** Up to two figures per card keeps the grid scannable; the rest live on the Analytics page. */
const MAX_METRICS = 2;

function Citations({ evidence, onOpen }: { evidence: EvidenceRef[]; onOpen?: (ref: EvidenceRef) => void }) {
  if (evidence.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-1 gap-y-1.5">
      <span className="mr-1 text-xs text-muted">Evidence</span>
      {evidence.map((ref, i) =>
        ref.integrity === "withdrawn" ? (
          <span
            key={`${ref.handle}-${i}`}
            className="inline-flex h-5 items-center rounded-sm border border-dashed border-border-strong px-1 text-xs text-muted"
            title={`${ref.source.title}: source no longer available`}
          >
            {i + 1} · source no longer available
          </span>
        ) : (
          <CiteChip
            key={`${ref.handle}-${i}`}
            kind="evidence"
            index={i + 1}
            label={`${ref.source.title}, ${ref.locator_label}`}
            state={CITE_STATE[ref.integrity]}
            onOpen={() => onOpen?.(ref)}
          />
        ),
      )}
    </div>
  );
}

/** One key signal: category, claim, up to two recomputed figures and the passages behind it. */
export function SignalCard({
  signal,
  analyses,
  onOpen,
}: {
  signal: Signal;
  analyses: AnalysisIndex;
  onOpen?: (ref: EvidenceRef) => void;
}) {
  const metrics = metricViews(signal, analyses).slice(0, MAX_METRICS);
  return (
    <article className="flex flex-col rounded-lg border border-border bg-surface p-5">
      <div className="flex-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">{signal.category}</p>
      <h3 className="mt-1 text-md font-semibold text-primary">{signal.title}</h3>
      <p className="mt-1.5 text-base text-secondary">{signal.statement}</p>
      {metrics.length > 0 &&
        (numbersAllowed(signal.integrity) ? (
          <div className={metrics.length > 1 ? "mt-4 grid grid-cols-2 gap-4" : "mt-4"}>
            {metrics.map((m) => (
              <MetricFigure key={m.key} metric={m} compact />
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm text-muted">Figures hidden: could not be re-verified.</p>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-border pt-3">
        <Citations evidence={signal.evidence} onOpen={onOpen} />
        <ItemIntegrityIndicator value={signal.integrity} />
      </div>
    </article>
  );
}
