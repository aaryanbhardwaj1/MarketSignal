"use client";

import { useMemo } from "react";
import { MessageSquarePlus, Presentation } from "lucide-react";
import type { Analysis } from "@/lib/api/contracts";
import { isNotFoundError } from "@/lib/api/errors";
import { useAnalysis, useInsights } from "@/lib/api/hooks/insights";
import { analyticsHref } from "@/lib/routes";
import { useDocumentTitle } from "@/lib/use-document-title";
import { analysisDeckHref, followUpHref } from "@/lib/views/analytics";
import { Badge } from "../ui/badge";
import { LinkButton } from "../ui/button";
import { PageContainer } from "../ui/page-container";
import { PageHeader } from "../ui/page-header";
import { EmptyState, ErrorState, LoadingRegion } from "../ui/states";
import { AnalysisSummary } from "./analysis-card";
import { AnalysisDetailView, type RelatedTitles } from "./analysis-detail";
import { analysisState } from "./analysis-format";

/** Header actions: add this analysis (and the insights using it) to a deck, or ask a follow-up. */
export function AnalysisActions({ ws, analysis }: { ws: string; analysis: Analysis }) {
  return (
    <>
      <LinkButton href={followUpHref(ws, analysis.question)} variant="secondary" iconLeft={<MessageSquarePlus aria-hidden className="size-4" />}>
        Ask a follow-up
      </LinkButton>
      <LinkButton
        href={analysisDeckHref(ws, { analyses: [analysis.id], signals: analysis.used_by.signals })}
        variant="primary"
        iconLeft={<Presentation aria-hidden className="size-4" />}
      >
        Add to presentation
      </LinkButton>
    </>
  );
}

/** Route container for one analysis: loading, not found and error states around the detail view. */
export function AnalysisPage({ ws, analysisId }: { ws: string; analysisId: string }) {
  const query = useAnalysis(ws, analysisId);
  const brief = useInsights(ws);
  useDocumentTitle(query.data?.title, "Analytics");
  const crumbs = [{ label: "Analytics", href: analyticsHref(ws) }];
  const titles = useMemo<RelatedTitles>(
    () => ({
      signals: new Map((brief.data?.signals ?? []).map((s) => [s.id, s.title])),
      opportunities: new Map((brief.data?.opportunities ?? []).map((o) => [o.id, o.title])),
    }),
    [brief.data],
  );

  if (query.isPending) {
    return (
      <PageContainer width="content">
        <PageHeader title="Analysis" breadcrumb={crumbs} />
        <div className="mt-6">
          <LoadingRegion label="Loading analysis" lines={8} />
        </div>
      </PageContainer>
    );
  }

  if (query.isError) {
    const notFound = isNotFoundError(query.error);
    return (
      <PageContainer width="content">
        <PageHeader title={notFound ? "Analysis not found" : "Analysis"} breadcrumb={crumbs} />
        <div className="mt-6">
          {notFound ? (
            <EmptyState
              title="This analysis does not exist in this workspace"
              description="It may have been renamed or removed from the curated set."
              action={<LinkButton href={analyticsHref(ws)} variant="secondary">Back to Analytics</LinkButton>}
            />
          ) : (
            <ErrorState title="The analysis could not be loaded" error={query.error} retry={() => void query.refetch()} />
          )}
        </div>
      </PageContainer>
    );
  }

  const analysis = query.data;
  const state = analysisState(analysis);
  return (
    <PageContainer width="content">
      <PageHeader
        breadcrumb={crumbs}
        eyebrow={analysis.business_area ?? undefined}
        title={analysis.title}
        description={<AnalysisSummary analysis={analysis} as="span" />}
        meta={state.kind === "computed" ? undefined : <Badge tone={state.tone}>{state.label}</Badge>}
        actions={<AnalysisActions ws={ws} analysis={analysis} />}
        divider={false}
      />
      <div className="ms-page-enter mt-2">
        <AnalysisDetailView ws={ws} analysis={analysis} titles={titles} />
      </div>
    </PageContainer>
  );
}
