import { redirect } from "next/navigation";
import { workspaceRootTarget } from "@/components/shell/routes";

export default async function WorkspacePage({ params }: PageProps<"/w/[ws]">) {
  const { ws } = await params;
  redirect(workspaceRootTarget(ws));
}
