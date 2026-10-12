import { redirect } from "next/navigation";
import { sourceDetailRedirectTarget } from "@/components/shell/routes";

/** Legacy route: `/sources/[id]` → `/evidence/sources/[id]`. */
export default async function LegacySourceDetailPage({ params }: PageProps<"/w/[ws]/sources/[sourceId]">) {
  const { ws, sourceId } = await params;
  redirect(sourceDetailRedirectTarget(ws, sourceId));
}
