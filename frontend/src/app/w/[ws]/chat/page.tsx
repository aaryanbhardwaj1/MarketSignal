import { redirect } from "next/navigation";
import { chatRedirectTarget } from "@/components/shell/routes";

/** Legacy route: `/chat?c=X` → `/ask/X`. */
export default async function LegacyChatPage({ params, searchParams }: PageProps<"/w/[ws]/chat">) {
  const { ws } = await params;
  const { c } = await searchParams;
  redirect(chatRedirectTarget(ws, c));
}
