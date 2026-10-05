"use client";

import { useState } from "react";
import type { SourceSummary } from "@/lib/api/types";
import { InlineError } from "../ui/error-panel";
import { DeleteSourceDialog } from "./delete-source-dialog";
import { SourceRow } from "./source-row";
import { useSourceMutations } from "./use-source-mutations";

const COLUMNS = [
  "Code",
  "Title",
  "Type",
  "Class",
  "Confidentiality",
  "Latest",
  "Status",
  "Parents / children",
  "Ingest time",
  "Error",
  "Warnings",
  "Health",
];

export function SourcesTable({ ws, sources }: { ws: string; sources: SourceSummary[] }) {
  const { retry, remove } = useSourceMutations(ws);
  const [pendingDelete, setPendingDelete] = useState<SourceSummary | null>(null);

  if (sources.length === 0) {
    return <p className="text-sm text-slate-500">No sources yet. Upload a document to begin.</p>;
  }

  const confirmDelete = () => {
    if (!pendingDelete) return;
    remove.mutate(pendingDelete.source_id, { onSuccess: () => setPendingDelete(null) });
  };

  return (
    <>
      {retry.error && <InlineError error={retry.error} />}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <caption className="sr-only">Sources in workspace {ws}</caption>
          <thead className="bg-slate-50">
            <tr>
              {COLUMNS.map((c) => (
                <th
                  key={c}
                  scope="col"
                  className="whitespace-nowrap px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500"
                >
                  {c}
                </th>
              ))}
              <th scope="col" className="px-3 py-2.5">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sources.map((s) => (
              <SourceRow
                key={s.source_id}
                ws={ws}
                source={s}
                retrying={retry.isPending && retry.variables === s.source_id}
                onRetry={() => retry.mutate(s.source_id)}
                onDelete={() => {
                  remove.reset();
                  setPendingDelete(s);
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
      <DeleteSourceDialog
        source={pendingDelete}
        busy={remove.isPending}
        error={remove.error}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
}
