import { redirect } from "next/navigation";
import { sourcesRedirectTarget } from "@/components/shell/routes";

/** Legacy route: `/sources` → `/evidence`. */
export default async function LegacySourcesPage({ params }: PageProps<"/w/[ws]/sources">) {
  const { ws } = await params;
  redirect(sourcesRedirectTarget(ws));
}
