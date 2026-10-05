import { WorkspaceDashboard } from "@/components/dashboard/workspace-dashboard";

export default async function WorkspacePage({ params }: PageProps<"/w/[ws]">) {
  const { ws } = await params;
  return <WorkspaceDashboard ws={ws} />;
}
