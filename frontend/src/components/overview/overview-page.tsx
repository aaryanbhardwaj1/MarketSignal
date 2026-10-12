"use client";

import { DriftCallout, NoBriefState, useOpenEvidence } from "@/components/opportunities/brief-parts";
import { LinkButton } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { CardGridSkeleton, ErrorState } from "@/components/ui/states";
import type { InsightsBrief, WorkspaceOverview } from "@/lib/api/contracts";
import { useWorkspaceOverview } from "@/lib/api/hooks/core";
import { useAnalyses, useInsights } from "@/lib/api/hooks/insights";
import { formatDate, formatDateTime } from "@/lib/format";
import { indexAnalyses, splitWorkspaceName, type AnalysisIndex } from "@/lib/insights-view";
import { OpportunityRows } from "./opportunity-rows";
import { RecentActivity } from "./recent-activity";
import { SignalCard } from "./signal-card";
import { WorkspaceSummary } from "./workspace-summary";
import { askHref, opportunitiesHref } from "@/lib/routes";

function Header({ ws, overview }: { ws: string; overview: WorkspaceOverview | undefined }) {
  const name = overview ? splitWorkspaceName(overview.name) : null;
  const asOf = overview?.last_ready_at ? formatDate(overview.last_ready_at) : null;
  return (
    <PageHeader
      title={name?.client ?? "Overview"}
      description={name?.engagement ?? overview?.description ?? undefined}
      meta={asOf ? <span>Evidence as of {asOf}</span> : undefined}
      actions={<LinkButton href={askHref(ws)}>Ask MarketSignal</LinkButton>}
    />
  );
}

function SummarySection({ ws }: { ws: string }) {
  const overview = useWorkspaceOverview(ws);
  return (
    <Section title="Workspace summary" description="What this workspace holds today.">
      {overview.isPending ? (
        <CardGridSkeleton label="Loading workspace summary" count={5} columns="sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5" />
      ) : overview.isError ? (
        <ErrorState
          title="Workspace summary could not be loaded"
          description="The workspace is temporarily unavailable. Try again in a moment."
          retry={() => void overview.refetch()}
        />
      ) : (
        <WorkspaceSummary ws={ws} overview={overview.data} />
      )}
    </Section>
  );
}

function BriefSections({ ws, brief, analyses }: { ws: string; brief: InsightsBrief; analyses: AnalysisIndex }) {
  const onOpen = useOpenEvidence() ?? undefined;
  return (
    <>
      <Section
        title="Key signals"
        description={`Curated analyst brief · re-verified against current evidence on ${formatDateTime(brief.computed_at)}`}
      >
        <div className="flex flex-col gap-4">
          <DriftCallout brief={brief} />
          <div className="grid gap-4 md:grid-cols-2 min-[1440px]:grid-cols-3">
            {brief.signals.map((s) => (
              <SignalCard key={s.id} signal={s} analyses={analyses} onOpen={onOpen} />
            ))}
          </div>
        </div>
      </Section>
      {brief.opportunities.length > 0 && (
        <Section
          title="Growth opportunities"
          description="Hypotheses weighed against the evidence for and against them. Not scored or ranked."
          actions={
            <LinkButton href={opportunitiesHref(ws)} variant="ghost">
              View all opportunities
            </LinkButton>
          }
        >
          <OpportunityRows ws={ws} opportunities={brief.opportunities} />
        </Section>
      )}
    </>
  );
}

function Brief({ ws }: { ws: string }) {
  const brief = useInsights(ws);
  const analyses = useAnalyses(ws);
  if (brief.isPending) {
    return (
      <Section title="Key signals">
        <CardGridSkeleton label="Loading key signals" count={6} columns="md:grid-cols-2 min-[1440px]:grid-cols-3" />
      </Section>
    );
  }
  if (brief.isError) {
    return (
      <Section title="Key signals">
        <ErrorState
          title="The analyst brief could not be loaded"
          description="Key signals and growth opportunities are temporarily unavailable. Try again in a moment."
          retry={() => void brief.refetch()}
        />
      </Section>
    );
  }
  if (!brief.data.fixture_version) {
    return (
      <Section title="Key signals and growth opportunities">
        <NoBriefState ws={ws} subject="Key signals and growth opportunities" />
      </Section>
    );
  }
  return <BriefSections ws={ws} brief={brief.data} analyses={indexAnalyses(analyses.data?.analyses)} />;
}

/** Overview: what MarketSignal knows about this client, and what to look at next. */
export function OverviewPage({ ws }: { ws: string }) {
  const overview = useWorkspaceOverview(ws);
  return (
    <PageContainer>
      <Header ws={ws} overview={overview.data} />
      <div className="mt-6">
        <SummarySection ws={ws} />
        <Brief ws={ws} />
        <Section title="Recent activity" description="Saved research and the results computed while answering it.">
          <RecentActivity ws={ws} />
        </Section>
      </div>
    </PageContainer>
  );
}
