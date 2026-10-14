"use client";

import { ClaimTag } from "@/components/ui/claim-tag";
import { SERIES_COLORS } from "@/components/charts";
import type { EvidenceRef, ItemIntegrity } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { businessLocator } from "@/lib/format";
import type { MetricView } from "@/lib/insights-view";
import type { LeadSignal, SourceMixEntry } from "@/lib/views/opportunities";

/** Small label that introduces a value ("Lead signal", "Evidence"). */
export function FieldLabel({ children }: { children: string }) {
  return <p className="text-xs font-medium text-muted">{children}</p>;
}

/** "5 supporting · 2 contradicting" with a hairline balance bar; contradictions are never hidden. */
export function EvidenceTally({ supporting, contradicting }: { supporting: number; contradicting: number }) {
  const total = supporting + contradicting;
  return (
    <div className="min-w-0">
      <p className="text-sm tabular-nums text-secondary">
        <span className="font-semibold text-primary">{supporting}</span> supporting
        <span aria-hidden className="text-muted">
          {" · "}
        </span>
        <span className={cx(contradicting > 0 && "text-status-mixed")}>
          <span className="font-semibold">{contradicting}</span> contradicting
        </span>
      </p>
      {total > 0 && (
        <div aria-hidden className="mt-1.5 flex h-1 w-28 gap-px overflow-hidden rounded-full bg-sunken">
          <span className="h-full bg-accent" style={{ width: `${(supporting / total) * 100}%` }} />
          {contradicting > 0 && (
            <span className="h-full bg-chart-negative" style={{ width: `${(contradicting / total) * 100}%` }} />
          )}
        </div>
      )}
    </div>
  );
}

/** Where the cited evidence comes from: a thin composition bar plus the counts in words. */
export function SourceMix({ mix }: { mix: SourceMixEntry[] }) {
  const total = mix.reduce((n, m) => n + m.count, 0);
  if (total === 0) return null;
  const color = (i: number) => SERIES_COLORS[Math.min(i, SERIES_COLORS.length - 1)];
  return (
    <div className="min-w-0">
      <div aria-hidden className="flex h-1 w-28 gap-px overflow-hidden rounded-full">
        {mix.map((m, i) => (
          <span key={m.code} className="h-full" style={{ width: `${(m.count / total) * 100}%`, backgroundColor: color(i) }} />
        ))}
      </div>
      <ul aria-label="Evidence by source type" className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-secondary">
        {mix.map((m, i) => (
          <li key={m.code} className="inline-flex items-center gap-1">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color(i) }} />
            {m.label} <span className="tabular-nums text-primary">{m.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A recomputed figure: value with the Derived tag, its label and its base. */
export function FigureLine({ metric }: { metric: MetricView }) {
  return (
    <div className="min-w-0">
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-semibold tabular-nums text-primary">{metric.display}</span>
        <ClaimTag type="derived" size="sm" />
      </div>
      <p className="mt-0.5 text-sm text-secondary">{metric.label}</p>
      {metric.base && (
        <p className="text-xs text-muted">
          {metric.baseLabel} <span className="tabular-nums">{metric.base}</span>
        </p>
      )}
    </div>
  );
}

/** The one signal a summary leads with: a figure, else a short supporting passage. */
export function LeadSignalView({ lead }: { lead: LeadSignal }) {
  if (lead.kind === "metric") return <FigureLine metric={lead.metric} />;
  if (lead.kind === "quote") {
    return (
      <figure className="min-w-0">
        <blockquote className="border-l-2 border-border-strong pl-2.5 text-sm text-secondary">“{lead.text}”</blockquote>
        <figcaption className="mt-1 flex items-center gap-2 text-xs text-muted">
          <ClaimTag type="observed" size="sm" />
          <span className="truncate">{lead.source}</span>
        </figcaption>
      </figure>
    );
  }
  if (lead.kind === "withheld") {
    return <p className="text-sm text-muted">Figures withheld: could not be re-verified against current data.</p>;
  }
  return <p className="text-sm text-muted">No figure or passage cited yet.</p>;
}

/** The honest state of an item whose evidence changed or could not be re-verified. */
export function IntegrityNotice({ integrity }: { integrity: ItemIntegrity }) {
  if (integrity === "verified") return null;
  return (
    <p className="text-xs text-status-mixed">
      {integrity === "unverified"
        ? "Could not be re-verified against current evidence. Figures are withheld."
        : "Some cited passages changed or are no longer available."}
    </p>
  );
}

/**
 * A cited source as a small chip; it opens the passage in the evidence drawer. A withdrawn source,
 * or no drawer (static render), shows a quiet non-interactive label instead.
 */
export function EvidenceChip({ evidence, onOpen }: { evidence: EvidenceRef; onOpen?: (ref: EvidenceRef) => void }) {
  const where = businessLocator(evidence.locator_label);
  const label = [evidence.source.title, where].filter(Boolean).join(", ");
  const withdrawn = evidence.integrity === "withdrawn";
  const state = withdrawn ? "no longer available" : evidence.integrity === "stale" ? "source updated" : null;
  const body = (
    <>
      <span className="truncate">{evidence.source.title}</span>
      {where && <span className="shrink-0 text-muted">· {where}</span>}
      {state && <span className="shrink-0 text-status-mixed">· {state}</span>}
    </>
  );
  const base = "inline-flex h-6 max-w-full items-center gap-1 rounded-md border px-2 text-xs";
  if (!onOpen || withdrawn) {
    return <span className={cx(base, "text-secondary", state ? "border-dashed border-border-strong" : "border-border")}>{body}</span>;
  }
  return (
    <button
      type="button"
      onClick={() => onOpen(evidence)}
      aria-label={`Open source passage: ${label}${state ? ` (${state})` : ""}`}
      className={cx(
        base,
        "bg-surface text-secondary transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong hover:text-primary",
        state ? "border-dashed border-border-strong" : "border-border",
      )}
    >
      {body}
    </button>
  );
}

/** "2 open gaps" with a quiet marker; zero gaps reads calmly. */
export function GapCount({ count, label }: { count: number; label: string }) {
  return (
    <p className={cx("text-sm tabular-nums", count > 0 ? "text-secondary" : "text-muted")}>
      {count > 0 && <span aria-hidden className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full border border-status-validation" />}
      {label}
    </p>
  );
}
