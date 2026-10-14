import type { Metadata } from "next";
import { InsightsPage } from "@/components/insights/insights-page";

export const metadata: Metadata = { title: "Insights" };

export default async function Page({ params }: PageProps<"/w/[ws]/insights">) {
  const { ws } = await params;
  return <InsightsPage ws={ws} />;
}
