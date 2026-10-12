"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { getSource, listSources } from "@/lib/api/endpoints";
import { describeError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/api/query-keys";
import { formatNumber } from "@/lib/format";
import { errorMessage } from "@/lib/labels";
import {
  DEFAULT_LIBRARY_FILTERS,
  isFiltered,
  libraryCounts,
  mergeRows,
  parseLibraryFilters,
  sourceRows,
  sourcesWithHistory,
  supersededRows,
  writeLibraryFilters,
  type LibraryFilters,
} from "@/lib/library-filters";
import { hasInFlightSources } from "@/lib/status";
import { PageContainer } from "../ui/page-container";
import { PageHeader } from "../ui/page-header";
import { SearchInput } from "../ui/search-input";
import { Section } from "../ui/section";
import { ErrorState, LoadingRegion } from "../ui/states";
import { LibraryFilterBar } from "./library-filter-bar";
import { LibraryTable } from "./library-table";
import { LibrarySearchResults } from "./search-results";

const POLL_INTERVAL_MS = 3_000;

function plural(n: number, one: string, many: string): string {
  return `${formatNumber(n)} ${n === 1 ? one : many}`;
}

/** Evidence Library: what MarketSignal can cite, with search, filters and a sources table. */
export function LibraryView({ ws }: { ws: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const filters = parseLibraryFilters(params);

  const sources = useQuery({
    queryKey: queryKeys.sources(ws),
    queryFn: ({ signal }) => listSources(ws, signal),
    refetchInterval: (query) => (hasInFlightSources(query.state.data) ? POLL_INTERVAL_MS : false),
  });
  const list = useMemo(() => sources.data ?? [], [sources.data]);
  const historyIds = filters.includeSuperseded || filters.status === "superseded" ? sourcesWithHistory(list) : [];
  const histories = useQueries({
    queries: historyIds.map((id) => ({
      queryKey: queryKeys.source(ws, id),
      queryFn: ({ signal }: { signal: AbortSignal }) => getSource(ws, id, signal),
    })),
  });
  const historyRows = histories.flatMap((h) => (h.data ? supersededRows(h.data) : []));
  const rows = mergeRows(sourceRows(list), historyRows);
  const counts = libraryCounts(list);

  const replaceParams = (next: URLSearchParams) => {
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  const setFilters = (next: LibraryFilters) => replaceParams(writeLibraryFilters(params.toString(), next));
  const clearFilters = () => setFilters(DEFAULT_LIBRARY_FILTERS);
  const setQuery = (value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set("q", value);
    else next.delete("q");
    replaceParams(next);
  };

  const meta = sources.data ? (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      <span>{plural(counts.sources, "source", "sources")}</span>
      <span>{formatNumber(counts.ready)} ready</span>
      {counts.processing > 0 && <span>{formatNumber(counts.processing)} processing</span>}
      {counts.failed > 0 && <span>{formatNumber(counts.failed)} failed</span>}
      <span>{plural(counts.passages, "evidence passage", "evidence passages")}</span>
    </span>
  ) : undefined;

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Evidence Library"
        description="The documents, research and data MarketSignal can draw on. Every answer and insight cites a passage or table held here."
        meta={meta}
      />

      <div className="mt-6 max-w-reading">
        <SearchInput
          key={q}
          id="library-search"
          label="Search the Evidence Library"
          placeholder="Search passages, for example “fit inconsistency”"
          defaultValue={q}
          onSubmit={setQuery}
        />
      </div>

      <div className="mt-4 flex flex-col">
        {q && (
          <LibrarySearchResults
            ws={ws}
            q={q}
            filters={filters}
            onClearSearch={() => setQuery("")}
            onClearFilters={filters.type || filters.cls ? clearFilters : undefined}
          />
        )}

        <Section
          title="Sources"
          description="Each source is listed at its current version. Include superseded versions to see what changed over time."
        >
          {sources.isPending ? (
            <LoadingRegion label="Loading sources" lines={6} />
          ) : sources.isError ? (
            <ErrorState
              title="The library could not be loaded"
              description={errorMessage(describeError(sources.error).code).label}
              retry={() => void sources.refetch()}
            />
          ) : (
            <div className="flex flex-col gap-4">
              <LibraryFilterBar rows={rows} filters={filters} onChange={setFilters} onReset={isFiltered(filters) ? clearFilters : undefined} />
              <LibraryTable ws={ws} rows={rows} filters={filters} onClearFilters={clearFilters} empty={list.length === 0} />
              {counts.processing > 0 && (
                <p role="status" className="text-sm text-muted">
                  {plural(counts.processing, "source is", "sources are")} still being processed. This list refreshes automatically.
                </p>
              )}
            </div>
          )}
        </Section>

        <p className="mt-6 text-sm text-muted">
          Structured datasets behind computed figures are listed in{" "}
          <Link href={`/w/${encodeURIComponent(ws)}/analytics`} className="rounded-sm font-medium text-accent-text hover:underline">
            Analytics
          </Link>
          .
        </p>
      </div>
    </PageContainer>
  );
}
