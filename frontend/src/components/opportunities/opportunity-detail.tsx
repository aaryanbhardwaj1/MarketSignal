"use client";

import { Presentation } from "lucide-react";
import { EvidenceBalance } from "@/components/charts";
import { LinkButton } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ClaimTag } from "@/components/ui/claim-tag";
import { DevDetails } from "@/components/ui/disclosure";
import { Divider } from "@/components/ui/divider";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { EVIDENCE_STATUS_LABEL, StatusPill } from "@/components/ui/status-pill";
import { EmptyState, ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import type { EvidenceRef, InsightsBrief, Opportunity } from "@/lib/api/contracts";
import { useAnalyses, useInsights } from "@/lib/api/hooks/insights";
import { evidenceBalance, indexAnalyses, numbersAllowed, type AnalysisIndex } from "@/lib/insights-view";
import { opportunitiesHref } from "@/lib/routes";
import { useDocumentTitle } from "@/lib/use-document-title";
import { gapLabel, opportunityDeckHref, relatedLinks, sourceMix } from "@/lib/views/opportunities";
import { BriefMeta, DriftCallout, ItemIntegrityIndicator, NoBriefState, useOpenEvidence } from "./brief-parts";
import { DetailSection, EvidenceColumns, GapList, NextInvestigation, QuantSignals, RelatedSection, RiskList } from "./detail-sections";
import { FieldLabel, GapCount, SourceMix } from "./opportunity-parts";

/** Strategic thesis and why it matters, each with the kind of claim it is. */
function ThesisBlock({ opportunity }: { opportunity: Opportunity }) {
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <DetailSection
        id="thesis"
        title={
          <span className="inline-flex items-center gap-2">
            Strategic thesis
            {opportunity.thesis_claim_type && <ClaimTag type={opportunity.thesis_claim_type} size="sm" explain />}
          </span>
        }
      >
        <p className="max-w-reading text-lg text-primary">{opportunity.thesis}</p>
      </DetailSection>
      {opportunity.why_it_matters && (
        <DetailSection
          id="why"
          title={
            <span className="inline-flex items-center gap-2">
              Why it matters <ClaimTag type={opportunity.why_it_matters.claim_type} size="sm" explain />
            </span>
          }
        >
          <p className="max-w-reading text-base text-secondary">{opportunity.why_it_matters.text}</p>
        </DetailSection>
      )}
    </div>
  );
}

/** Visual evidence summary: the support/contradiction balance, why the status, open gaps and source mix. */
function EvidenceSummary({ opportunity }: { opportunity: Opportunity }) {
  const balance = evidenceBalance(opportunity);
  return (
    <aside aria-label="Evidence summary" className="flex flex-col gap-4 rounded-lg bg-sunken/60 p-4">
      <EvidenceBalance supporting={balance.supporting} contradicting={balance.contradicting} />
      <div>
        <FieldLabel>{`Why ${EVIDENCE_STATUS_LABEL[opportunity.status].toLowerCase()}`}</FieldLabel>
        <p className="mt-1 text-sm text-primary">{opportunity.status_rationale}</p>
      </div>
      <div className="flex flex-wrap gap-x-8 gap-y-3">
        <div>
          <FieldLabel>Open questions</FieldLabel>
          <div className="mt-1">
            <GapCount count={balance.gaps} label={gapLabel(balance.gaps)} />
          </div>
        </div>
        <div>
          <FieldLabel>Sources</FieldLabel>
          <div className="mt-1.5">
            <SourceMix mix={sourceMix(opportunity)} />
          </div>
        </div>
      </div>
    </aside>
  );
}

function IntegrityCallouts({ brief, opportunity }: { brief: InsightsBrief; opportunity: Opportunity }) {
  return (
    <>
      <DriftCallout brief={brief} />
      {opportunity.integrity === "unverified" && (
        <Callout tone="warn" title="Could not be re-verified">
          The cited evidence for this opportunity no longer matches the current sources, so its figures are withheld.
          The passages below show what changed.
        </Callout>
      )}
      {opportunity.integrity === "partial" && (
        <Callout tone="warn" title="Some evidence changed">
          Some cited passages changed or are no longer available since this brief was prepared. They are marked below;
          review them before relying on this opportunity.
        </Callout>
      )}
    </>
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
  const showNumbers = numbersAllowed(opportunity.integrity);
  const related = relatedLinks(ws, opportunity, brief.signals, analyses);
  const handles = [...opportunity.supporting, ...opportunity.contradicting, ...opportunity.risks.flatMap((r) => r.evidence)].map(
    (r) => r.handle,
  );
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Growth Opportunities", href: opportunitiesHref(ws) }]}
        title={opportunity.title}
        meta={
          <>
            <StatusPill status={opportunity.status} />
            <ItemIntegrityIndicator value={opportunity.integrity} />
            <BriefMeta brief={brief} />
          </>
        }
        actions={
          <LinkButton
            href={opportunityDeckHref(ws, opportunity)}
            variant="primary"
            iconLeft={<Presentation aria-hidden size={16} strokeWidth={1.75} />}
          >
            Create presentation
          </LinkButton>
        }
      />

      <div className="mt-6 flex flex-col gap-10">
        <div className="flex flex-col gap-3 empty:hidden">
          <IntegrityCallouts brief={brief} opportunity={opportunity} />
        </div>

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <ThesisBlock opportunity={opportunity} />
          <EvidenceSummary opportunity={opportunity} />
        </div>

        <Divider />
        <EvidenceColumns opportunity={opportunity} onOpen={onOpen} />
        <QuantSignals opportunity={opportunity} analyses={analyses} showNumbers={showNumbers} />
        <RiskList risks={opportunity.risks} onOpen={onOpen} />

        <div className="grid gap-8 lg:grid-cols-2">
          <GapList gaps={opportunity.gaps} />
          <NextInvestigation ws={ws} opportunity={opportunity} />
        </div>

        <RelatedSection insights={related.insights} analyses={related.analyses} />

        {opportunity.caveats.length > 0 && (
          <DetailSection id="caveats" title="Caveats" description="Limits to keep in mind before acting on this opportunity.">
            <ul className="flex list-disc flex-col gap-1.5 pl-5 text-base text-secondary">
              {opportunity.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </DetailSection>
        )}

        <DevDetails data={{ opportunity_id: opportunity.id, fixture_version: brief.fixture_version, evidence_handles: handles }} />
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
    <PageContainer className="ms-page-enter">
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
