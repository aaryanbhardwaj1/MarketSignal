import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog } from "@/lib/api/contracts";
import { allProvenance, gitForPath, shortHash } from "@/lib/eval-view";
import { formatBytes, formatDateTime } from "@/lib/format";
import { ProvenanceTable } from "./caveats";

type SourceRow = EvalCatalog["sources"][number] & { git: string | null };

export function ProvenanceTab({ catalog }: { catalog: EvalCatalog }) {
  const rows: SourceRow[] = catalog.sources.map((s) => ({ ...s, git: gitForPath(catalog, s.path) }));
  const columns: Column<SourceRow>[] = [
    { key: "path", header: "Artifact", cell: (s) => <span className="break-all font-mono text-sm">{s.path}</span> },
    {
      key: "sha",
      header: "sha256",
      cell: (s) => (
        <span className="font-mono text-sm" title={s.sha256}>
          {shortHash(s.sha256, 12)}
        </span>
      ),
    },
    { key: "bytes", header: "Size", align: "right", cell: (s) => <span className="whitespace-nowrap tabular-nums">{formatBytes(s.bytes)}</span> },
    {
      key: "git",
      header: "Run commit",
      cell: (s) => (s.git ? <span className="font-mono text-sm">{s.git}</span> : <span className="text-muted">Not recorded</span>),
    },
  ];
  return (
    <div>
      <p className="max-w-reading text-base text-secondary">
        The catalog behind these pages was built from the committed artifacts below on{" "}
        <span className="font-medium text-primary">{formatDateTime(catalog.built_at)}</span>. Nothing is computed when the
        page loads; each figure carries a pointer into one of these files.
      </p>

      <Section title="Evaluation runs" description="Dataset, split, timestamp, configuration, model and commit for each run.">
        <ProvenanceTable rows={allProvenance(catalog)} caption="Provenance of each evaluation run" />
      </Section>

      <Section
        title="Source artifacts"
        description={`${catalog.sources.length} files with content hashes. Commit is shown where the artifact belongs to a recorded run.`}
      >
        <Table columns={columns} rows={rows} rowKey={(s) => s.path} caption="Source artifacts with sha256 and size" density="compact" />
      </Section>
    </div>
  );
}
