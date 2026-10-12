import { AnalysisPage } from "@/components/analytics/analysis-page";

export default async function AnalysisDetailPage({ params }: PageProps<"/w/[ws]/analytics/[analysisId]">) {
  const { ws, analysisId } = await params;
  return <AnalysisPage ws={ws} analysisId={analysisId} />;
}
