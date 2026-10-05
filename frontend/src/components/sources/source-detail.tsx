"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { getSource } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { SourceDetail as SourceDetailData } from "@/lib/api/types";
import { isNonTerminalStatus, retryable } from "@/lib/status";
import { Badge } from "../ui/badge";
import { PageHeader } from "../ui/card";
import { ErrorPanel, InlineError } from "../ui/error-panel";
import { buttonClass } from "../ui/form-controls";
import { Loading } from "../ui/loading";
import { DeleteSourceDialog } from "./delete-source-dialog";
import { useSourceMutations } from "./use-source-mutations";
import { VersionHistory } from "./version-history";

function latestOf(source: SourceDetailData | undefined) {
  if (!source || source.versions.length === 0) return null;
  return source.versions.reduce((a, b) => (b.version > a.version ? b : a));
}

export function SourceDetail({ ws, sourceId }: { ws: string; sourceId: string }) {
  const router = useRouter();
  const { retry, remove } = useSourceMutations(ws);
  const [confirming, setConfirming] = useState(false);
  const { data, error, isPending, refetch } = useQuery({
    queryKey: queryKeys.source(ws, sourceId),
    queryFn: ({ signal }) => getSource(ws, sourceId, signal),
    refetchInterval: (query) =>
      isNonTerminalStatus(latestOf(query.state.data)?.status) ? 3_000 : false,
  });
  const backHref = `/w/${encodeURIComponent(ws)}/sources`;

  if (isPending) return <Loading label="Loading source..." />;
  if (error) return <ErrorPanel error={error} title="Source unavailable" />;

  const latest = latestOf(data);

  return (
    <>
      <Link href={backHref} className="text-sm text-indigo-700 hover:underline">
        &larr; All sources
      </Link>
      <PageHeader
        eyebrow={
          <span className="font-mono">
            {ws} / {data.source_code}
          </span>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {data.title}
            {data.deleted && <Badge tone="muted">deleted</Badge>}
          </span>
        }
        description={`Type ${data.source_type} - ${data.versions.length} version(s). Superseded versions stay resolvable for existing evidence handles.`}
        actions={
          <div className="flex gap-2">
            {retryable(latest?.status) && (
              <button
                type="button"
                className={buttonClass("secondary")}
                disabled={retry.isPending}
                onClick={() => retry.mutate(data.source_id, { onSettled: () => void refetch() })}
              >
                {retry.isPending ? "Retrying..." : "Retry ingestion"}
              </button>
            )}
            {!data.deleted && (
              <button
                type="button"
                className={buttonClass("danger")}
                onClick={() => {
                  remove.reset();
                  setConfirming(true);
                }}
              >
                Delete
              </button>
            )}
          </div>
        }
      />
      {retry.error && <InlineError error={retry.error} />}
      <VersionHistory versions={data.versions} currentVersionId={data.current_version_id} />
      <DeleteSourceDialog
        source={confirming ? data : null}
        busy={remove.isPending}
        error={remove.error}
        onCancel={() => setConfirming(false)}
        onConfirm={() =>
          remove.mutate(data.source_id, {
            onSuccess: () => {
              setConfirming(false);
              router.push(backHref);
            },
          })
        }
      />
    </>
  );
}
