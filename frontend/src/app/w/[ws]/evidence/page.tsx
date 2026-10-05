import { EvidenceView } from "@/components/evidence/evidence-view";
import { firstParam } from "@/lib/search-params";

export default async function EvidencePage({
  params,
  searchParams,
}: PageProps<"/w/[ws]/evidence">) {
  const { ws } = await params;
  const query = await searchParams;
  const handle = firstParam(query.h)?.trim() ?? "";
  return <EvidenceView ws={ws} handle={handle} child={firstParam(query.child)} />;
}
