"use client";

import { useSearchParams } from "next/navigation";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { useEvalCatalog } from "@/lib/api/hooks/evaluation";
import { EVAL_TABS, type EvalTabId } from "@/lib/eval-view";
import { formatDateTime } from "@/lib/format";
import { AnalyticsTab } from "./analytics-tab";
import { CatalogProvider } from "./catalog-context";
import { CatalogLoading, CatalogProblem } from "./catalog-states";
import { FailuresTab } from "./failures-tab";
import { GroundedTab } from "./grounded-tab";
import { OverviewTab } from "./overview-tab";
import { ProvenanceTab } from "./provenance-tab";
import { ResearchTab } from "./research-tab";
import { RetrievalTab } from "./retrieval-tab";

const PREFIX = "eval";

function activeTab(raw: string | null): EvalTabId {
  return EVAL_TABS.some((t) => t.id === raw) ? (raw as EvalTabId) : "overview";
}

/** RAG Evaluation (Developer Tools): every figure is read from the precomputed evaluation catalog. */
export function EvaluationView({ ws }: { ws: string }) {
  const catalog = useEvalCatalog();
  const tab = activeTab(useSearchParams().get("tab"));
  const data = catalog.data;

  return (
    <PageContainer width="wide">
      <PageHeader
        title="RAG Evaluation"
        description="How retrieval, grounded answers, research mode and analytics were measured against versioned datasets with known expected evidence."
        meta={data ? <span>Catalog built {formatDateTime(data.built_at)}</span> : undefined}
      />
      <div className="mt-6">
        {catalog.isPending ? (
          <CatalogLoading />
        ) : catalog.isError || !data ? (
          <CatalogProblem error={catalog.error} retry={() => void catalog.refetch()} />
        ) : (
          <CatalogProvider catalog={data}>
            <Tabs param="tab" label="Evaluation sections" idPrefix={PREFIX} tabs={[...EVAL_TABS]} value={tab} />
            <TabPanel idPrefix={PREFIX} id={tab}>
              {tab === "overview" && <OverviewTab catalog={data} />}
              {tab === "retrieval" && <RetrievalTab catalog={data} />}
              {tab === "grounded" && <GroundedTab catalog={data} />}
              {tab === "research" && <ResearchTab catalog={data} />}
              {tab === "analytics" && <AnalyticsTab catalog={data} />}
              {tab === "failures" && <FailuresTab catalog={data} ws={ws} />}
              {tab === "provenance" && <ProvenanceTab catalog={data} />}
            </TabPanel>
          </CatalogProvider>
        )}
      </div>
    </PageContainer>
  );
}
