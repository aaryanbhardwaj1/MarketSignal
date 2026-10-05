"use client";

import { useQuery } from "@tanstack/react-query";
import { listSources } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import { hasInFlightSources } from "@/lib/status";
import { Card, PageHeader } from "../ui/card";
import { ErrorPanel } from "../ui/error-panel";
import { Loading } from "../ui/loading";
import { SourcesTable } from "./sources-table";
import { UploadForm } from "./upload-form";
import { useSourceMutations } from "./use-source-mutations";

const POLL_INTERVAL_MS = 3_000;

export function SourcesView({ ws }: { ws: string }) {
  const { invalidate } = useSourceMutations(ws);
  const { data, error, isPending, isFetching } = useQuery({
    queryKey: queryKeys.sources(ws),
    queryFn: ({ signal }) => listSources(ws, signal),
    refetchInterval: (query) => (hasInFlightSources(query.state.data) ? POLL_INTERVAL_MS : false),
  });
  const polling = hasInFlightSources(data);

  return (
    <>
      <PageHeader
        eyebrow={ws}
        title="Sources"
        description="Every uploaded document, its latest immutable version and ingestion outcome. Click a row for full version history."
        actions={
          polling ? (
            <p role="status" className="flex items-center gap-2 text-xs text-sky-700">
              <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />
              Ingestion in progress - refreshing every 3 s{isFetching ? "..." : ""}
            </p>
          ) : null
        }
      />
      <Card title="Upload a source">
        <UploadForm ws={ws} onUploaded={() => void invalidate()} />
      </Card>
      {isPending ? (
        <Loading label="Loading sources..." />
      ) : error ? (
        <ErrorPanel error={error} title="Could not load sources" />
      ) : (
        <SourcesTable ws={ws} sources={data} />
      )}
    </>
  );
}
