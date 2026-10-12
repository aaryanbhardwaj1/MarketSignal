import type { Metadata } from "next";
import { AnalysisPage } from "@/components/analytics/analysis-page";

/** Static section title; detail pages refine it once their record loads. */
export const metadata: Metadata = { title: "Analytics" };

export default async function AnalysisDetailPage({ params }: PageProps<"/w/[ws]/analytics/[analysisId]">) {
  const { ws, analysisId } = await params;
  return <AnalysisPage ws={ws} analysisId={analysisId} />;
}
