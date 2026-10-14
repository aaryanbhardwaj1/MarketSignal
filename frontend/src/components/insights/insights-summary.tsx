import { EvidenceBalance } from "@/components/charts/evidence-balance";
import { StackedBar } from "@/components/charts/stacked-bar";
import type { Signal } from "@/lib/api/contracts";
import { formatCount } from "@/lib/format";
import { evidenceTotals, statusCounts } from "@/lib/views/insights";

const STATUS_COLOR: Record<string, string> = {
  strong_evidence: "var(--color-status-strong)",
  emerging: "var(--color-status-emerging)",
  mixed_evidence: "var(--color-status-mixed)",
  needs_validation: "var(--color-status-validation)",
};

/** One compact band: how many findings, how well supported, and how much evidence pushes back. */
export function InsightsSummary({ signals, opportunityCount }: { signals: Signal[]; opportunityCount: number }) {
  const statuses = statusCounts(signals);
  const totals = evidenceTotals(signals);
  return (
    <section
      aria-label="Summary"
      className="grid gap-x-10 gap-y-5 border-b border-border py-5 md:grid-cols-[auto_minmax(0,1fr)_minmax(0,16rem)]"
    >
      <div>
        <p className="text-display font-semibold tabular-nums text-primary">{signals.length}</p>
        <p className="text-sm text-secondary">
          findings
          {opportunityCount > 0 && <> · {formatCount(opportunityCount, "strategic opportunity", "strategic opportunities")}</>}
        </p>
      </div>
      <div className="min-w-0">
        <p className="mb-2 text-xs font-medium text-muted">Evidence status</p>
        <StackedBar
          ariaLabel="Findings by evidence status"
          segments={statuses.map((s) => ({ label: s.label, value: s.count, color: STATUS_COLOR[s.status] }))}
        />
      </div>
      <div className="min-w-0">
        <p className="mb-2 text-xs font-medium text-muted">Evidence balance</p>
        <EvidenceBalance
          supporting={totals.supporting}
          contradicting={totals.contradicting}
          caption={
            totals.withContradictions > 0
              ? `${formatCount(totals.withContradictions, "finding")} with contradicting evidence`
              : "No finding has contradicting evidence"
          }
        />
      </div>
    </section>
  );
}
