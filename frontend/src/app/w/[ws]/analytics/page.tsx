import { AnalyticsView } from "@/components/analytics/analytics-view";

export default async function AnalyticsPage({ params }: PageProps<"/w/[ws]/analytics">) {
  const { ws } = await params;
  return <AnalyticsView ws={ws} />;
}
