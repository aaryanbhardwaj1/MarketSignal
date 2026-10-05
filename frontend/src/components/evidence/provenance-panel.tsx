import type { Evidence } from "@/lib/api/types";
import { truncateHash } from "@/lib/format";
import { CopyButton } from "../ui/copy-button";

function HashRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-1.5">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="flex items-center gap-1">
        <code className="font-mono text-xs text-slate-800" title={value ?? undefined}>
          {truncateHash(value)}
        </code>
        {value && <CopyButton value={value} label="Copy" />}
      </dd>
    </div>
  );
}

function PlainRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-mono text-xs text-slate-800">{value ?? "-"}</dd>
    </div>
  );
}

export function ProvenancePanel({ evidence }: { evidence: Evidence }) {
  const p = evidence.provenance;
  return (
    <dl className="divide-y divide-slate-100">
      <HashRow label="Parent content hash" value={evidence.content_hash} />
      <HashRow label="Parent sha256 (provenance)" value={p.parent_content_sha256} />
      <HashRow label="Source file sha256" value={p.source_content_sha256} />
      <PlainRow label="Parser" value={p.parser_version} />
      <PlainRow label="Structure" value={p.structure_version} />
      <PlainRow label="Chunking policy" value={p.chunking_policy_version} />
      <PlainRow label="Embedding model" value={p.embedding_model} />
    </dl>
  );
}
