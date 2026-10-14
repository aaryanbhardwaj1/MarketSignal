"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { useEvalCatalog } from "@/lib/api/hooks/evaluation";
import { EVAL_TABS, parseEvalTab, type EvalSplit } from "@/lib/eval-view";
import { AnalyticsTab } from "./analytics-tab";
import { CatalogProvider } from "./catalog-context";
import { CatalogLoading, CatalogProblem } from "./catalog-states";
import { ConfigStrip, DASHBOARD_SENTENCE } from "./dashboard/config-strip";
import { FailuresTab } from "./failures-tab";
import { GroundedTab } from "./grounded-tab";
import { OverviewTab } from "./overview-tab";
import { ProvenanceTab } from "./provenance-tab";
import { RagasPanel } from "./ragas/ragas-panel";
import { ResearchTab } from "./research-tab";
import { RetrievalTab } from "./retrieval-tab";

const PREFIX = "eval";

/** RAG Evaluation (Developer Tools): every figure is read from the precomputed evaluation catalog. */
export function EvaluationView({ ws }: { ws: string }) {
  const catalog = useEvalCatalog();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = parseEvalTab(params.get("tab"));
  const split = params.get("split");
  const data = catalog.data;

  const setSplit = (next: EvalSplit) => {
    const q = new URLSearchParams(params.toString());
    q.set("split", next);
    router.replace(`${pathname}?${q.toString()}`, { scroll: false });
  };

  return (
    <PageContainer width="wide">
      <PageHeader title="RAG Evaluation" description={DASHBOARD_SENTENCE} />
      <div className="mt-6">
        {catalog.isPending ? (
          <CatalogLoading />
        ) : catalog.isError || !data ? (
          <CatalogProblem error={catalog.error} retry={() => void catalog.refetch()} />
        ) : (
          <CatalogProvider catalog={data}>
            <ConfigStrip catalog={data} />
            <div className="mt-6">
              <Tabs param="tab" label="Evaluation sections" idPrefix={PREFIX} tabs={[...EVAL_TABS]} value={tab} />
            </div>
            <TabPanel idPrefix={PREFIX} id={tab}>
              {tab === "overview" && <OverviewTab catalog={data} ws={ws} />}
              {tab === "retrieval" && <RetrievalTab catalog={data} split={split} onSplitChange={setSplit} />}
              {tab === "grounded" && <GroundedTab catalog={data} />}
              {tab === "research" && <ResearchTab catalog={data} split={split} onSplitChange={setSplit} />}
              {tab === "ragas" && <RagasPanel catalog={data} ws={ws} />}
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
