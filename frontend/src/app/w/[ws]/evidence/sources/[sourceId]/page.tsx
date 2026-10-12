import type { Metadata } from "next";
import { SourcePage } from "@/components/library/source-page";

/** Static section title; detail pages refine it once their record loads. */
export const metadata: Metadata = { title: "Evidence Library" };

export default async function SourceDetailPage({ params }: PageProps<"/w/[ws]/evidence/sources/[sourceId]">) {
  const { ws, sourceId } = await params;
  return <SourcePage ws={ws} sourceId={sourceId} />;
}
