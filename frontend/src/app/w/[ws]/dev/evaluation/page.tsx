import type { Metadata } from "next";
import { Suspense } from "react";
import { CatalogLoading } from "@/components/evaluation/catalog-states";
import { EvaluationView } from "@/components/evaluation/evaluation-view";

export const metadata: Metadata = { title: "RAG Evaluation" };

export default async function EvaluationPage({ params }: PageProps<"/w/[ws]/dev/evaluation">) {
  const { ws } = await params;
  return (
    <Suspense fallback={<CatalogLoading />}>
      <EvaluationView ws={ws} />
    </Suspense>
  );
}
