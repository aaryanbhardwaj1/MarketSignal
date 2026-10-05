import type { SourceVersion } from "@/lib/api/types";
import { formatBytes, formatDateTime, formatMs } from "@/lib/format";
import { Badge } from "../ui/badge";
import { StatusBadge } from "../ui/status-badge";
import { HealthBadge, VersionError, WarningBadges } from "./version-badges";

const TIMING_KEYS = ["parse_ms", "chunk_ms", "embed_ms", "index_ms", "health_ms"] as const;

function Timings({ timings }: { timings: SourceVersion["timings"] }) {
  if (!timings) return <span className="text-slate-400">-</span>;
  return (
    <dl className="grid grid-cols-[auto_auto] gap-x-3 text-xs tabular-nums">
      {TIMING_KEYS.filter((k) => typeof timings[k] === "number").map((k) => (
        <div key={k} className="contents">
          <dt className="text-slate-500">{k.replace("_ms", "")}</dt>
          <dd className="text-right text-slate-700">{formatMs(timings[k])}</dd>
        </div>
      ))}
      <dt className="font-semibold text-slate-700">total</dt>
      <dd className="text-right font-semibold text-slate-900">{formatMs(timings.total_ms)}</dd>
    </dl>
  );
}

function VersionCard({ version, current }: { version: SourceVersion; current: boolean }) {
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-lg font-semibold tabular-nums text-slate-900">v{version.version}</span>
        <StatusBadge status={version.status} />
        {current && <Badge tone="info">current</Badge>}
        <WarningBadges warnings={version.warnings} />
        <span className="ml-auto font-mono text-xs text-slate-400">{version.version_id}</span>
      </div>
      <div className="mt-4 grid gap-6 md:grid-cols-[1fr_auto]">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <Meta label="File" value={version.original_filename ?? "-"} />
          <Meta label="Size" value={formatBytes(version.byte_size)} />
          <Meta label="Class / confidentiality" value={`${version.source_class} / ${version.confidentiality}`} />
          <Meta label="Parents / children" value={`${version.parent_count ?? "-"} / ${version.child_count ?? "-"}`} />
          <Meta label="Embedding model" value={version.embedding_model ?? "-"} />
          <Meta label="Attempts" value={String(version.attempts)} />
          <Meta label="Created" value={formatDateTime(version.created_at)} />
          <Meta label="Ready" value={formatDateTime(version.ready_at)} />
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Health</dt>
            <dd className="mt-0.5">
              <HealthBadge health={version.health} />
            </dd>
          </div>
          {version.error_code && (
            <div className="sm:col-span-2 lg:col-span-3">
              <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Error</dt>
              <dd className="mt-0.5">
                <VersionError version={version} />
              </dd>
            </div>
          )}
        </dl>
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Timings</p>
          <Timings timings={version.timings} />
        </div>
      </div>
    </li>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words text-slate-800">{value}</dd>
    </div>
  );
}

export function VersionHistory({
  versions,
  currentVersionId,
}: {
  versions: SourceVersion[];
  currentVersionId: string | null;
}) {
  if (versions.length === 0) return <p className="text-sm text-slate-500">No versions recorded.</p>;
  const ordered = [...versions].sort((a, b) => b.version - a.version);
  return (
    <ol className="flex flex-col gap-4" aria-label="Version history, newest first">
      {ordered.map((v) => (
        <VersionCard key={v.version_id} version={v} current={v.version_id === currentVersionId} />
      ))}
    </ol>
  );
}
