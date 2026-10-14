import type { Metadata } from "next";
import { OverviewPage } from "@/components/overview/overview-page";

export const metadata: Metadata = { title: "Insights" };

// Temporary: renders the previous overview until the Insights page lands.
export default async function Page({ params }: PageProps<"/w/[ws]/insights">) {
  const { ws } = await params;
  return <OverviewPage ws={ws} />;
}
