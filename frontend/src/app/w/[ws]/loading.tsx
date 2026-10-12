import { PageContainer } from "@/components/ui/page-container";
import { LoadingRegion, Skeleton } from "@/components/ui/states";

export default function WorkspaceLoading() {
  return (
    <PageContainer>
      <LoadingRegion label="Loading page">
        <div className="flex flex-col gap-6">
          <Skeleton height="2rem" className="w-64" />
          <Skeleton lines={4} />
          <Skeleton height="12rem" />
        </div>
      </LoadingRegion>
    </PageContainer>
  );
}
