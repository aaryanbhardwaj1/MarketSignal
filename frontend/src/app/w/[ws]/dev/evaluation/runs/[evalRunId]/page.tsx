import { Suspense } from "react";
import { CatalogLoading } from "@/components/evaluation/catalog-states";
import { RunView } from "@/components/evaluation/run-view";

export default async function EvaluationRunPage({ params }: PageProps<"/w/[ws]/dev/evaluation/runs/[evalRunId]">) {
  const { ws, evalRunId } = await params;
  return (
    <Suspense fallback={<CatalogLoading />}>
      <RunView ws={ws} runId={evalRunId} />
    </Suspense>
  );
}
