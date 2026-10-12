import type { EvalCatalog, EvalProvenance } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";
import { shortHash } from "@/lib/eval-view";
import { Table, type Column } from "@/components/ui/table";

/** Caveats block. Rendered unconditionally on the Overview; per tab it lists the relevant ones. */
export function Caveats({ caveats, title = "Caveats" }: { caveats: EvalCatalog["caveats"]; title?: string }) {
  if (caveats.length === 0) return null;
  return (
    <section aria-label={title} className="rounded-lg border border-warn/25 bg-warn-subtle px-4 py-3">
      <p className="text-base font-semibold text-primary">{title}</p>
      <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-5 text-base text-secondary">
        {caveats.map((c) => (
          <li key={c.id}>{c.text}</li>
        ))}
      </ul>
    </section>
  );
}

export interface ProvenanceRow {
  id: string;
  label: string;
  provenance: EvalProvenance;
}

const mono = (v: string | null) => (v ? <span className="font-mono text-sm">{v}</span> : <span className="text-muted">-</span>);

/** Dataset, split, timestamp, config, model and git per evaluation run. */
export function ProvenanceTable({ rows, caption }: { rows: ProvenanceRow[]; caption: string }) {
  const columns: Column<ProvenanceRow>[] = [
    { key: "run", header: "Run", cell: (r) => <span className="font-medium">{r.label}</span> },
    {
      key: "dataset",
      header: "Dataset",
      cell: (r) => (
        <span className="flex flex-col">
          <span>
            {r.provenance.dataset.name}
            {r.provenance.dataset.version && r.provenance.dataset.version !== r.provenance.dataset.name
              ? ` (${r.provenance.dataset.version})`
              : ""}
          </span>
          <span className="font-mono text-xs text-muted">sha256 {shortHash(r.provenance.dataset.sha256)}</span>
        </span>
      ),
    },
    { key: "split", header: "Split", cell: (r) => r.provenance.split ?? <span className="text-muted">-</span> },
    { key: "at", header: "Recorded", cell: (r) => <span className="whitespace-nowrap">{formatDateTime(r.provenance.at)}</span> },
    { key: "config", header: "Config", cell: (r) => mono(r.provenance.config_hash) },
    { key: "model", header: "Model", cell: (r) => mono(r.provenance.model) },
    { key: "git", header: "Git", cell: (r) => mono(r.provenance.git) },
  ];
  return <Table columns={columns} rows={rows} rowKey={(r) => r.id} caption={caption} density="compact" />;
}
