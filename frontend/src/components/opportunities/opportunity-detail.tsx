"use client";

import { LinkButton } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { ResultPanel } from "@/components/ui/result-panel";
import { Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import type { EvidenceRef, InsightsBrief, Opportunity } from "@/lib/api/contracts";
import { useAnalyses, useInsights } from "@/lib/api/hooks/insights";
import { formatNumber } from "@/lib/format";
import { indexAnalyses, metricViews, numbersAllowed, type AnalysisIndex, type MetricView } from "@/lib/insights-view";
import { BriefMeta, DriftCallout, ItemIntegrityIndicator, MetricFigure, NoBriefState, OpportunityStatusBadge, useOpenEvidence } from "./brief-parts";
import { EvidenceItem } from "./evidence-item";
import { useDocumentTitle } from "@/lib/use-document-title";
import { opportunitiesHref } from "@/lib/routes";

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
  onOpen?: (ref: EvidenceRef) => void;
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
          {items.map((e, i) => (
            <EvidenceItem key={`${e.handle}-${i}`} evidence={e} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </div>
  );
}

function QuantPanel({ metric }: { metric: MetricView }) {
  if (!metric.provenance) return <MetricFigure metric={metric} />;
  const denominator = !metric.visible
    ? undefined
    : metric.base
      ? { label: metric.baseLabel, value: metric.base }
      : metric.provenance.rowsMatched != null
        ? { label: "Based on", value: `${formatNumber(metric.provenance.rowsMatched)} records` }
        : undefined;
  return (
    <ResultPanel
      title={metric.label}
      value={metric.visible ? metric.display : undefined}
      unit=""
      denominator={denominator}
      provenance={{
        sourceTitle: metric.provenance.sourceTitle,
        sourceCode: metric.provenance.sourceCode,
        version: metric.provenance.version,
        table: metric.provenance.table,
      }}
    >
      {!metric.visible && <p className="text-sm text-muted">Could not be re-verified against the current data.</p>}
    </ResultPanel>
  );
}

/** The detail body, separated from data loading so it renders from fixtures in tests. */
export function OpportunityDetailView({
  ws,
  brief,
  opportunity,
  analyses,
  onOpen,
}: {
  ws: string;
  brief: InsightsBrief;
  opportunity: Opportunity;
  analyses: AnalysisIndex;
  onOpen?: (ref: EvidenceRef) => void;
}) {
  const metrics = metricViews(opportunity, analyses);
  const showNumbers = numbersAllowed(opportunity.integrity);
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Growth Opportunities", href: opportunitiesHref(ws) }]}
        title={
          <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{opportunity.title}</span>
            <OpportunityStatusBadge status={opportunity.status} size="md" />
          </span>
        }
        description={opportunity.thesis}
        meta={<span className="text-secondary">{opportunity.status_rationale}</span>}
      />
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
        <ItemIntegrityIndicator value={opportunity.integrity} />
        <BriefMeta brief={brief} />
      </div>
      <div className="mt-6 flex flex-col gap-4">
        <DriftCallout brief={brief} />
        {!showNumbers && (
          <Callout tone="warn" title="Could not be re-verified">
            The cited evidence for this opportunity no longer matches the current sources, so its figures are hidden.
          </Callout>
        )}
      </div>

      <div className="mt-8">
        <Section title="Evidence" description="Cited passages for and against the hypothesis. Open a passage to read it in context.">
          <div className="grid gap-6 lg:grid-cols-2">
            <EvidenceColumn
              title="Supporting evidence"
              description="Passages consistent with the hypothesis."
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
        </Section>

        {metrics.length > 0 && (
          <Section
            title="Quantitative signals"
            description="Figures recomputed from the structured datasets each time this page loads."
          >
            {showNumbers ? (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {metrics.map((m) => (
                  <QuantPanel key={m.key} metric={m} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">Figures are hidden until this opportunity can be re-verified.</p>
            )}
          </Section>
        )}

        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <Card as="div">
            <section aria-labelledby="gaps-heading">
            <h2 id="gaps-heading" className="text-md font-semibold text-primary">
              Evidence gaps
            </h2>
            {opportunity.gaps.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No gaps recorded.</p>
            ) : (
              <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-base text-secondary">
                {opportunity.gaps.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            )}
            </section>
          </Card>
          <Card as="div">
            <section aria-labelledby="next-heading">
            <h2 id="next-heading" className="text-md font-semibold text-primary">
              Next research step
            </h2>
            <p className="mt-2 text-base text-primary">{opportunity.next_step}</p>
            </section>
          </Card>
        </div>

        {opportunity.caveats.length > 0 && (
          <Section title="Caveats" description="Limits to keep in mind before acting on this opportunity.">
            <ul className="flex list-disc flex-col gap-1.5 pl-5 text-base text-secondary">
              {opportunity.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </Section>
        )}
      </div>
    </>
  );
}

function DetailSkeleton() {
  return (
    <LoadingRegion label="Loading opportunity">
      <div className="flex flex-col gap-6">
        <Skeleton lines={3} className="max-w-reading" />
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton height="16rem" />
          <Skeleton height="16rem" />
        </div>
      </div>
    </LoadingRegion>
  );
}

export function OpportunityDetail({ ws, opportunityId }: { ws: string; opportunityId: string }) {
  const brief = useInsights(ws);
  const analyses = useAnalyses(ws);
  const onOpen = useOpenEvidence() ?? undefined;
  useDocumentTitle(brief.data?.opportunities.find((o) => o.id === opportunityId)?.title, "Growth Opportunities");
  const back = (
    <LinkButton href={opportunitiesHref(ws)}>Back to Growth Opportunities</LinkButton>
  );

  if (brief.isPending) {
    return (
      <PageContainer>
        <DetailSkeleton />
      </PageContainer>
    );
  }
  if (brief.isError) {
    return (
      <PageContainer>
        <ErrorState
          title="This opportunity could not be loaded"
          description="The brief is temporarily unavailable. Try again in a moment."
          retry={() => void brief.refetch()}
        />
      </PageContainer>
    );
  }
  if (!brief.data.fixture_version) {
    return (
      <PageContainer>
        <NoBriefState ws={ws} subject="Growth opportunities" />
      </PageContainer>
    );
  }
  const opportunity = brief.data.opportunities.find((o) => o.id === opportunityId);
  if (!opportunity) {
    return (
      <PageContainer>
        <EmptyState
          title="Opportunity not found"
          description="This opportunity is not part of the current brief. It may have been renamed or removed."
          action={back}
        />
      </PageContainer>
    );
  }
  return (
    <PageContainer>
      <OpportunityDetailView
        ws={ws}
        brief={brief.data}
        opportunity={opportunity}
        analyses={indexAnalyses(analyses.data?.analyses)}
        onOpen={onOpen}
      />
    </PageContainer>
  );
}
