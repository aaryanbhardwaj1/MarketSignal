import { LinkButton } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-container";
import { EmptyState } from "@/components/ui/states";

export default function WorkspaceNotFound() {
  return (
    <PageContainer>
      <EmptyState
        title="Page not found"
        description="This page does not exist in this workspace, or the link is out of date."
        action={<LinkButton href="/">Go to the overview</LinkButton>}
      />
    </PageContainer>
  );
}
