import { SourcesView } from "@/components/sources/sources-view";

export default async function SourcesPage({ params }: PageProps<"/w/[ws]/sources">) {
  const { ws } = await params;
  return <SourcesView ws={ws} />;
}
