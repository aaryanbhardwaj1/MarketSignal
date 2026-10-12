import { redirect } from "next/navigation";
import { searchRedirectTarget } from "@/components/shell/routes";

/** Legacy route: `/search?q=` → `/evidence?q=`. */
export default async function LegacySearchPage({ params, searchParams }: PageProps<"/w/[ws]/search">) {
  const { ws } = await params;
  const { q } = await searchParams;
  redirect(searchRedirectTarget(ws, q));
}
