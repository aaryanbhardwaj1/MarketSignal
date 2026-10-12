import { PageContainer } from "../ui/page-container";
import { PageHeader } from "../ui/page-header";
import { LoadingRegion, Skeleton } from "../ui/states";

/** Neutral page frame used until a section's content lands: a title and calm skeleton blocks. */
export function PagePlaceholder({ title, description }: { title: string; description?: string }) {
  return (
    <PageContainer>
      <div className="flex flex-col gap-6">
        <PageHeader title={title} description={description} />
        <LoadingRegion label={`Loading ${title}`}>
          <div className="flex flex-col gap-6">
            <div className="grid gap-4 sm:grid-cols-3">
              <Skeleton height="5.5rem" />
              <Skeleton height="5.5rem" />
              <Skeleton height="5.5rem" />
            </div>
            <Skeleton lines={4} />
            <Skeleton height="14rem" />
          </div>
        </LoadingRegion>
      </div>
    </PageContainer>
  );
}
