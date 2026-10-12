"use client";

import { useAnalysis } from "@/lib/api/hooks/insights";
import { describeError, isApiError } from "@/lib/api/errors";
import { errorMessage } from "@/lib/labels";
import { Badge } from "../ui/badge";
import { LinkButton } from "../ui/button";
import { PageContainer } from "../ui/page-container";
import { PageHeader } from "../ui/page-header";
import { EmptyState, ErrorState, LoadingRegion } from "../ui/states";
import { AnalysisDetailView } from "./analysis-detail";
import { analysisState, categoryLabel, scopeLine } from "./analysis-format";
import { useDocumentTitle } from "../overview/use-document-title";

function analyticsHref(ws: string): string {
  return `/w/${encodeURIComponent(ws)}/analytics`;
}

/** Route container for one named analysis: loading, not found and error states around the detail view. */
export function AnalysisPage({ ws, analysisId }: { ws: string; analysisId: string }) {
  const query = useAnalysis(ws, analysisId);
  useDocumentTitle(query.data?.title, "Analytics");
  const crumbs = [{ label: "Analytics", href: analyticsHref(ws) }];

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
    const notFound = isApiError(query.error) && query.error.status === 404;
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
            <ErrorState
              title="The analysis could not be loaded"
              description={errorMessage(describeError(query.error).code).label}
              retry={() => void query.refetch()}
            />
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
        title={analysis.title}
        description={scopeLine(analysis)}
        meta={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{categoryLabel(analysis.category)}</Badge>
            <Badge tone={state.tone}>{state.label}</Badge>
          </span>
        }
      />
      <div className="mt-2">
        <AnalysisDetailView analysis={analysis} />
      </div>
    </PageContainer>
  );
}
