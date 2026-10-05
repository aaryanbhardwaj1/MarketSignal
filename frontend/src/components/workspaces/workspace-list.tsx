"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { listWorkspaces } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import { ErrorPanel } from "../ui/error-panel";
import { Loading } from "../ui/loading";

export function WorkspaceList() {
  const { data, error, isPending } = useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: ({ signal }) => listWorkspaces(signal),
  });

  if (isPending) return <Loading label="Loading workspaces..." />;
  if (error) return <ErrorPanel error={error} title="Could not load workspaces" />;
  if (data.length === 0) {
    return <p className="text-sm text-slate-500">No workspaces yet. Create the first one.</p>;
  }

  return (
    <ul className="grid gap-4 sm:grid-cols-2">
      {data.map((w) => (
        <li key={w.id}>
          <Link
            href={`/w/${encodeURIComponent(w.code)}`}
            className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-300 hover:shadow-md focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            <span className="font-mono text-xs font-semibold tracking-wide text-indigo-700">
              {w.code}
            </span>
            <span className="mt-1 font-semibold text-slate-900">{w.name}</span>
            {w.description && (
              <span className="mt-2 text-sm text-slate-600">{w.description}</span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}
