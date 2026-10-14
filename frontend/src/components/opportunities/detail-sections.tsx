"use client";

import { MessageSquareText } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { HBarChart } from "@/components/charts";
import { LinkButton } from "@/components/ui/button";
import { ClaimTag } from "@/components/ui/claim-tag";
import { SectionHeader } from "@/components/ui/section-header";
import { Stat, StatRow } from "@/components/ui/stat";
import type { EvidenceRef, Opportunity, OpportunityRisk } from "@/lib/api/contracts";
import { formatCount } from "@/lib/format";
import type { AnalysisIndex, MetricView } from "@/lib/insights-view";
import {
  comparableGroups,
  formatMetricValue,
  investigateHref,
  orderEvidence,
  type ComparableGroup,
  type RelatedLink,
} from "@/lib/views/opportunities";
import { EvidenceItem } from "./evidence-item";
import { EvidenceChip } from "./opportunity-parts";

type OnOpen = ((ref: EvidenceRef) => void) | undefined;

/** A titled page section; the heading labels the landmark. */
export function DetailSection({
  id,
  title,
  description,
  action,
  children,
}: {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={`${id}-heading`} className="flex flex-col gap-4">
      <SectionHeader id={`${id}-heading`} title={title} description={description} action={action} />
      {children}
    </section>
  );
}

