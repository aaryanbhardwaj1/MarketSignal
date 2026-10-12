"use client";

import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState } from "@/components/ui/states";

const TITLE = "This page could not be shown";

export default function WorkspaceError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <PageContainer>
      <title>{`${TITLE} · MarketSignal`}</title>
      <PageHeader title={TITLE} description="Something went wrong while loading this page." />
      <div className="mt-6">
        <ErrorState
          title="Loading failed"
          description="Try again, or choose another page from the navigation."
          retry={retry}
          devDetail={error.digest ? `digest ${error.digest}` : undefined}
        />
      </div>
    </PageContainer>
  );
}
