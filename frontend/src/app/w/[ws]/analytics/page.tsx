import type { Metadata } from "next";
import { AnalyticsView } from "@/components/analytics/analytics-view";

export const metadata: Metadata = { title: "Analytics" };

export default async function AnalyticsPage({ params }: PageProps<"/w/[ws]/analytics">) {
  const { ws } = await params;
  return <AnalyticsView ws={ws} />;
}
