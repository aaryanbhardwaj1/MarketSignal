import type { Metadata } from "next";
import { OverviewPage } from "@/components/overview/overview-page";

export const metadata: Metadata = { title: "Overview" };

export default async function Page({ params }: PageProps<"/w/[ws]/overview">) {
  const { ws } = await params;
  return <OverviewPage ws={ws} />;
}
