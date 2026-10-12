"use client";

import { PageContainer } from "@/components/ui/page-container";
import { ErrorState } from "@/components/ui/states";

export default function WorkspaceError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <PageContainer>
      <ErrorState
        title="This page could not be shown"
        description="Something went wrong while loading this page. Try again, or choose another page from the navigation."
        retry={retry}
        devDetail={error.digest ? `digest ${error.digest}` : undefined}
      />
    </PageContainer>
  );
}
