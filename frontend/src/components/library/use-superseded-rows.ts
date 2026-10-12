"use client";

import { useQueries } from "@tanstack/react-query";
import { getSource } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { SourceSummary } from "@/lib/api/types";
import { sourcesWithHistory, supersededRows, type LibraryFilters, type LibraryRow } from "@/lib/library-filters";

export interface SupersededRowsState {
  rows: LibraryRow[];
  /** True while any source's version history is still loading. */
  loading: boolean;
  /** Number of sources whose earlier versions could not be loaded. */
  failed: number;
  retry: () => void;
}

/**
 * Superseded versions are only on each source's detail, so they are fetched per source, and only
 * when the filters ask for them. Failures are reported (never silently dropped) so the page can
 * say the list is partial.
 */
export function useSupersededRows(ws: string, list: readonly SourceSummary[], filters: LibraryFilters): SupersededRowsState {
  const wanted = filters.includeSuperseded || filters.status === "superseded";
  const ids = wanted ? sourcesWithHistory(list) : [];
  const histories = useQueries({
    queries: ids.map((id) => ({
      queryKey: queryKeys.source(ws, id),
      queryFn: ({ signal }: { signal: AbortSignal }) => getSource(ws, id, signal),
    })),
  });
  const failedQueries = histories.filter((h) => h.isError);
  return {
    rows: histories.flatMap((h) => (h.data ? supersededRows(h.data) : [])),
    loading: histories.some((h) => h.isPending),
    failed: failedQueries.length,
    retry: () => {
      for (const h of failedQueries) void h.refetch();
    },
  };
}
