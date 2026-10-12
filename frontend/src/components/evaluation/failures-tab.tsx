import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog } from "@/lib/api/contracts";
import { evalRunHref } from "@/lib/eval-view";
import { formatNumber } from "@/lib/format";

type FailureRun = EvalCatalog["failure_runs"][number];

const linkClass = "rounded-sm text-accent-text hover:underline";

export function FailuresTab({ catalog, ws }: { catalog: EvalCatalog; ws: string }) {
  const columns: Column<FailureRun>[] = [
    {
      key: "run",
      header: "Evaluation run",
      cell: (r) => (
        <Link href={evalRunHref(ws, r.run_id)} className={`${linkClass} font-medium`}>
          {r.label}
        </Link>
      ),
    },
    { key: "items", header: "Items", align: "right", cell: (r) => <span className="tabular-nums">{formatNumber(r.item_count)}</span> },
    {
      key: "buckets",
      header: "Stored failure buckets",
      cell: (r) =>
        r.buckets.length === 0 ? (
          <span className="text-muted">No failures recorded in this run</span>
        ) : (
          <ul className="flex flex-col gap-1">
            {r.buckets.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center gap-2">
                <Link href={evalRunHref(ws, r.run_id, { bucket: b.id })} className={linkClass}>
                  {b.label}
                </Link>
                <Badge tone="neutral">
                  {formatNumber(b.n)} of {formatNumber(r.item_count)}
                </Badge>
              </li>
            ))}
          </ul>
        ),
    },
  ];
  return (
    <div>
      <Callout tone="info" title="Failed cases are preserved, not discarded.">
        Every item from each run is kept, including misses and incorrect answers. Buckets come from the labels stored with
        each run; no new root-cause taxonomy is inferred here. Open a run to review its items one at a time.
      </Callout>
      <Section title="Runs and failure buckets" description="Choose a run or a bucket to review its items, expected evidence and stored checks.">
        <Table columns={columns} rows={catalog.failure_runs} rowKey={(r) => r.run_id} caption="Evaluation runs with failure buckets" />
      </Section>
    </div>
  );
}
