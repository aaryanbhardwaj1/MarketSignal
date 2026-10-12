import { LinkButton } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/states";

const TITLE = "Page not found";

export default function WorkspaceNotFound() {
  return (
    <PageContainer>
      <title>{`${TITLE} · MarketSignal`}</title>
      <PageHeader title={TITLE} description="This page does not exist in this workspace, or the link is out of date." />
      <div className="mt-6">
        <EmptyState
          title="Nothing to show here"
          description="Use the navigation to choose another page."
          action={<LinkButton href="/">Go to the overview</LinkButton>}
        />
      </div>
    </PageContainer>
  );
}
