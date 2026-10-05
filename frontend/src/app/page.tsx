import { Card, PageHeader } from "@/components/ui/card";
import { CreateWorkspaceForm } from "@/components/workspaces/create-workspace-form";
import { WorkspaceList } from "@/components/workspaces/workspace-list";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-8 sm:px-6">
      <PageHeader
        eyebrow="Phase 1 - corpus inspection"
        title="Workspaces"
        description="Each workspace is an isolated client engagement. Every material claim resolves to an exact, immutable evidence handle inside one workspace."
      />
      <div className="grid gap-8 lg:grid-cols-[1fr_22rem]">
        <WorkspaceList />
        <Card title="New workspace">
          <CreateWorkspaceForm />
        </Card>
      </div>
    </main>
  );
}
