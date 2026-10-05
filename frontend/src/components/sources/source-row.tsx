"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";
import type { SourceSummary } from "@/lib/api/types";
import { formatMs } from "@/lib/format";
import { retryable } from "@/lib/status";
import { Badge } from "../ui/badge";
import { buttonClass } from "../ui/form-controls";
import { StatusBadge } from "../ui/status-badge";
import { HealthBadge, VersionError, WarningBadges } from "./version-badges";

export function SourceRow({
  ws,
  source,
  retrying,
  onRetry,
  onDelete,
}: {
  ws: string;
  source: SourceSummary;
  retrying: boolean;
  onRetry: () => void;
  onDelete: () => void;
}) {
  const router = useRouter();
  const href = `/w/${encodeURIComponent(ws)}/sources/${encodeURIComponent(source.source_id)}`;
  const v = source.latest;

  const onRowClick = (event: MouseEvent<HTMLTableRowElement>) => {
    if ((event.target as HTMLElement).closest("a,button")) return;
    router.push(href);
  };

  return (
    <tr onClick={onRowClick} className="cursor-pointer align-top hover:bg-slate-50">
      <td className="px-3 py-3">
        <Link href={href} className="font-mono text-xs font-semibold text-indigo-700 hover:underline">
          {source.source_code}
        </Link>
        {source.deleted && (
          <span className="ml-1">
            <Badge tone="muted">deleted</Badge>
          </span>
        )}
      </td>
      <td className="max-w-[16rem] px-3 py-3 text-slate-900">
        <span className="line-clamp-2">{source.title}</span>
        {v?.original_filename && (
          <span className="block truncate text-xs text-slate-500">{v.original_filename}</span>
        )}
      </td>
      <td className="px-3 py-3 text-slate-600">{source.source_type}</td>
      <td className="px-3 py-3 capitalize text-slate-600">{v?.source_class ?? "-"}</td>
      <td className="px-3 py-3 capitalize text-slate-600">{v?.confidentiality ?? "-"}</td>
      <td className="px-3 py-3 tabular-nums text-slate-600">{v ? `v${v.version}` : "-"}</td>
      <td className="px-3 py-3">
        <StatusBadge status={v?.status} />
      </td>
      <td className="px-3 py-3 tabular-nums text-slate-600">
        {v?.parent_count ?? "-"} / {v?.child_count ?? "-"}
      </td>
      <td className="px-3 py-3 tabular-nums text-slate-600">{formatMs(v?.timings?.total_ms)}</td>
      <td className="px-3 py-3">
        <VersionError version={v} />
      </td>
      <td className="px-3 py-3">
        <WarningBadges warnings={v?.warnings} />
      </td>
      <td className="px-3 py-3">
        <HealthBadge health={v?.health ?? null} />
      </td>
      <td className="px-3 py-3">
        <div className="flex justify-end gap-1.5">
          {retryable(v?.status) && (
            <button
              type="button"
              className={buttonClass("secondary", "sm")}
              onClick={onRetry}
              disabled={retrying}
              aria-label={`Retry ingestion of ${source.source_code}`}
            >
              {retrying ? "Retrying..." : "Retry"}
            </button>
          )}
          {!source.deleted && (
            <button
              type="button"
              className={buttonClass("ghost", "sm")}
              onClick={onDelete}
              aria-label={`Delete ${source.source_code}`}
            >
              <span className="text-red-700">Delete</span>
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}
