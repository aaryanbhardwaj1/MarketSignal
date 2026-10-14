"use client";

import { Lightbulb } from "lucide-react";
import { staggerStyle } from "@/components/motion/stagger";
import { LinkButton } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { CardGridSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import type { InsightsBrief } from "@/lib/api/contracts";
import { useAnalyses, useInsights } from "@/lib/api/hooks/insights";
import { indexAnalyses, type AnalysisIndex } from "@/lib/insights-view";
import { askHref, evidenceLibraryHref } from "@/lib/routes";
import { orderOpportunities } from "@/lib/views/opportunities";
import { DriftCallout } from "./brief-parts";
import { OpportunityCard } from "./opportunity-card";

export const LIST_DESCRIPTION = "Potential growth directions, with the evidence for and against each.";
export const LIST_NOTE =
  "Curated from the analyst brief and re-verified against current evidence. Statuses are qualitative; there are no scores.";

/** Teaching empty state for a workspace without a curated brief. */
function NoOpportunities({ ws }: { ws: string }) {
  return (
    <EmptyState
      icon={Lightbulb}
      title="No growth opportunities yet"
      description="Evaluate potential growth directions supported, or challenged, by the evidence. They appear here once an analyst has prepared a brief for this workspace."
      action={
        <div className="flex flex-wrap justify-center gap-2">
          <LinkButton href={askHref(ws)}>Ask a research question</LinkButton>
          <LinkButton href={evidenceLibraryHref(ws)} variant="ghost">
            Open the Evidence Library
          </LinkButton>
        </div>
      }
    />
  );
}

/** The ordered list body, separated from data loading so it renders from fixtures in tests. */
export function OpportunitiesListView({ ws, brief, analyses }: { ws: string; brief: InsightsBrief; analyses: AnalysisIndex }) {
  const opportunities = orderOpportunities(brief.opportunities);
  return (
    <div className="flex flex-col gap-4">
      <DriftCallout brief={brief} />
      <ol aria-label="Growth opportunities" className="ms-stagger divide-y divide-border border-y border-border">
        {opportunities.map((o, i) => (
          <li key={o.id} style={staggerStyle(i)}>
            <OpportunityCard ws={ws} opportunity={o} analyses={analyses} />
          </li>
        ))}
      </ol>
    </div>
  );
}

export function OpportunitiesList({ ws }: { ws: string }) {
  const brief = useInsights(ws);
  const analyses = useAnalyses(ws);

  return (
    <PageContainer className="ms-page-enter">
      <PageHeader
        title="Growth Opportunities"
        description={LIST_DESCRIPTION}
        meta={brief.data?.fixture_version ? <span>{LIST_NOTE}</span> : undefined}
        divider={false}
      />
      <div className="mt-2">
        {brief.isPending ? (
          <CardGridSkeleton label="Loading growth opportunities" count={4} lines={4} columns="lg:grid-cols-1" padding="md" />
        ) : brief.isError ? (
          <ErrorState
            title="Growth opportunities could not be loaded"
            description="The brief is temporarily unavailable. Try again in a moment."
            error={brief.error}
            retry={() => void brief.refetch()}
          />
        ) : !brief.data.fixture_version || brief.data.opportunities.length === 0 ? (
          <NoOpportunities ws={ws} />
        ) : (
          <OpportunitiesListView ws={ws} brief={brief.data} analyses={indexAnalyses(analyses.data?.analyses)} />
        )}
      </div>
    </PageContainer>
  );
}