function EvidenceColumn({
  title,
  description,
  items,
  empty,
  onOpen,
}: {
  title: string;
  description: string;
  items: EvidenceRef[];
  empty: string;
  onOpen: OnOpen;
}) {
  return (
    <div className="min-w-0">
      <h3 className="text-base font-semibold text-primary">
        {title} <span className="font-normal tabular-nums text-muted">({items.length})</span>
      </h3>
      <p className="mt-0.5 text-sm text-muted">{description}</p>
      {items.length === 0 ? (
        <p className="mt-3 rounded-lg border border-dashed border-border-strong px-4 py-3 text-sm text-muted">{empty}</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-3">
          {orderEvidence(items).map((e, i) => (
            <EvidenceItem key={`${e.handle}-${i}`} evidence={e} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Supporting and contradicting passages side by side on wide screens; contradictions are never hidden. */
export function EvidenceColumns({ opportunity, onOpen }: { opportunity: Opportunity; onOpen: OnOpen }) {
  return (
    <DetailSection
      id="evidence"
      title="Evidence for and against"
      description="Cited passages, strongest first. Open a passage to read it in context."
    >
      <div className="grid gap-8 lg:grid-cols-2">
        <EvidenceColumn
          title="Supporting evidence"
          description="Passages consistent with the thesis."
          items={opportunity.supporting}
          empty="No supporting passages cited."
          onOpen={onOpen}
        />
        <EvidenceColumn
          title="Contradicting evidence"
          description="Passages that weaken or complicate it."
          items={opportunity.contradicting}
          empty="No contradicting passages cited. Absence of counter-evidence is not proof."
          onOpen={onOpen}
        />
      </div>
    </DetailSection>
  );
}

function FigureStat({ metric }: { metric: MetricView }) {
  return (
    <Stat
      size="sm"
      label={metric.label}
      value={metric.visible ? metric.display : <span className="text-base font-medium text-muted">Not shown</span>}
      sub={metric.visible ? (metric.basis ?? undefined) : "Could not be re-verified against current data"}
      className="max-w-64"
    />
  );
}

function GroupChart({ group }: { group: ComparableGroup }) {
  const bases = group.items.filter((i) => i.view.base).map((i) => `${i.group}: ${i.view.baseLabel.toLowerCase()} ${i.view.base}`);
  return (
    <HBarChart
      title={<span className="text-sm font-medium text-primary">{group.measure}</span>}
      ariaLabel={`${group.measure}, by group`}
      data={group.items.map((i, n) => ({ label: i.group, value: i.value, emphasis: n === 0 }))}
      format={(v) => formatMetricValue(group.unit, v)}
      valueLabel={group.measure}
      caption={bases.length > 0 ? bases.join(" · ") : undefined}
      labelWidth="9rem"
    />
  );
}

/** Recomputed figures: comparable values share a chart, the rest are plain stats with their bases. */
export function QuantSignals({
  opportunity,
  analyses,
  showNumbers,
}: {
  opportunity: Opportunity;
  analyses: AnalysisIndex;
  showNumbers: boolean;
}) {
  if (opportunity.metrics.length === 0) return null;
  const { groups, singles } = comparableGroups(opportunity, analyses);
  return (
    <DetailSection
      id="figures"
      title={
        <span className="inline-flex items-center gap-2">
          Quantitative signals <ClaimTag type="derived" size="sm" explain />
        </span>
      }
      description="Recomputed from the structured datasets each time this page loads."
    >
      {showNumbers ? (
        <div className="flex flex-col gap-6">
          {groups.map((g) => (
            <GroupChart key={`${g.unit}-${g.measure}`} group={g} />
          ))}
          {singles.length > 0 && (
            <StatRow>
              {singles.map((m) => (
                <FigureStat key={m.key} metric={m} />
              ))}
            </StatRow>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted">Figures are withheld until this opportunity can be re-verified against current data.</p>
      )}
    </DetailSection>
  );
}

function RiskItem({ risk, onOpen }: { risk: OpportunityRisk; onOpen: OnOpen }) {
  return (
    <li className="py-4 first:pt-0 last:pb-0">
      <p className="text-base text-primary">
        {risk.text}
        <ClaimTag type={risk.claim_type} size="sm" className="ml-2" />
      </p>
      {risk.integrity !== "verified" && (
        <p className="mt-1 text-xs text-status-mixed">Some evidence for this risk changed or is no longer available.</p>
      )}
      {risk.evidence.length > 0 && (
        <ul aria-label="Evidence for this risk" className="mt-2 flex flex-wrap gap-1.5">
          {risk.evidence.map((e, i) => (
            <li key={`${e.handle}-${i}`} className="max-w-full">
              <EvidenceChip evidence={e} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function RiskList({ risks, onOpen }: { risks: OpportunityRisk[]; onOpen: OnOpen }) {
  if (risks.length === 0) return null;
  return (
    <DetailSection id="risks" title="Risks and blockers" description="What could stop this from working, with the evidence behind each.">
      <ul className="flex flex-col divide-y divide-border">
        {risks.map((r, i) => (
          <RiskItem key={`${i}-${r.text}`} risk={r} onOpen={onOpen} />
        ))}
      </ul>
    </DetailSection>
  );
}

export function GapList({ gaps }: { gaps: string[] }) {
  return (
    <DetailSection id="gaps" title="Evidence gaps" description={gaps.length > 0 ? `${formatCount(gaps.length, "open question")} the evidence does not yet answer.` : undefined}>
      {gaps.length === 0 ? (
        <p className="text-sm text-muted">No gaps recorded.</p>
      ) : (
        <ul className="flex list-disc flex-col gap-1.5 pl-5 text-base text-secondary">
          {gaps.map((g) => (
            <li key={g}>{g}</li>
          ))}
        </ul>
      )}
    </DetailSection>
  );
}

/** The grounded next research question, with a hand-off to Chat that prefills the composer. */
export function NextInvestigation({ ws, opportunity }: { ws: string; opportunity: Opportunity }) {
  const question = opportunity.next_investigation;
  return (
    <DetailSection id="next" title="Recommended next investigation">
      {question ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-md font-medium text-primary">{question}</p>
          <LinkButton
            href={investigateHref(ws, question)}
            variant="secondary"
            size="sm"
            iconLeft={<MessageSquareText aria-hidden size={14} strokeWidth={1.75} />}
          >
            Investigate in Chat
          </LinkButton>
        </div>
      ) : null}
      {opportunity.next_step && (
        <p className="text-sm text-secondary">
          <span className="font-medium text-primary">Suggested next step: </span>
          {opportunity.next_step}
        </p>
      )}
    </DetailSection>
  );
}

function LinkList({ label, links }: { label: string; links: RelatedLink[] }) {
  if (links.length === 0) return null;
  return (
    <div className="min-w-0">
      <h3 className="text-sm font-medium text-muted">{label}</h3>
      <ul className="mt-2 flex flex-col gap-1.5">
        {links.map((l) => (
          <li key={l.id} className="text-base">
            <Link href={l.href} className="rounded-sm text-accent-text hover:underline">
              {l.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RelatedSection({ insights, analyses }: { insights: RelatedLink[]; analyses: RelatedLink[] }) {
  if (insights.length === 0 && analyses.length === 0) return null;
  return (
    <DetailSection id="related" title="Related" description="The insights and analyses this opportunity draws on.">
      <div className="grid gap-6 md:grid-cols-2">
        <LinkList label="Insights" links={insights} />
        <LinkList label="Analyses" links={analyses} />
      </div>
    </DetailSection>
  );
}
