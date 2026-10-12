"use client";

import { useMemo, useState } from "react";
import { useDatasets } from "@/lib/api/hooks/core";
import { useAnalyses } from "@/lib/api/hooks/insights";
import { describeError } from "@/lib/api/errors";
import { errorMessage } from "@/lib/labels";
import { formatDateTime, formatNumber } from "@/lib/format";
import { FilterBar, FilterSelect } from "../ui/filter-bar";
import { PageContainer } from "../ui/page-container";
import { PageHeader } from "../ui/page-header";
import { Section } from "../ui/section";
import { EmptyState, ErrorState, LoadingRegion, Skeleton } from "../ui/states";
import { AnalysisCard } from "./analysis-card";
import { categoryLabel } from "./analysis-format";
import { DatasetsList } from "./datasets-list";
import { SavedResults } from "./saved-results";

function CardsSkeleton() {
  return (
    <LoadingRegion label="Loading analyses">
      <ul className="grid gap-3 md:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <li key={i} className="rounded-lg border border-border bg-surface p-4">
            <Skeleton lines={4} />
          </li>
        ))}
      </ul>
    </LoadingRegion>
  );
}

export function AnalyticsView({ ws }: { ws: string }) {
  const analyses = useAnalyses(ws);
  const datasets = useDatasets(ws);
  const [category, setCategory] = useState("");
  const [dataset, setDataset] = useState("");

  const all = useMemo(() => analyses.data?.analyses ?? [], [analyses.data]);
  const categories = useMemo(() => [...new Set(all.map((a) => a.category))].sort(), [all]);
  const datasetOptions = useMemo(
    () => [...new Map(all.map((a) => [a.provenance.dataset, a.provenance.source_title])).entries()],
    [all],
  );
  const shown = all.filter((a) => (!category || a.category === category) && (!dataset || a.provenance.dataset === dataset));
  const datasetList = useMemo(() => datasets.data?.datasets ?? [], [datasets.data]);
  const datasetLabel = (id: string, title: string): string => {
    const table = datasetList.find((d) => d.dataset === id)?.table;
    return table && table !== title ? `${title} · ${table}` : title;
  };

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Analytics"
        description="Figures computed directly from the workspace's structured datasets, each with its filters, base and source table."
        meta={
          analyses.data?.fixture_version ? (
            <span>
              {formatNumber(all.length)} named analyses · recomputed {formatDateTime(analyses.data.computed_at)}
            </span>
          ) : undefined
        }
      />

      <div className="mt-6 flex flex-col">
        <Section
          title="Named analyses"
          description="Curated questions recomputed from the source data on every visit. A figure is shown only when it still matches what was reviewed."
        >
          {analyses.isPending ? (
            <CardsSkeleton />
          ) : analyses.isError ? (
            <ErrorState
              title="Analyses could not be loaded"
              description={errorMessage(describeError(analyses.error).code).label}
              retry={() => void analyses.refetch()}
            />
          ) : all.length === 0 ? (
            <EmptyState title="No named analyses for this workspace" description="Curated analyses have not been set up here yet. Saved research results and datasets are listed below." />
          ) : (
            <div className="flex flex-col gap-4">
              <FilterBar onReset={category || dataset ? () => { setCategory(""); setDataset(""); } : undefined}>
                <FilterSelect
                  id="analysis-category"
                  label="Category"
                  value={category}
                  onChange={setCategory}
                  options={[{ value: "", label: "All categories" }, ...categories.map((c) => ({ value: c, label: categoryLabel(c) }))]}
                />
                <FilterSelect
                  id="analysis-dataset"
                  label="Dataset"
                  value={dataset}
                  onChange={setDataset}
                  options={[{ value: "", label: "All datasets" }, ...datasetOptions.map(([value, title]) => ({ value, label: datasetLabel(value, title) }))]}
                />
              </FilterBar>
              {shown.length === 0 ? (
                <EmptyState title="No analyses match these filters" />
              ) : (
                <ul aria-label="Named analyses" className="grid gap-3 md:grid-cols-2">
                  {shown.map((a) => (
                    <AnalysisCard key={a.id} ws={ws} analysis={a} />
                  ))}
                </ul>
              )}
            </div>
          )}
        </Section>

        <SavedResults ws={ws} datasets={datasetList} />

        <Section title="Datasets" description="Structured tables MarketSignal can compute from. Expand a dataset to see its columns.">
          {datasets.isPending ? (
            <LoadingRegion label="Loading datasets" lines={5} />
          ) : datasets.isError ? (
            <ErrorState title="Datasets could not be loaded" description="Try again in a moment." retry={() => void datasets.refetch()} />
          ) : datasetList.length === 0 ? (
            <EmptyState title="No datasets yet" description="Spreadsheets and data tables added to the Evidence Library appear here once processed." />
          ) : (
            <DatasetsList ws={ws} datasets={datasetList} truncated={datasets.data.truncated} />
          )}
        </Section>
      </div>
    </PageContainer>
  );
}
