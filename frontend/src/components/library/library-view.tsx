"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listSources } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import { formatCount, formatNumber } from "@/lib/format";
import {
  DEFAULT_LIBRARY_FILTERS,
  filterLibraryRows,
  isFiltered,
  libraryCounts,
  mergeRows,
  parseLibraryFilters,
  sourceRows,
  writeLibraryFilters,
  type LibraryFilters,
} from "@/lib/library-filters";
import { hasInFlightSources } from "@/lib/status";
import { Button } from "../ui/button";
import { Callout } from "../ui/callout";
import { PageContainer } from "../ui/page-container";
import { PageHeader } from "../ui/page-header";
import { SearchInput } from "../ui/search-input";
import { Section } from "../ui/section";
import { ErrorState, LoadingRegion } from "../ui/states";
import { LibraryFilterBar } from "./library-filter-bar";
import { LibraryTable } from "./library-table";
import { LibrarySearchResults } from "./search-results";
import { useSupersededRows } from "./use-superseded-rows";
import { analyticsHref } from "@/lib/routes";

const SEARCH_INPUT_ID = "library-search";

const POLL_INTERVAL_MS = 3_000;

/**
 * The search box keeps its element (and focus) across searches; it is only remounted when a clear
 * action empties it. Clear actions also remove the control that triggered them, so focus then
 * returns to the search box instead of falling to <body>.
 */
function useSearchReset(inputId: string): { searchKey: number; afterClear: () => void } {
  const [searchKey, setSearchKey] = useState(0);
  const refocus = useRef(false);
  useEffect(() => {
    if (!refocus.current) return;
    refocus.current = false;
    document.getElementById(inputId)?.focus();
  }, [searchKey, inputId]);
  const afterClear = useCallback(() => {
    refocus.current = true;
    setSearchKey((k) => k + 1);
  }, []);
  return { searchKey, afterClear };
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
  const history = useSupersededRows(ws, list, filters);
  const rows = mergeRows(sourceRows(list), history.rows);
  const counts = libraryCounts(list);
  const shownCount = filterLibraryRows(rows, filters).length;

  const { searchKey, afterClear } = useSearchReset(SEARCH_INPUT_ID);
  const [searchText, setSearchText] = useState("");
  const onSummary = useCallback((text: string) => setSearchText(text), []);
  const filterText = sources.data
    ? isFiltered(filters)
      ? `Showing ${formatNumber(shownCount)} of ${formatCount(rows.length, "source", "sources")}`
      : `${formatCount(shownCount, "source", "sources")}`
    : "";
  const announcement = [q ? searchText : null, filterText].filter(Boolean).join(". ");

  const replaceParams = (next: URLSearchParams) => {
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  const setFilters = (next: LibraryFilters) => replaceParams(writeLibraryFilters(params.toString(), next));
  const setQuery = (value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set("q", value);
    else next.delete("q");
    replaceParams(next);
  };
  const clearFilters = () => {
    setFilters(DEFAULT_LIBRARY_FILTERS);
    afterClear();
  };
  const clearSearch = () => {
    setQuery("");
    afterClear();
  };

  const meta = sources.data ? (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      <span>{formatCount(counts.sources, "source", "sources")}</span>
      <span>{formatNumber(counts.ready)} ready</span>
      {counts.processing > 0 && <span>{formatNumber(counts.processing)} processing</span>}
      {counts.failed > 0 && <span>{formatNumber(counts.failed)} failed</span>}
      <span>{formatCount(counts.passages, "evidence passage", "evidence passages")}</span>
    </span>
  ) : undefined;

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Evidence Library"
        description="The documents, research and data MarketSignal draws on. Answers and insights cite the passages and tables they rely on."
        meta={meta}
      />

      <div className="mt-6 max-w-reading">
        <SearchInput
          key={searchKey}
          id={SEARCH_INPUT_ID}
          label="Search the Evidence Library"
          placeholder="Search passages, for example “fit inconsistency”"
          defaultValue={q}
          onSubmit={setQuery}
        />
      </div>

      <p role="status" className="sr-only">
        {announcement}
      </p>

      <div className="mt-4 flex flex-col">
        {q && (
          <LibrarySearchResults
            ws={ws}
            q={q}
            filters={filters}
            onClearSearch={clearSearch}
            onClearFilters={filters.type || filters.cls ? clearFilters : undefined}
            onSummary={onSummary}
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
              error={sources.error}
              retry={() => void sources.refetch()}
            />
          ) : (
            <div className="flex flex-col gap-4">
              <LibraryFilterBar rows={rows} filters={filters} onChange={setFilters} onReset={isFiltered(filters) ? clearFilters : undefined} />
              {history.failed > 0 && (
                <Callout
                  tone="warn"
                  title="Some earlier versions could not be loaded"
                  action={
                    <Button variant="secondary" size="sm" onClick={history.retry}>
                      Try again
                    </Button>
                  }
                >
                  {`Superseded versions of ${formatCount(history.failed, "source", "sources")} are missing from this list.`}
                </Callout>
              )}
              {history.loading && <p className="text-sm text-muted">Loading earlier versions…</p>}
              <LibraryTable ws={ws} rows={rows} filters={filters} onClearFilters={clearFilters} empty={list.length === 0} />
              {counts.processing > 0 && (
                <p role="status" className="text-sm text-muted">
                  {formatCount(counts.processing, "source is", "sources are")} still being processed. This list refreshes automatically.
                </p>
              )}
            </div>
          )}
        </Section>

        <p className="mt-6 text-sm text-muted">
          Structured datasets behind computed figures are listed in{" "}
          <Link href={analyticsHref(ws)} className="rounded-sm font-medium text-accent-text hover:underline">
            Analytics
          </Link>
          .
        </p>
      </div>
    </PageContainer>
  );
}
