import { SourceDetail } from "@/components/sources/source-detail";

export default async function SourceDetailPage({
  params,
}: PageProps<"/w/[ws]/sources/[sourceId]">) {
  const { ws, sourceId } = await params;
  return <SourceDetail ws={ws} sourceId={sourceId} />;
}
