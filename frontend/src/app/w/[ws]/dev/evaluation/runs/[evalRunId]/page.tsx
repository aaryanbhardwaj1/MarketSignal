import type { Metadata } from "next";
import { Suspense } from "react";
import { CatalogLoading } from "@/components/evaluation/catalog-states";
import { RunView } from "@/components/evaluation/run-view";

export async function generateMetadata({ params }: PageProps<"/w/[ws]/dev/evaluation/runs/[evalRunId]">): Promise<Metadata> {
  const { evalRunId } = await params;
  return { title: `Evaluation run ${evalRunId} · RAG Evaluation` };
}

export default async function EvaluationRunPage({ params }: PageProps<"/w/[ws]/dev/evaluation/runs/[evalRunId]">) {
  const { ws, evalRunId } = await params;
  return (
    <Suspense fallback={<CatalogLoading />}>
      <RunView ws={ws} runId={evalRunId} />
    </Suspense>
  );
}
