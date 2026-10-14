"use client";

import { useMemo } from "react";
import { BarChart3, RefreshCw } from "lucide-react";
import type { Analysis } from "@/lib/api/contracts";
import { useDatasets } from "@/lib/api/hooks/core";
import { useAnalyses } from "@/lib/api/hooks/insights";
import { formatDateTime, formatNumber } from "@/lib/format";
import { groupByArea } from "@/lib/views/analytics";
import { PageContainer } from "../ui/page-container";
import { PageHeader } from "../ui/page-header";
import { SectionHeader } from "../ui/section-header";
import { CardGridSkeleton, EmptyState, ErrorState, LoadingRegion } from "../ui/states";
import { AnalysisCard } from "./analysis-card";
import { DatasetsList } from "./datasets-list";
import { SavedResults } from "./saved-results";
import { SecondarySection } from "./secondary-section";

export const ANALYTICS_DESCRIPTION =
  "Explore quantitative signals across customer, market and business data — computed directly from structured datasets.";
export const TRUST_LINE = "Every figure is recomputed from the source data on each visit. No model is involved.";

/** Analyses grouped by business area, two tiles per row on wide screens. Presentational. */
export function AnalysisAreas({ ws, analyses }: { ws: string; analyses: readonly Analysis[] }) {
  const groups = groupByArea(analyses);
  return (
    <div className="flex flex-col gap-10">
      {groups.map((group) => {
        const headingId = `area-${group.area.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
        return (
          <section key={group.area} aria-labelledby={headingId} className="flex flex-col gap-4">
            <SectionHeader
              id={headingId}
              title={group.area}
              description={`${formatNumber(group.analyses.length)} ${group.analyses.length === 1 ? "analysis" : "analyses"}`}
            />
            <ul aria-label={group.area} className="ms-stagger grid gap-4 lg:grid-cols-2">
              {group.analyses.map((a) => (
                <AnalysisCard key={a.id} ws={ws} analysis={a} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

/** "What does the data show?": named analyses by business area, then saved results and datasets. */
export function AnalyticsView({ ws }: { ws: string }) {
  const analyses = useAnalyses(ws);
  const datasets = useDatasets(ws);
  const all = useMemo(() => analyses.data?.analyses ?? [], [analyses.data]);
  const datasetList = useMemo(() => datasets.data?.datasets ?? [], [datasets.data]);

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Analytics"
        description={ANALYTICS_DESCRIPTION}
        meta={
          <span className="inline-flex items-center gap-1.5 text-sm text-muted">
            <RefreshCw aria-hidden className="size-3.5" />
            <span>
              {TRUST_LINE}
              {analyses.data?.computed_at && ` Last recomputed ${formatDateTime(analyses.data.computed_at)}.`}
            </span>
          </span>
        }
      />

      <div className="ms-page-enter mt-8 flex flex-col gap-12">
        {analyses.isPending ? (
          <CardGridSkeleton label="Loading analyses" count={4} lines={5} columns="lg:grid-cols-2" gap="sm" />
        ) : analyses.isError ? (
          <ErrorState title="Analyses could not be loaded" error={analyses.error} retry={() => void analyses.refetch()} />
        ) : all.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            title="No analyses for this workspace yet"
            description="Explore quantitative signals across customer, market and business data. Curated analyses appear here once they are set up; datasets and saved research results are listed below."
          />
        ) : (
          <AnalysisAreas ws={ws} analyses={all} />
        )}

        <div className="flex flex-col gap-3">
          <SavedResults ws={ws} datasets={datasetList} />
          <SecondarySection
            id="datasets"
            title="Datasets"
            description="Structured tables these figures are computed from. Expand a dataset to see its columns."
          >
            {datasets.isPending ? (
              <LoadingRegion label="Loading datasets" lines={5} />
            ) : datasets.isError ? (
              <ErrorState title="Datasets could not be loaded" description="Try again in a moment." error={datasets.error} retry={() => void datasets.refetch()} />
            ) : datasetList.length === 0 ? (
              <EmptyState title="No datasets yet" description="Spreadsheets and data tables added to the Evidence library appear here once processed." />
            ) : (
              <DatasetsList ws={ws} datasets={datasetList} truncated={datasets.data.truncated} />
            )}
          </SecondarySection>
        </div>
      </div>
    </PageContainer>
  );
}
