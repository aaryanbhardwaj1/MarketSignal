"use client";

import { useQuery } from "@tanstack/react-query";
import { searchWorkspace } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { SearchMode, SourceClass } from "@/lib/api/types";
import { DEFAULT_SEARCH_K, SEARCH_MODE_LABELS, flagMessage, formatTimings } from "@/lib/search";
import { PageHeader } from "../ui/card";
import { ErrorPanel } from "../ui/error-panel";
import { Loading } from "../ui/loading";
import { SearchForm } from "./search-form";
import { SearchResults } from "./search-results";

export function SearchView({
  ws,
  q,
  mode,
  sourceClasses,
}: {
  ws: string;
  q: string;
  mode: SearchMode;
  sourceClasses: readonly SourceClass[];
}) {
  const query = useQuery({
    queryKey: queryKeys.search(ws, q, mode, DEFAULT_SEARCH_K, sourceClasses),
    queryFn: ({ signal }) =>
      searchWorkspace(ws, { q, mode, k: DEFAULT_SEARCH_K, sourceClasses }, signal),
    enabled: q.length > 0,
  });

  return (
    <>
      <PageHeader
        eyebrow={ws}
        title="Search"
        description="Search ingested evidence. Each result opens the evidence viewer at the exact matching span."
      />
      <SearchForm key={`${q}|${mode}|${sourceClasses.join(",")}`} ws={ws} q={q} mode={mode} sourceClasses={sourceClasses} />
      {!q ? (
        <p className="text-sm text-slate-500">Enter a query to search this workspace.</p>
      ) : query.isPending ? (
        <Loading label={`Searching (${SEARCH_MODE_LABELS[mode]})...`} />
      ) : query.isError ? (
        <ErrorPanel error={query.error} title="Search failed" />
      ) : (
        <>
          {query.data.flags.length > 0 && (
            <div role="alert" className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <ul className="list-disc pl-5">
                {query.data.flags.map((flag) => (
                  <li key={flag}>{flagMessage(flag)}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-sm text-slate-600">
            {query.data.items.length} result(s) for{" "}
            <span className="font-medium">&quot;{query.data.query}&quot;</span> in{" "}
            <span className="font-medium">{query.data.mode}</span> mode (top {DEFAULT_SEARCH_K}).
          </p>
          <SearchResults ws={ws} items={query.data.items} />
          {Object.keys(query.data.timings_ms).length > 0 && (
            <p className="font-mono text-xs text-slate-400">{formatTimings(query.data.timings_ms)}</p>
          )}
        </>
      )}
    </>
  );
}
