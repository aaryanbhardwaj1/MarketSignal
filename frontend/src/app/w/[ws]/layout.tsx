import { WorkspaceSubnav } from "@/components/layout/workspace-subnav";

export default async function WorkspaceLayout({ children, params }: LayoutProps<"/w/[ws]">) {
  const { ws } = await params;
  const code = ws;
  return (
    <>
      <WorkspaceSubnav ws={code} />
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-8 sm:px-6">
        {children}
      </main>
    </>
  );
}
