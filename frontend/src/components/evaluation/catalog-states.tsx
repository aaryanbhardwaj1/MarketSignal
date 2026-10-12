import { Callout } from "@/components/ui/callout";
import { ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import { catalogFailure } from "@/lib/eval-view";

export const CATALOG_UNAVAILABLE = "The evaluation catalog is only served in development builds.";

export function CatalogLoading() {
  return (
    <LoadingRegion label="Loading evaluation results">
      <div className="flex flex-col gap-4">
        <Skeleton height="2.25rem" className="w-full" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} height="6.5rem" />
          ))}
        </div>
        <Skeleton lines={6} />
      </div>
    </LoadingRegion>
  );
}

/** Unavailable (route absent in production or catalog not built) versus a genuine load failure. */
export function CatalogProblem({ error, retry }: { error: unknown; retry: () => void }) {
  if (catalogFailure(error) === "unavailable") {
    return (
      <Callout tone="neutral" title={CATALOG_UNAVAILABLE}>
        Evaluation results are precomputed from committed evaluation artifacts and exposed only by development API
        builds. Run the API in development mode to review them.
      </Callout>
    );
  }
  return (
    <ErrorState
      title="Evaluation results could not be loaded"
      description="The evaluation catalog request failed. Check that the API is running, then try again."
      retry={retry}
      devDetail={error instanceof Error ? error.message : undefined}
    />
  );
}
