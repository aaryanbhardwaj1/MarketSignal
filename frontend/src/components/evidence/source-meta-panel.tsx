import Link from "next/link";
import type { ReactNode } from "react";
import type { Evidence } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { StatusBadge } from "../ui/status-badge";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <dt className="shrink-0 text-xs text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words text-right text-sm text-slate-800">{children}</dd>
    </div>
  );
}

export function SourceMetaPanel({ ws, evidence }: { ws: string; evidence: Evidence }) {
  const s = evidence.source;
  return (
    <dl className="divide-y divide-slate-100">
      <Row label="Title">{s.title}</Row>
      <Row label="Code">
        <Link
          href={`/w/${encodeURIComponent(ws)}/sources/${encodeURIComponent(s.source_id)}`}
          className="font-mono text-xs font-semibold text-indigo-700 hover:underline"
        >
          {s.source_code}
        </Link>
      </Row>
      <Row label="Class">
        <span className="capitalize">{s.source_class}</span>
      </Row>
      <Row label="Confidentiality">
        <span className="capitalize">{s.confidentiality}</span>
      </Row>
      <Row label="Type">{s.source_type}</Row>
      <Row label="Version">
        <span className="inline-flex items-center gap-2">
          v{s.version} <StatusBadge status={s.version_status} />
        </span>
      </Row>
      <Row label="File">{s.original_filename ?? "-"}</Row>
      <Row label="Ingested">{formatDateTime(s.ingested_at)}</Row>
    </dl>
  );
}
