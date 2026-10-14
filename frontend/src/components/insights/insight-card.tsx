"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { Collapse } from "@/components/motion/collapse";
import { ClaimTag } from "@/components/ui/claim-tag";
import { StatusPill } from "@/components/ui/status-pill";
import type { EvidenceRef, InsightsBrief, Signal } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { numbersAllowed, type AnalysisIndex } from "@/lib/insights-view";
import { outlookNature, relatedLinks, strongestMetric, uniqueSources } from "@/lib/views/insights";
import { InsightDetails } from "./insight-details";
import { EvidenceCount, IntegrityNote, LineLabel, SourceChips, SupportingFigure } from "./insight-parts";

const MAX_ASIDE_LINKS = 2;

/** Forward-looking framing for Future Outlook: a cited forecast, or a hypothesis. Never a fact. */
function OutlookLine({ signal }: { signal: Signal }) {
  const nature = outlookNature(signal);
  return (
    <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-secondary">
      <ClaimTag type={nature.type} explain />
      {nature.type === "forecast" ? (
        <span>Projection stated by {nature.sources.join(", ")}</span>
      ) : (
        <span>No cited source states this projection; treat it as a proposition to test</span>
      )}
    </p>
  );
}

export interface InsightCardProps {
  ws: string;
  signal: Signal;
  brief: Pick<InsightsBrief, "signals" | "opportunities">;
  analyses: AnalysisIndex;
  selected: boolean;
  onToggle: (id: string) => void;
  onOpen?: (ref: EvidenceRef) => void;
  /** Start with details open (tests, deep links). */
  defaultOpen?: boolean;
}

/**
 * One insight as a hairline row: what the evidence says (statement), what it means (implication),
 * the strongest recomputed figure, the evidence balance and the sources. "Details" discloses every
 * cited passage, caveats, gaps and related items.
 */
export function InsightCard({ ws, signal, brief, analyses, selected, onToggle, onOpen, defaultOpen = false }: InsightCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const detailsId = useId();
  const checkboxId = useId();
  const metric = strongestMetric(signal, analyses);
  const withheld = !numbersAllowed(signal.integrity) && signal.metrics.length > 0;
  const outlook = signal.kind === "future_outlook";
  const links = relatedLinks(ws, signal, brief, analyses);
  /** Opportunities first, then analyses; the full list (insights included) is under Details. */
  const primaryLinks = links.filter((l) => l.kind !== "insight").slice(0, MAX_ASIDE_LINKS);

  return (
    <article
      id={signal.id}
      aria-labelledby={`${signal.id}-title`}
      data-selected={selected || undefined}
      className={cx(
        "grid scroll-mt-24 grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3 px-4 py-4 transition-colors duration-(--duration-fast) ease-standard lg:grid-cols-[1.25rem_minmax(0,1fr)_13rem] lg:gap-x-6",
        selected && "bg-accent-subtle/40",
      )}
    >
      <div className="pt-0.5">
        <input
          id={checkboxId}
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(signal.id)}
          aria-label={`Select "${signal.title}" for a presentation`}
          className="h-4 w-4 cursor-pointer rounded-sm accent-accent"
        />
      </div>

      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-xs font-medium text-muted">{signal.category}</span>
          {signal.status && <StatusPill status={signal.status} className="lg:hidden" />}
        </div>
        <h3 id={`${signal.id}-title`} className="mt-1 text-md font-semibold text-primary">
          {signal.title}
        </h3>
        <p className="mt-1.5 max-w-reading text-base text-secondary">
          {signal.statement}
          {signal.claim_type && (
            <>
              {" "}
              <ClaimTag type={signal.claim_type} size="sm" explain />
            </>
          )}
        </p>
        {signal.implication && (
          <p className="mt-2 max-w-reading text-base text-primary">
            <LineLabel>So what</LineLabel>
            {signal.implication.text} <ClaimTag type={signal.implication.claim_type} size="sm" explain />
          </p>
        )}
        {outlook && <OutlookLine signal={signal} />}
        {outlook && signal.gaps.length > 0 && (
          <div className="mt-2 text-sm text-secondary">
            <LineLabel>Open questions</LineLabel>
            <ul className="mt-0.5 list-disc pl-5">
              {signal.gaps.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-2">
          <IntegrityNote integrity={signal.integrity} />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <SourceChips sources={uniqueSources(signal)} onOpen={onOpen ? (s) => onOpen(s.ref) : undefined} />
          <button
            type="button"
            aria-expanded={open}
            aria-controls={detailsId}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1 rounded-sm text-sm text-muted transition-colors duration-(--duration-fast) ease-standard hover:text-primary"
          >
            <ChevronDown
              aria-hidden
              size={14}
              className={cx("transition-transform duration-(--duration-base) ease-standard", open && "rotate-180")}
            />
            {open ? "Hide details" : "Details"}
          </button>
        </div>
        <Collapse open={open} id={detailsId}>
          <InsightDetails signal={signal} links={links} onOpen={onOpen} />
        </Collapse>
      </div>

      <aside
        aria-label="Evidence summary"
        className="col-start-2 mt-3 flex min-w-0 flex-wrap content-start items-start gap-x-6 gap-y-3 lg:col-start-3 lg:row-start-1 lg:mt-0 lg:flex-col lg:flex-nowrap lg:border-l lg:border-border lg:pl-5"
      >
        {signal.status && <StatusPill status={signal.status} className="hidden lg:inline-flex" />}
        {metric ? (
          <SupportingFigure metric={metric} />
        ) : withheld ? (
          <p className="text-xs text-muted">Figures withheld: could not be re-verified.</p>
        ) : null}
        <EvidenceCount supporting={signal.support_count} contradicting={signal.contradiction_count} />
        {primaryLinks.length > 0 && (
          <div className="w-full min-w-0 text-xs">
            <p className="text-muted">Related</p>
            <ul className="mt-0.5 flex flex-col gap-1">
              {primaryLinks.map((l) => (
                <li key={`${l.kind}-${l.id}`} className="line-clamp-2 break-words">
                  <Link href={l.href} className="text-accent-text hover:underline">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </article>
  );
}
