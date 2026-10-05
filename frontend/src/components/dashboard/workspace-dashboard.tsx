"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getWorkspace } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import { formatNumber } from "@/lib/format";
import { Card, PageHeader } from "../ui/card";
import { ErrorPanel } from "../ui/error-panel";
import { Loading } from "../ui/loading";
import { CountList } from "./count-list";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</dd>
    </div>
  );
}

const LINKS = [
  { slug: "sources", label: "Sources", text: "Ingestion status, versions, uploads and retries." },
  { slug: "search", label: "Smoke search", text: "Single-lane lexical or dense retrieval check." },
  { slug: "evidence", label: "Evidence lookup", text: "Resolve a handle to its exact parent text." },
] as const;

export function WorkspaceDashboard({ ws }: { ws: string }) {
  const { data, error, isPending } = useQuery({
    queryKey: queryKeys.workspace(ws),
    queryFn: ({ signal }) => getWorkspace(ws, signal),
  });

  if (isPending) return <Loading label="Loading workspace..." />;
  if (error) return <ErrorPanel error={error} title={`Workspace ${ws} unavailable`} />;

  const sourceCount = Object.values(data.sources_by_class).reduce((a, b) => a + b, 0);

  return (
    <>
      <PageHeader eyebrow={data.code} title={data.name} description={data.description} />
      <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Corpus version" value={formatNumber(data.corpus_version)} />
        <Stat label="Sources" value={formatNumber(sourceCount)} />
        <Stat label="Parents" value={formatNumber(data.parent_count)} />
        <Stat label="Children" value={formatNumber(data.child_count)} />
      </dl>
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Sources by class">
          <CountList counts={data.sources_by_class} empty="No sources yet." />
        </Card>
        <Card title="Sources by status">
          <CountList counts={data.sources_by_status} asStatus empty="No sources yet." />
        </Card>
      </div>
      <nav aria-label="Workspace tools" className="grid gap-4 md:grid-cols-3">
        {LINKS.map(({ slug, label, text }) => (
          <Link
            key={slug}
            href={`/w/${encodeURIComponent(ws)}/${slug}`}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-indigo-300 hover:shadow-md focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            <span className="font-semibold text-indigo-700">{label} &rarr;</span>
            <span className="mt-1 block text-sm text-slate-600">{text}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
