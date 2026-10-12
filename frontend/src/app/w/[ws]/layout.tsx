import { EvidenceDrawerProvider } from "@/components/evidence/evidence-drawer-provider";
import { AppShell } from "@/components/shell/app-shell";

export default async function WorkspaceLayout({ children, params }: LayoutProps<"/w/[ws]">) {
  const { ws } = await params;
  return (
    <EvidenceDrawerProvider ws={ws}>
      <AppShell ws={ws}>{children}</AppShell>
    </EvidenceDrawerProvider>
  );
}
