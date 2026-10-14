"use client";

import { Lightbulb } from "lucide-react";
import type { ReactNode } from "react";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import { LinkButton } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { CardGridSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import type { EvidenceRef } from "@/lib/api/contracts";
import { useWorkspaceOverview } from "@/lib/api/hooks/core";
import { useAnalyses, useInsights } from "@/lib/api/hooks/insights";
import { drawerTarget, indexAnalyses, splitWorkspaceName } from "@/lib/insights-view";
import { analyticsHref, askHref, evidenceLibraryHref } from "@/lib/routes";
import { InsightsView, insightsDescription } from "./insights-view";

/** Opens a cited passage (highlighted when verified) in the evidence drawer; null without a drawer. */
function useOpenEvidence(): ((ref: EvidenceRef) => void) | undefined {
  const drawer = useOptionalEvidenceDrawer();
  if (!drawer) return undefined;
  return (ref) => {
    const target = drawerTarget(ref);
    if (target) drawer.openEvidence(target);
  };
}

/** Teaching empty state: what this page is for and what still works without a brief. */
export function NoInsights({ ws }: { ws: string }) {
  return (
    <EmptyState
      icon={Lightbulb}
      title="Review evidence-backed patterns and strategic implications."
      description="Insights interpret the evidence: emerging signals, risks, competitor moves, friction to fix and the outlook, each tied to the passages and figures behind it. They appear once an analyst has prepared a brief for this workspace. Meanwhile you can explore the data in Analytics or research a question in Chat."
      action={
        <div className="flex flex-wrap justify-center gap-2">
          <LinkButton href={askHref(ws)}>Ask a research question</LinkButton>
          <LinkButton href={analyticsHref(ws)} variant="ghost">
            Open Analytics
          </LinkButton>
          <LinkButton href={evidenceLibraryHref(ws)} variant="ghost">
            Browse evidence
          </LinkButton>
        </div>
      }
    />
  );
}

/** Insights: what the evidence means, grouped into six categories, with deck selection. */
export function InsightsPage({ ws }: { ws: string }) {
  const overview = useWorkspaceOverview(ws);
  const brief = useInsights(ws);
  const analyses = useAnalyses(ws);
  const onOpen = useOpenEvidence();
  const client = overview.data ? splitWorkspaceName(overview.data.name).client : null;

  const shell = (body: ReactNode) => (
    <PageContainer>
      <PageHeader title="Insights" description={insightsDescription(client)} />
      <div className="mt-6">{body}</div>
    </PageContainer>
  );

  if (brief.isPending) {
    return shell(<CardGridSkeleton label="Loading insights" count={6} columns="md:grid-cols-2" />);
  }
  if (brief.isError) {
    return shell(
      <ErrorState
        title="Insights could not be loaded"
        description="The analyst brief is temporarily unavailable. Analytics and Chat still work. Try again in a moment."
        retry={() => void brief.refetch()}
      />,
    );
  }
  if (!brief.data.fixture_version) return shell(<NoInsights ws={ws} />);

  return (
    <PageContainer className="ms-page-enter">
      <InsightsView
        ws={ws}
        brief={brief.data}
        analyses={indexAnalyses(analyses.data?.analyses)}
        client={client}
        onOpen={onOpen}
      />
    </PageContainer>
  );
}
