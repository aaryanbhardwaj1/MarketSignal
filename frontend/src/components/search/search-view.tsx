"use client";

import { useQuery } from "@tanstack/react-query";
import { devSearch } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { SearchMode } from "@/lib/api/types";
import { Badge } from "../ui/badge";
import { PageHeader } from "../ui/card";
import { ErrorPanel } from "../ui/error-panel";
import { Loading } from "../ui/loading";
import { SearchForm } from "./search-form";
import { SearchResults } from "./search-results";

const K = 10;

export function SearchView({ ws, q, mode }: { ws: string; q: string; mode: SearchMode }) {
  const query = useQuery({
    queryKey: queryKeys.search(ws, q, mode, K),
    queryFn: ({ signal }) => devSearch(ws, { q, mode, k: K }, signal),
    enabled: q.length > 0,
  });

  return (
    <>
      <PageHeader
        eyebrow={ws}
        title="Phase 1 smoke search (single lane; no fusion/rerank)"
        description="Developer check that ingested children are retrievable. Each result opens the evidence viewer at the exact child span."
        actions={<Badge tone="warning">dev only</Badge>}
      />
      <SearchForm key={`${q}|${mode}`} ws={ws} q={q} mode={mode} />
      {!q ? (
        <p className="text-sm text-slate-500">Enter a query to run a single-lane search.</p>
      ) : query.isPending ? (
        <Loading label={`Searching (${mode})...`} />
      ) : query.isError ? (
        <ErrorPanel error={query.error} title="Search failed" />
      ) : (
        <>
          <p className="text-sm text-slate-600">
            {query.data.hits.length} hit(s) for <span className="font-medium">&quot;{query.data.query}&quot;</span>{" "}
            in <span className="font-medium">{query.data.mode}</span> mode (top {K}).
          </p>
          <SearchResults ws={ws} hits={query.data.hits} />
        </>
      )}
    </>
  );
}
