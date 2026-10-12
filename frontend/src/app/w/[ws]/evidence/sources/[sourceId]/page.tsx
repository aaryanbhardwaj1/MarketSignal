import { SourcePage } from "@/components/library/source-page";

export default async function SourceDetailPage({ params }: PageProps<"/w/[ws]/evidence/sources/[sourceId]">) {
  const { ws, sourceId } = await params;
  return <SourcePage ws={ws} sourceId={sourceId} />;
}
